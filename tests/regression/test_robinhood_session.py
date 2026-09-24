"""
Regression test for robinhood_mcp.session() — one MCP session per run
(roadmap step 4). A fake MCP server; no network.

Pinned: every call inside the block goes through ONE opened session, including
calls made by robinhood_live and market_caps through rh.call / rh.calls; a
tool error reaches the caller as RobinhoodError and the session carries on; an
expired sign-in at open time raises NeedsLogin (the trader halts and alerts);
a session that dies mid-run fails the in-flight call and later calls fall back
to their own sessions; a stuck call times out and does not block the calls
behind it; the previous state is restored on exit.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import asyncio
import contextlib
import os
import sqlite3
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import robinhood_mcp as rh

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


class FakeServer:
    """An MCP 'server': counts sessions opened and tool calls made."""

    def __init__(self, die_after=None, hang_on=None, fail_open=None):
        self.opened, self.calls, self.die_after, self.hang_on, self.fail_open = 0, [], die_after, hang_on, fail_open

    def opener(self):
        srv = self

        @contextlib.asynccontextmanager
        async def _cm():
            if srv.fail_open:
                raise ExceptionGroup("tg", [srv.fail_open])   # how anyio wraps it
            srv.opened += 1

            class S:
                async def call_tool(self, tool, args):
                    srv.calls.append(tool)
                    if srv.hang_on == tool:
                        await asyncio.sleep(3600)
                    if srv.die_after is not None and len(srv.calls) > srv.die_after:
                        raise asyncio.CancelledError()         # the transport went away
                    if tool == "bad_tool":
                        return SimpleNamespace(isError=True, content=[SimpleNamespace(text="no such tool")])
                    if tool == "get_portfolio":
                        return SimpleNamespace(isError=False, structuredContent={
                            "data": {"total_value": "88.10", "buying_power": {"buying_power": "19.26"}}})
                    return SimpleNamespace(isError=False, structuredContent={"tool": tool, "args": args})
            yield S()
        return _cm()


def main():
    per_call = []
    rh._session_do = lambda url, interactive, fn: per_call.append(1) or asyncio.sleep(0, result=["fallback"])
    rh.settings = lambda: {"mcp_url": "https://fake", "account_number": "1"}

    srv = FakeServer()
    with rh.session(opener=srv.opener) as s:
        r = [rh.call("get_equity_quotes", {"symbols": [x]}) for x in ("A", "B", "C")]
        r += rh.calls([("get_portfolio", {}), ("get_equity_positions", {})])
        import robinhood_live
        c = sqlite3.connect(":memory:")
        bp = robinhood_live.LiveBroker(c, "1").get_buying_power()
        try:
            rh.call("bad_tool", {})
            err = None
        except rh.RobinhoodError as e:
            err = e
        after = rh.call("get_equity_quotes", {"symbols": ["D"]})
        n = s.calls_made
    check("8 calls, ONE session opened", srv.opened == 1 and len(srv.calls) == 8 and not per_call, (srv.opened, srv.calls))
    check("results parsed as before", r[0] == {"tool": "get_equity_quotes", "args": {"symbols": ["A"]}})
    check("robinhood_live reads through the shared session", bp == 19.26, bp)
    check("a tool error reaches the caller as RobinhoodError", err is not None and "no such tool" in str(err))
    check("and the session carries on after it", after["args"] == {"symbols": ["D"]} and n == 8)
    check("after the block, nothing is active", rh._live_session() is None)
    rh.call("get_accounts", {})
    check("outside a session: one session per call, as before", per_call == [1])

    per_call.clear()
    try:
        with rh.session(opener=FakeServer(fail_open=rh.NeedsLogin("expired")).opener):
            pass
        check("expired sign-in at open raises NeedsLogin", False)
    except rh.NeedsLogin:
        check("expired sign-in at open raises NeedsLogin (unwrapped from the task group)", True)
    check("... and leaves nothing active", rh._live_session() is None)

    srv = FakeServer(die_after=2)
    with rh.session(opener=srv.opener):
        rh.call("a", {}); rh.call("b", {})
        try:
            rh.call("c", {})
            died = False
        except BaseException:                                  # noqa: BLE001
            died = True
        fb = rh.call("d", {})
    check("session dies mid-run: the in-flight call fails (never a fake result)", died)
    check("later calls fall back to their own sessions", fb == "fallback" and per_call == [1], (fb, per_call))

    per_call.clear()
    rh.CALL_TIMEOUT = 0.5
    srv = FakeServer(hang_on="get_equity_orders")
    with rh.session(opener=srv.opener):
        try:
            rh.call("get_equity_orders", {})
            timed_out = False
        except TimeoutError:
            timed_out = True
        fb = rh.call("get_portfolio", {})
    check("a stuck call times out (a transport failure to the caller)", timed_out)
    check("and does not block the calls behind it", fb == "fallback", fb)

    srv1, srv2 = FakeServer(), FakeServer()
    with rh.session(opener=srv1.opener) as outer:
        with rh.session(opener=srv2.opener) as inner:
            check("nested: the inner session is active", rh._live_session() is inner)
        check("nested: the outer one is restored", rh._live_session() is outer)

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
