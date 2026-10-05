"""
The connection from this VM to Robinhood's Trading MCP — the transport under
the LIVE broker. Addendum A §16, §23-24; Addendum B §B13-B14.

    https://agent.robinhood.com/mcp/trading      (config/risk.yaml robinhood.mcp_url)

Authorisation is Robinhood's OAuth. It is done ONCE, by the account owner, on a
desktop device with the Robinhood app's verification step; this program never
sees a password. The resulting tokens are stored OUTSIDE the repository, in a
file readable only by this Linux user:

    ~/.config/stockbot2000/robinhood_oauth.json      (mode 600)

Refresh is automatic while the refresh token is valid (`refresh()`: before every
session once a quarter of the token's stated life has passed, and once more on a
rejected token). The MCP client never did this itself: it does not store when a
token was issued, so after a restart it treated the stored token as valid
forever, and on a rejection it went straight to the browser sign-in — the 09-24
token died 10-01 with its refresh token unused. When refresh fails, every
call raises NeedsLogin — the trader then halts (fail closed) and alerts the
owner to run --login again. Nothing ever falls back to trading without it.

    python robinhood_mcp.py --login     one-time sign-in (interactive; the owner)
    python robinhood_mcp.py --probe     read-only: accounts, the agentic account,
                                        buying power, positions, one quote
    python robinhood_mcp.py --tools     list the server's tools and their schemas

The program only calls tools by name through `call()`. Which calls may place
money-moving orders is decided in robinhood_live.py and the risk engine, never
here.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import asyncio
import concurrent.futures
import contextlib
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("robinhood_mcp")
# The HTTP and MCP client libraries log every request at INFO, which buried the
# trader's own lines in the cron log. Their warnings and errors still show.
for _noisy in ("httpx2", "httpx", "mcp.client.streamable_http"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

DEFAULT_URL = "https://agent.robinhood.com/mcp/trading"
TOKEN_FILE = Path(os.path.expanduser("~/.config/stockbot2000/robinhood_oauth.json"))
# The browser is sent here after consent. Nothing needs to be listening: the
# owner copies the address the browser lands on (it contains the one-time code)
# and pastes it back into the --login prompt. That works whether the browser is
# on this VM or on a laptop.
REDIRECT_URI = "http://localhost:8765/callback"
# Refresh once this fraction of the token's stated lifetime has passed. The 09-24
# token said ~8.1 days and was rejected after ~7.1, so the stated life is not trusted.
REFRESH_AFTER = 0.25
FALLBACK_TOKEN_ENDPOINT = "https://api.robinhood.com/oauth2/token/"


class NeedsLogin(RuntimeError):
    """No valid authorisation: the owner must run `robinhood_mcp.py --login`."""


class RobinhoodError(RuntimeError):
    """The Robinhood MCP returned an error for a tool call."""


def settings() -> dict:
    try:
        import risk_engine
        rh = risk_engine.load_limits().get("robinhood") or {}
    except Exception:                                        # noqa: BLE001
        rh = {}
    return {"mcp_url": rh.get("mcp_url", DEFAULT_URL), "account_number": rh.get("account_number")}


# --- token storage ------------------------------------------------------------

class FileTokenStorage:
    """mcp.client.auth.TokenStorage backed by one JSON file with mode 600."""

    def __init__(self, path: Path = TOKEN_FILE):
        self.path = path

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken
        t = dict(self._read().get("tokens") or {})
        t.pop("issued_at", None)
        return OAuthToken.model_validate(t) if t else None

    async def set_tokens(self, tokens) -> None:
        d = self._read()
        d["tokens"] = {**tokens.model_dump(mode="json", exclude_none=True), "issued_at": time.time(),
                       "login_at": time.time()}  # written ONLY on full --login, not on refresh()
        self._write(d)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull
        c = self._read().get("client")
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def set_client_info(self, info) -> None:
        d = self._read()
        d["client"] = info.model_dump(mode="json", exclude_none=True)
        self._write(d)


def _token_endpoint(url: str) -> str:
    import httpx2
    u = urlparse(url)
    try:
        r = httpx2.get(f"{u.scheme}://{u.netloc}/.well-known/oauth-authorization-server{u.path}", timeout=15)
        if r.status_code == 200 and r.json().get("token_endpoint"):
            return r.json()["token_endpoint"]
    except Exception as e:                                   # noqa: BLE001
        log.warning(f"token endpoint discovery failed ({e}); using {FALLBACK_TOKEN_ENDPOINT}")
    return FALLBACK_TOKEN_ENDPOINT


def refresh(force: bool = False, url: str | None = None, storage: "FileTokenStorage | None" = None,
            post=None) -> bool:
    """Exchange the stored refresh token for new tokens when due (or `force`). True = a usable token
    is stored. Serialised across processes with a lock file; a refresh another process did in the
    last minute counts, so two runs never spend one (possibly single-use) refresh token twice."""
    import fcntl
    st = storage or FileTokenStorage()
    st.path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(st.path.with_suffix(".lock"), os.O_WRONLY | os.O_CREAT, 0o600), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        d = st._read()
        t, c = d.get("tokens") or {}, d.get("client") or {}
        if not t.get("refresh_token") or not c.get("client_id"):
            return False
        age = time.time() - float(t.get("issued_at") or 0)
        life = float(t.get("expires_in") or 0)
        if age < 60 or (not force and life and age < REFRESH_AFTER * life):
            return True
        url = url or settings()["mcp_url"]
        data = {"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                "client_id": c["client_id"], "resource": url}
        try:
            if post is None:
                import httpx2
                r = httpx2.post(_token_endpoint(url), data=data, timeout=30)
                status, body = r.status_code, (r.json() if r.status_code == 200 else r.text[:200])
            else:
                status, body = post(data)
        except Exception as e:                               # noqa: BLE001 — a failed refresh is a NeedsLogin later
            log.warning(f"Robinhood token refresh failed: {e}")
            return False
        if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
            log.warning(f"Robinhood token refresh refused: HTTP {status} {body if status != 200 else ''}")
            return False
        new = {k: v for k, v in body.items() if v is not None}
        new.setdefault("refresh_token", t["refresh_token"])  # RFC 6749 §6: may be omitted = unchanged
        new["issued_at"] = time.time()
        d["tokens"] = new
        st._write(d)
        log.info("Robinhood token refreshed (old one %s)"
                 % (f"{age / 86400:.1f} days old" if t.get("issued_at") else "of unknown age"))
        return True


def _provider(url: str, interactive: bool):
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import OAuthClientMetadata

    async def redirect_handler(auth_url: str) -> None:
        if not interactive:
            raise NeedsLogin("Robinhood authorisation missing or expired — run: "
                             "./venv/bin/python robinhood_mcp.py --login")
        print("\n1. Open this address in a browser on your DESKTOP computer and approve access:\n")
        print(f"   {auth_url}\n")
        print("2. Complete the verification step in the Robinhood mobile app if it asks.")
        print("3. The browser then goes to a page starting http://localhost:8765/callback that")
        print("   will not load. That is expected. Copy the WHOLE address from the address bar.\n")

    async def callback_handler():
        pasted = input("4. Paste that address here and press Enter:\n> ").strip()
        q = parse_qs(urlparse(pasted).query)
        if "error" in q:
            raise NeedsLogin(f"authorisation refused: {q.get('error_description', q['error'])[0]}")
        if "code" not in q:
            raise NeedsLogin("no ?code= in the pasted address — copy the full address bar text")
        from mcp.shared.auth import AuthorizationCodeResult
        return AuthorizationCodeResult(code=q["code"][0], state=(q.get("state") or [None])[0],
                                       iss=(q.get("iss") or [None])[0])

    meta = OAuthClientMetadata(client_name="Stockbot2000", redirect_uris=[REDIRECT_URI],
                               grant_types=["authorization_code", "refresh_token"],
                               response_types=["code"], token_endpoint_auth_method="none")
    return OAuthClientProvider(server_url=url, client_metadata=meta, storage=FileTokenStorage(),
                               redirect_handler=redirect_handler, callback_handler=callback_handler)


def _parse(result):
    """Tool result -> Python value. JSON text is decoded; anything else is returned as text."""
    if getattr(result, "isError", False):
        texts = [getattr(c, "text", "") for c in (result.content or [])]
        raise RobinhoodError(" ".join(t for t in texts if t) or "tool error")
    sc = getattr(result, "structuredContent", None)
    if sc:
        return sc
    texts = [getattr(c, "text", None) for c in (result.content or [])]
    text = "\n".join(t for t in texts if t)
    try:
        return json.loads(text)
    except ValueError:
        return text


@contextlib.asynccontextmanager
async def _open(url: str, interactive: bool):
    """One authenticated, initialised MCP session."""
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    if not interactive:
        await asyncio.to_thread(refresh, False, url)
    async with httpx2.AsyncClient(auth=_provider(url, interactive), timeout=30.0) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session


async def _session_do(url: str, interactive: bool, fn):
    async with _open(url, interactive) as session:
        return await fn(session)


def _unwrap(e: BaseException) -> BaseException:
    """The NeedsLogin / RobinhoodError inside an anyio exception group, else e itself."""
    for x in getattr(e, "exceptions", None) or ():
        if isinstance(x, (NeedsLogin, RobinhoodError)):
            return x
        inner = _unwrap(x)
        if inner is not x:
            return inner
    return e


# --- one session per run -----------------------------------------------------
#
# Every call() used to open its own MCP session: HTTP connection, OAuth token
# check, initialise, call, tear down. A trader run makes dozens of calls (a
# quote per candidate, the portfolio, positions, each order's review / place /
# poll), so most of a run's latency was handshakes. `session()` keeps ONE
# session open on a background thread for the length of a run, and while it is
# open call() and calls() use it. Nothing about WHAT is called changes.
#
# If that session dies mid-run, later calls fall back to one session each, as
# before: a dropped connection must not halt the rest of the run. An error from
# a call is raised to the caller exactly as before (an order that fails in
# transport after submission is still UNKNOWN in robinhood_live and resolved by
# asking Robinhood, never by resubmitting).

_ACTIVE = None
CALL_TIMEOUT = 120.0


class Session:
    def __init__(self, url: str | None = None, interactive: bool = False, opener=None):
        self.url = url or settings()["mcp_url"]
        self.interactive = interactive
        self.opener = opener or (lambda: _open(self.url, self.interactive))
        self.loop, self.thread, self.queue = None, None, None
        self.ready = threading.Event()
        self.error, self.dead, self.calls_made = None, False, 0

    # the server side, on its own thread and event loop
    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        self.queue = asyncio.Queue()
        pending = None
        try:
            async with self.opener() as session:
                self.ready.set()
                while True:
                    item = await self.queue.get()
                    if item is None:
                        break
                    tool, args, fut = pending = item
                    try:
                        fut.set_result(_parse(await session.call_tool(tool, args or {})))
                    except Exception as e:                   # noqa: BLE001 — the caller gets it
                        fut.set_exception(_unwrap(e))
                    pending = None
        except BaseException as e:                           # noqa: BLE001 — the session is gone
            self.error = _unwrap(e)
        finally:
            self.dead = True
            self.ready.set()
            # Nothing waits forever on a session that no longer exists.
            if pending and not pending[2].done():
                pending[2].set_exception(self.error or RobinhoodError("MCP session closed"))
            while self.queue is not None and not self.queue.empty():
                item = self.queue.get_nowait()
                if item and not item[2].done():
                    item[2].set_exception(self.error or RobinhoodError("MCP session closed"))

    # the caller side
    def __enter__(self, retried: bool = False):
        global _ACTIVE
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="robinhood-mcp", daemon=True)
        self.thread.start()
        if not self.ready.wait(60):
            raise RobinhoodError("MCP session did not open within 60 s")
        if self.dead:
            self.thread.join(5)
            if (isinstance(self.error, NeedsLogin) and not self.interactive and not retried
                    and refresh(force=True, url=self.url)):
                self.ready.clear()
                self.error, self.dead = None, False
                return self.__enter__(retried=True)
            raise self.error or RobinhoodError("MCP session failed to open")
        self._prev, _ACTIVE = _ACTIVE, self
        return self

    def __exit__(self, *exc) -> None:
        global _ACTIVE
        if _ACTIVE is self:
            _ACTIVE = self._prev
        if not self.dead and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.queue.put_nowait, None)
        self.thread.join(30)
        log.info(f"robinhood: {self.calls_made} call(s) in one session")

    def call(self, tool: str, args: dict | None = None):
        fut = concurrent.futures.Future()
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, (tool, args or {}, fut))
        except RuntimeError:                                 # loop already closed
            raise RobinhoodError("MCP session closed") from None
        self.calls_made += 1
        try:
            return fut.result(timeout=CALL_TIMEOUT)
        except concurrent.futures.TimeoutError:
            # A stuck call would hold up every call queued behind it. Later
            # calls fall back to their own sessions; this one is reported as a
            # transport failure (an order in flight is then UNKNOWN, resolved
            # by asking Robinhood).
            self.dead = True
            raise


def session(url: str | None = None, interactive: bool = False, opener=None) -> Session:
    """`with robinhood_mcp.session():` — one MCP session for every call inside the block."""
    return Session(url, interactive, opener)


def _live_session():
    return _ACTIVE if _ACTIVE is not None and not _ACTIVE.dead else None


def calls(batch: list, interactive: bool = False, url: str | None = None) -> list:
    """Run several (tool, args) calls in ONE authenticated session. Returns their parsed results."""
    s = _live_session()
    if s is not None and not interactive:
        return [s.call(tool, args) for tool, args in batch]
    url = url or settings()["mcp_url"]

    async def run(session):
        out = []
        for tool, args in batch:
            out.append(_parse(await session.call_tool(tool, args or {})))
        return out
    try:
        try:
            return asyncio.run(_session_do(url, interactive, run))
        except BaseException as e:                           # noqa: BLE001
            # A rejected token: refresh once and retry (the server may end a token before its stated life).
            if interactive or not isinstance(_unwrap(e), NeedsLogin) or not refresh(force=True, url=url):
                raise
        return asyncio.run(_session_do(url, interactive, run))
    except NeedsLogin:
        raise
    except BaseException as e:                               # noqa: BLE001 — surface nested task errors
        inner = _unwrap(e)
        if inner is not e:
            raise inner from None
        raise


def call(tool: str, args: dict | None = None, interactive: bool = False) -> object:
    return calls([(tool, args or {})], interactive=interactive)[0]


def list_tools(interactive: bool = False) -> list:
    async def run(session):
        r = await session.list_tools()
        return [{"name": t.name, "schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", {})} for t in r.tools]
    return asyncio.run(_session_do(settings()["mcp_url"], interactive, run))


LOGIN_WARN_DAYS = 20   # alert when the last full --login is this many days old
LOGIN_MAX_DAYS  = 30   # assumed max lifetime of a Robinhood refresh token


def _check_login_age() -> None:
    """Alert via Telegram/desktop when the last full login is approaching its expiry.
    Runs during --refresh (called every 6 h from daily.sh) so the owner is warned
    before trading halts.  No-ops silently when notify is unavailable."""
    try:
        st = FileTokenStorage()
        t = st._read().get("tokens") or {}
        login_at = float(t.get("login_at") or 0)
        if not login_at:
            return  # no login_at recorded yet — will be set on next --login
        days = (time.time() - login_at) / 86400
        if days < LOGIN_WARN_DAYS:
            return
        days_left = max(0, LOGIN_MAX_DAYS - int(days))
        import notify
        msg = (f"Robinhood sign-in is {int(days):.0f} days old (estimated ≤{days_left} days left). "
               f"Run: ./venv/bin/python robinhood_mcp.py --login")
        notify.send(msg, title="Robinhood sign-in renewal due")
        log.warning(msg)
    except Exception:       # noqa: BLE001 — never interrupt the refresh flow
        pass


def agentic_account(accounts) -> dict | None:
    """The one account with agentic_allowed=true, from a get_accounts result."""
    def _find_list(o):
        if isinstance(o, list):
            return o
        if isinstance(o, dict):
            if isinstance(o.get("accounts"), list):
                return o["accounts"]
            for v in o.values():
                r = _find_list(v)
                if r:
                    return r
        return []
    rows = _find_list(accounts)
    ok = [a for a in (rows or []) if isinstance(a, dict) and a.get("agentic_allowed") in (True, "true")]
    return ok[0] if len(ok) == 1 else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Robinhood Trading MCP connection (sign-in and read-only checks).")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="exchange the refresh token now")
    ap.add_argument("--quiet", action="store_true", help="suppress stdout when --refresh does nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        if args.login:
            accts = call("get_accounts", {}, interactive=True)
            a = agentic_account(accts)
            print("\nSigned in. Token stored at", TOKEN_FILE, "(readable only by you).")
            print("Agentic account:", (a or {}).get("account_number", "NOT FOUND — open one in the Robinhood app"))
            return 0
        if args.refresh:
            if not TOKEN_FILE.exists():
                return 0  # sign-in never done — no-op
            ok = refresh(force=False)
            if not ok:
                print("refresh failed — run --login")
                return 3
            _check_login_age()
            if not getattr(args, "quiet", False):
                print("token ok")
            return 0
        if args.tools:
            for t in list_tools():
                print(t["name"], json.dumps(t["schema"].get("required", [])))
            return 0
        if args.probe:
            accts = call("get_accounts", {})
            a = agentic_account(accts)
            if not a:
                print("No single agentic_allowed account found:", json.dumps(accts)[:500])
                return 1
            n = a.get("account_number")
            port, pos, q = calls([("get_portfolio", {"account_number": n}),
                                  ("get_equity_positions", {"account_number": n}),
                                  ("get_equity_quotes", {"symbols": ["SPY"]})])
            print("agentic account:", n)
            print("portfolio:", json.dumps(port)[:800])
            print("positions:", json.dumps(pos)[:800])
            print("SPY quote:", json.dumps(q)[:400])
            print("\nSet this in config/risk.yaml:\nrobinhood:\n  account_number: \"%s\"" % n)
            return 0
    except NeedsLogin as e:
        print(e)
        return 3
    except ModuleNotFoundError as e:
        print(f"{e}. Install the MCP client first: ./venv/bin/pip install -r requirements.txt")
        return 4
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
