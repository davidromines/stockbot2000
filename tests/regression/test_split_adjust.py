"""slot_trader.split_adjust (LIVE split handler): a confirmed forward or reverse split restates the slot position on the
new basis before any stop is checked; anything unconfirmed or not a clean ratio is left to reconciliation; live_pnl
reads the restatement as one continuing position, not a trade."""
import runtime  # noqa: F401
import json
import sqlite3

import live_pnl
import slot_trader as st

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)


class Broker:
    def __init__(self, q): self.q = q
    def get_positions(self): return {s: {"quantity": v} for s, v in self.q.items()}


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    st.init(c)
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    for d in ("2026-10-01", "2026-10-02", "2026-10-05"):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1)", (d,))
    plan = json.dumps([{"type": "atr", "atr_multiple": 3.0}, {"type": "time", "max_hold_days": 21}])
    c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, atr, "
              "stop_plan, reason, signal_id) VALUES ('2026-10-01T13:35:00+00:00','LIVE',1,'fx_a',1,'AAA','OPEN',0.4,100.0,"
              "4.0,?,'entry rule of fx_b v1 (stand-in for fx_a)','s1')", (plan,))
    c.commit()
    return c


c = db()
done = st.split_adjust(c, Broker({"AAA": 0.8}), "LIVE", {}, splits_fn=lambda s, since: [("2026-10-03", 2.0)])
pos = st.open_positions(c, "LIVE")[1]
check("a confirmed 2-for-1 split is restated", done == [("AAA", 2)], done)
check("...on the new basis: 0.8 shares at 50, ATR 2", (pos["quantity"], pos["price"], pos["atr"]) == (0.8, 50.0, 2.0), dict(pos))
tl = [r for r in pos["stop_plan"] if r["type"] == "time"][0]["max_hold_days"]
check("the time limit keeps the sessions already held (21 - 3 = 18)", tl == 18, tl)
check("the stand-in link survives (its reason is kept)", st._belongs(pos, {"strategy_key": "fx_a", "version": 9}))
check("the broker now reconciles, and to the share", st.reconcile(c, Broker({"AAA": 0.8}), "LIVE")[0]
      and abs(st.open_positions(c, "LIVE")[1]["quantity"] - 0.8) < 1e-12)
check("running it again changes nothing", st.split_adjust(c, Broker({"AAA": 0.8}), "LIVE", {},
                                                           splits_fn=lambda s, since: [("2026-10-03", 2.0)]) == [])
lp = live_pnl.compute(c, {"costs": {}}, "LIVE")
check("live_pnl: no closed trade, one open position that keeps its original opening time",
      lp["closed"] == [] and len(lp["open"]) == 1 and lp["open"][0]["opened"].startswith("2026-10-01")
      and lp["open"][0]["entry"] == 50.0, lp)

# a real exit after the restatement: one trade, +10% on either basis, opened on the original date, in every consumer
import digest
import eod_report
import live_attribution
import live_feedback
import ranking
from datetime import datetime, timedelta, timezone
exit_at = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(timespec="seconds")   # after the restatement
c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, reason, "
          "signal_id) VALUES (?,'LIVE',1,'fx_a',1,'AAA','CLOSE',0.8,55.0,'stop_loss','s2')", (exit_at,))
c.commit()
lp = live_pnl.compute(c, {"costs": {}}, "LIVE")
check("live_pnl: one closed trade, +10%, opened 10-01", len(lp["closed"]) == 1 and abs(lp["closed"][0]["ret_pct"] - 10) < 1e-9
      and lp["closed"][0]["opened"].startswith("2026-10-01") and abs(lp["closed"][0]["gross"] - 4.0) < 1e-9, lp["closed"])
m, n = ranking.live_per_trade(c, "fx_a", 1)
check("ranking: one live trade at +10%", n == 1 and abs(m - 0.10) < 1e-9, (m, n))
at = live_attribution.trades(c, "LIVE")
check("attribution: one row, entry 50, entry date 10-01", len(at) == 1 and at.iloc[0]["entry"] == 50.0
      and at.iloc[0]["entry_date"] == "2026-10-01", at.to_dict("records"))
rt = live_feedback.round_trips(c, "LIVE")
check("feedback: one round trip opened 10-01 at +10%", len(rt) == 1 and rt[0]["opened"].startswith("2026-10-01")
      and abs(rt[0]["gross_return"] - 0.10) < 1e-9, rt)
check("feedback: the restatement rows are not fills (2 fills: the buy and the exit)",
      len(live_feedback.trades(c, "LIVE")) == 2, live_feedback.trades(c, "LIVE"))
g, k = eod_report._realized_gross(c, exit_at[:10], "LIVE")
check("EOD: the exit day books one trade, +$4.00 (the same-day restatement is not a trade)", k == 1 and abs(g - 4.0) < 1e-9,
      (g, k))
d = digest._collect_live(c, "2026-10-01T00:00:00")
check("digest: one closed trade, +$4.00", d["closed"] == 1 and abs(d["net_usd"] - 4.0) < 1e-9, d)

c2 = db()
check("an unconfirmed ratio is left alone (reconciliation decides)",
      st.split_adjust(c2, Broker({"AAA": 0.8}), "LIVE", {}, splits_fn=lambda s, since: []) == []
      and st.open_positions(c2, "LIVE")[1]["quantity"] == 0.4)
check("a split of another ratio does not confirm", st.split_adjust(c2, Broker({"AAA": 0.8}), "LIVE", {},
                                                                   splits_fn=lambda s, since: [("2026-10-03", 3.0)]) == [])
check("hand-placed extra shares (not a clean ratio) are not mistaken for a split",
      st.split_adjust(c2, Broker({"AAA": 0.65}), "LIVE", {}, splits_fn=lambda s, since: [("2026-10-03", 2.0)]) == [])
c3 = db()
st.split_adjust(c3, Broker({"AAA": 0.04}), "LIVE", {}, splits_fn=lambda s, since: [("2026-10-03", 0.1)])
p3 = st.open_positions(c3, "LIVE")[1]
check("a confirmed 1-for-10 reverse split: 0.04 shares at 1,000", (round(p3["quantity"], 9), round(p3["price"], 6))
      == (0.04, 1000.0), dict(p3))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
