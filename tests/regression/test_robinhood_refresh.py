"""robinhood_mcp.refresh: the stored token is renewed with its refresh token (10-01: the MCP client
never refreshed a stored token, and LIVE halted on NeedsLogin with a valid refresh token unused)."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import runtime  # noqa: F401,E402
import asyncio  # noqa: E402
import robinhood_mcp as rh  # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok:
        FAILED.append(name)


def main() -> int:
    d = tempfile.mkdtemp()
    st = rh.FileTokenStorage(Path(d) / "tok.json")
    sent = []

    def post_ok(data):
        sent.append(data)
        return 200, {"access_token": "A2", "token_type": "Bearer", "expires_in": 1000, "scope": "internal"}

    check("no tokens -> False, nothing sent", rh.refresh(storage=st, post=post_ok, url="u") is False and not sent)
    st._write({"client": {"client_id": "cid"},
               "tokens": {"access_token": "A1", "token_type": "Bearer", "expires_in": 1000, "refresh_token": "R1"}})
    check("token of unknown age is refreshed", rh.refresh(storage=st, post=post_ok, url="u") is True and len(sent) == 1)
    t = st._read()["tokens"]
    check("refresh grant carries refresh token and client id",
          sent[0]["grant_type"] == "refresh_token" and sent[0]["refresh_token"] == "R1" and sent[0]["client_id"] == "cid")
    check("new access token stored, refresh token kept when omitted",
          t["access_token"] == "A2" and t["refresh_token"] == "R1" and t.get("issued_at"))
    check("file stays mode 600", oct(os.stat(st.path).st_mode & 0o777) == "0o600")
    check("fresh token: no refresh, even forced within a minute",
          rh.refresh(storage=st, post=post_ok, url="u") and rh.refresh(True, "u", st, post_ok) and len(sent) == 1)
    d2 = st._read(); d2["tokens"]["issued_at"] = time.time() - 300; st._write(d2)
    check("past a quarter of its life: refreshed", rh.refresh(storage=st, post=post_ok, url="u") and len(sent) == 2)
    d2 = st._read(); d2["tokens"]["issued_at"] = time.time() - 120; st._write(d2)
    check("under a quarter of its life: not refreshed", rh.refresh(storage=st, post=post_ok, url="u") and len(sent) == 2)
    check("forced: refreshed", rh.refresh(True, "u", st, post_ok) and len(sent) == 3)
    d2 = st._read(); d2["tokens"]["issued_at"] = 0; st._write(d2)
    before = st._read()["tokens"]
    check("refused refresh -> False, tokens untouched",
          rh.refresh(True, "u", st, lambda data: (400, "invalid_grant")) is False and st._read()["tokens"] == before)
    # 10-19: refresh() erased the login stamp, so the renewal warning could never fire.
    d2 = st._read(); d2["tokens"]["login_at"] = 1_000_000.0; d2["tokens"]["issued_at"] = 0; st._write(d2)
    check("a refresh keeps the last full-login stamp", rh.refresh(True, "u", st, post_ok)
          and st._read()["tokens"].get("login_at") == 1_000_000.0)
    check("login_at reads the token record's stamp first", rh.login_at(st, Path(d) / "none.txt") == 1_000_000.0)
    seed = Path(d) / "seed.txt"; seed.write_text("2026-10-05T00:50:00Z  last known --login\n")
    d2 = st._read(); d2["tokens"].pop("login_at"); st._write(d2)
    check("without a stamp, login_at falls back to the seed file",
          abs(rh.login_at(st, seed) - 1791161400.0) < 1)
    check("no stamp and no seed: unknown (0), and no warning", rh.login_at(st, Path(d) / "none.txt") == 0.0
          and rh.login_age_message(0.0) is None)
    now = 1791161400.0
    check("no warning before 20 days", rh.login_age_message(now, now + 19 * 86400) is None)
    m = rh.login_age_message(now, now + 22 * 86400)
    check("warning from 20 days, with the days left and the fix", m and "22 days old" in m and "≤8 days left" in m
          and "--login" in m)
    import notify
    check("the alert uses a notify function that exists", hasattr(notify, "notify") and callable(notify.notify))
    tok = asyncio.run(st.get_tokens())
    check("get_tokens strips issued_at for the MCP client", tok.access_token == "A2" and not hasattr(tok, "issued_at")
          or "issued_at" not in tok.model_dump())
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
