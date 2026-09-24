"""
The connection from this VM to Robinhood's Trading MCP — the transport under
the LIVE broker. Addendum A §16, §23-24; Addendum B §B13-B14.

    https://agent.robinhood.com/mcp/trading      (config/risk.yaml robinhood.mcp_url)

Authorisation is Robinhood's OAuth. It is done ONCE, by the account owner, on a
desktop device with the Robinhood app's verification step; this program never
sees a password. The resulting tokens are stored OUTSIDE the repository, in a
file readable only by this Linux user:

    ~/.config/stockbot2000/robinhood_oauth.json      (mode 600)

Refresh is automatic while the refresh token is valid. When it is not, every
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
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("robinhood_mcp")

DEFAULT_URL = "https://agent.robinhood.com/mcp/trading"
TOKEN_FILE = Path(os.path.expanduser("~/.config/stockbot2000/robinhood_oauth.json"))
# The browser is sent here after consent. Nothing needs to be listening: the
# owner copies the address the browser lands on (it contains the one-time code)
# and pastes it back into the --login prompt. That works whether the browser is
# on this VM or on a laptop.
REDIRECT_URI = "http://localhost:8765/callback"


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
        t = self._read().get("tokens")
        return OAuthToken.model_validate(t) if t else None

    async def set_tokens(self, tokens) -> None:
        d = self._read()
        d["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self._write(d)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull
        c = self._read().get("client")
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def set_client_info(self, info) -> None:
        d = self._read()
        d["client"] = info.model_dump(mode="json", exclude_none=True)
        self._write(d)


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


async def _session_do(url: str, interactive: bool, fn):
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with httpx2.AsyncClient(auth=_provider(url, interactive), timeout=30.0) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                return await fn(session)


def calls(batch: list, interactive: bool = False, url: str | None = None) -> list:
    """Run several (tool, args) calls in ONE authenticated session. Returns their parsed results."""
    url = url or settings()["mcp_url"]

    async def run(session):
        out = []
        for tool, args in batch:
            out.append(_parse(await session.call_tool(tool, args or {})))
        return out
    try:
        return asyncio.run(_session_do(url, interactive, run))
    except NeedsLogin:
        raise
    except BaseException as e:                               # noqa: BLE001 — surface nested task errors
        inner = getattr(e, "exceptions", None)
        if inner:
            for x in inner:
                if isinstance(x, (NeedsLogin, RobinhoodError)):
                    raise x
        raise


def call(tool: str, args: dict | None = None, interactive: bool = False) -> object:
    return calls([(tool, args or {})], interactive=interactive)[0]


def list_tools(interactive: bool = False) -> list:
    async def run(session):
        r = await session.list_tools()
        return [{"name": t.name, "schema": t.inputSchema} for t in r.tools]
    return asyncio.run(_session_do(settings()["mcp_url"], interactive, run))


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
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        if args.login:
            accts = call("get_accounts", {}, interactive=True)
            a = agentic_account(accts)
            print("\nSigned in. Token stored at", TOKEN_FILE, "(readable only by you).")
            print("Agentic account:", (a or {}).get("account_number", "NOT FOUND — open one in the Robinhood app"))
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
