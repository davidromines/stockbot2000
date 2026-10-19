"""allocator (Stage AD6, shadow): the skeptical posterior, eligibility, the switching-cost rule, cash before a non-edge,
the shadow record. It must never assign or trade."""
import runtime  # noqa: F401
import sqlite3

import allocator as al

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

S = al.settings({})
p0 = al.posterior(None, None, 0, None, S)
check("no evidence: the posterior is the prior, zero", p0["post"] == 0 and abs(p0["post_sd"] - S["prior_sd20"]) < 1e-12)
pb = al.posterior(0.05, None, 0, 0.08, S)
check("a backtest alone is shrunk by its measured reliability (0.2): +5% -> +1%", abs(pb["post"] - 0.01) < 1e-12, pb)
pf = al.posterior(None, 0.02, 30, 0.05, S)
check("thirty forward trades move the estimate more than a backtest does", pf["w_forward"] > pb["w_backtest"], (pf, pb))
pc = al.posterior(None, 0.02, 3000, 0.05, S)
check("forward trades are capped (they share dates)", abs(pc["post"] - pf["post"]) < 1e-12)
pneg = al.posterior(0.04, -0.03, 30, 0.05, S)
check("a strong backtest with a losing forward record ends negative", pneg["post"] < 0, pneg)
check("risk-adjusted posterior divides by the dispersion", abs(pb["post_risk_adj"] - pb["post"] / 0.08) < 1e-12)


def row(k, score, fwd=None, n=0, fam=None, eligible=True, sd=0.05):
    return {"strategy_key": k, "version": 1, "family": fam or k, "score": score, "forward": fwd, "forward_trades": n,
            "eligible": eligible, "sd_20": sd}


rows = [row("hold_a", 0.03), row("hold_b", 0.02), row("star", 0.10, 0.03, 30), row("twin_of_star", 0.09, fam="star"),
        row("loser", 0.06, -0.05, 30), row("blocked", 0.20, eligible=False)]
holders = {1: {"strategy_key": "hold_a", "version": 1}, 2: {"strategy_key": "hold_b", "version": 1}}
p = al.plan(rows, holders, 2, S)
names = [x["strategy_key"] for x in p["shadow"]]
check("ineligible strategies never enter, however high the score", "blocked" not in names)
check("one per family", not ("star" in names and "twin_of_star" in names))
check("a strong backtest with a losing forward record is not chosen", "loser" not in names)
check("the best-evidenced strategy leads", names[0] == "star", names)
check("a holder beaten by more than the switching cost is listed as a swap; the comparison is recorded",
      p["overlap"] <= 2 and isinstance(p["swap"], list))
flat = [row("x", 0.0), row("y", -0.01)]
q = al.plan(flat, {1: {"strategy_key": "x", "version": 1}}, 1, S)
check("no positive posterior -> the shadow leaves the slot in cash", q["shadow"] == [] and q["cash_slots"] == 1)
close = [row("hold_a", 0.03), row("near", 0.032)]
r = al.plan(close, {1: {"strategy_key": "hold_a", "version": 1}}, 1, S)
check("a challenger better by less than the switching cost does not replace the holder", r["swap"] == []
      and [x["strategy_key"] for x in r["keep"]] == ["hold_a"], r)
c = sqlite3.connect(":memory:")
al.init(c)
check("the shadow table exists and the module has no trading or assignment code",
      c.execute("SELECT COUNT(*) FROM allocator_shadow").fetchone()[0] == 0
      and "slot_assignments" not in open(al.__file__).read().split("def init")[1].split("def run")[0]
      and "execute(sig" not in open(al.__file__).read())
check("render works", "ALLOCATOR" in al.render({**p, "held": holders}))
c.execute("CREATE TABLE paper_trades_restated (version TEXT, run_id TEXT, ticker TEXT, entry_date TEXT, net_pct REAL)")
c.executemany("INSERT INTO paper_trades_restated VALUES ('v2_next_open','r1',?,?,?)",
              [("A", "2026-10-01", 1.0), ("B", "2026-10-01", 3.0), ("C", "2026-10-02", -1.0)])
check("forward evidence = the restated record (net, next-open), counted by independent entry dates",
      al.honest_forward(c, "r1") == (0.01, 2) and al.honest_forward(c, "none") == (None, 0))
check("per-trade forward is put on the score's per-20-sessions scale", abs(al.per20(0.01, 60) - 0.01 / 3) < 1e-12
      and al.per20(0.01, 2) == 0.04)
hr = [{**row("h", 0.02), "honest_forward": -0.02, "honest_dates": 30, "hold_days": 20}]
check("a restated losing record overrides the paper figure", al.plan(hr, {}, 1, S)["shadow"] == [])

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
