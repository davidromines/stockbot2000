"""
Regression test for ranking.py and the slot selection built on it (the owner's
promotion process, 2026-09-24).

Pinned: a strategy starts at its backtest and every paper trade moves weight
to its forward record; a losing backtest is out (step 1), an absent backtest
starts neutral; DEMOTED strategies stay in the pool and can climb back; the
five slots fill with the best tradeable strategies on day one, with no
evidence floor; a strategy with no accounting row yet is not blocked; one with
no stop plan, a kill switch or broken accounting is; units are net return per
trade on both sides.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import killswitch
import ranking
import slots

FAILED = []
S = {"prior_trades": 10, "no_backtest_prior": 0.0}


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    # --- the score -----------------------------------------------------------
    check("day one: the backtest", ranking.score(0.01, None, 0, S) == 0.01)
    check("10 paper trades at the prior weight: halfway", abs(ranking.score(0.01, -0.01, 10, S)) < 1e-12)
    check("paper evidence dominates as it grows", ranking.score(0.01, -0.01, 90, S) < -0.007)
    check("no backtest: neutral start, paper decides",
          ranking.score(None, None, 0, S) == 0.0 and ranking.score(None, 0.02, 10, S) == 0.01)
    check("a losing backtest fails the gate", ranking.gate(-0.001)[0] is False and ranking.gate(0.0)[0] is False)
    check("no backtest is not a failure", ranking.gate(None)[0] is True)

    # --- forward units -------------------------------------------------------
    fw, n = ranking.forward_per_trade({"net_usd": 2.0, "capital_usd": 100, "closed_trades": 3,
                                       "open_positions": 2, "fund_kind": "paper"})
    check("paper fund: net per $20 per trade taken (closed + open)", n == 5 and abs(fw - 2.0 / (20 * 5)) < 1e-12)
    fw, n = ranking.forward_per_trade({"net_usd": 3.0, "capital_usd": 100, "closed_trades": 2,
                                       "fund_kind": "pair"})
    check("pair fund: the whole fund per trade, switches + the holding", n == 3 and abs(fw - 0.01) < 1e-12)
    check("no accounting yet: no forward evidence", ranking.forward_per_trade({"net_usd": None}) == (None, 0))

    # --- the pool keeps DEMOTED ---------------------------------------------
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE league_state (id INTEGER PRIMARY KEY, strategy_key TEXT, version INT, at TEXT, "
              "from_state TEXT, to_state TEXT, reason TEXT, actor TEXT)")
    for k, states in (("a", ["PAPER", "QUALIFIED", "DEMOTED"]), ("b", ["PAPER"]), ("c", ["PAPER", "REJECTED"])):
        for st in states:
            c.execute("INSERT INTO league_state (strategy_key, version, at, to_state, reason) VALUES (?,1,'t',?,'t')",
                      (k, st))
    got = sorted(k for k, _, _ in ranking.pool(c))
    check("DEMOTED stays in the pool (it can climb back); REJECTED does not", got == ["a", "b"], got)

    # --- pair funds: one family per index ----------------------------------
    import leagues
    import pair_funds
    pc = sqlite3.connect(":memory:")
    pair_funds.init(pc)
    for name, sig in (("sp500_1x", "SPY"), ("sp500_2x", "SPY"), ("nasdaq_1x", "QQQ"), ("russell_1x", "IWM"),
                      ("energy_2x", "XLE")):
        pc.execute("INSERT INTO pair_funds (name,label,bull,bear,signal,method,param,min_hold,capital_usd,"
                   "started_on) VALUES (?,?,?,?,?,'roc',5,1,100.0,'2026-09-15')", (name, name, "B", "S", sig))
    fams = {n: leagues.family_of(pc, f"pair:{n}") for n in ("sp500_1x", "sp500_2x", "nasdaq_1x", "russell_1x",
                                                          "energy_2x")}
    check("pair families split by index; S&P 1x and 2x share one",
          fams == {"sp500_1x": "pair_sp500", "sp500_2x": "pair_sp500", "nasdaq_1x": "pair_nasdaq",
                   "russell_1x": "pair_russell", "energy_2x": "pair_energy"}, fams)

    # --- slots fill from the ranking on day one -----------------------------
    def row(key, sc, fam, bt=0.01, recon=None, gate=True):
        return {"strategy_key": key, "version": 1, "name": key, "state": "PAPER", "family": fam,
                "league": "momentum", "backtest": bt, "forward": None, "forward_trades": 0, "score": sc,
                "passes_gate": gate, "gate": "ok" if gate else "backtest loses money net",
                "net_usd": None, "recon_status": recon, "as_of": None, "sessions": 0, "closed_trades": 0}
    rows = [row("s1", 0.030, "f1"), row("s2", 0.025, "f2"), row("nostop", 0.024, "f3"),
            row("s3", 0.020, "f4"), row("killed", 0.019, "f5"), row("badacct", 0.018, "f6", recon="ACCOUNTING_PROBLEM"),
            row("s4", 0.010, "f7", recon="NO_ACCOUNTING"), row("s5", 0.005, "f8"), row("s6", 0.001, "f9"),
            row("loser", 0.050, "f10", bt=-0.01, gate=False)]
    ranking.rank = lambda conn, cfg: rows
    slots.genome_for = lambda conn, k, v: None if k == "nostop" else {"risk": {"stop_atr_multiple": 2.0}}
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    c.execute("INSERT INTO prices VALUES ('SPY','2026-09-24',1)")
    slots.init(c)
    killswitch.init(c) if hasattr(killswitch, "init") else None
    real_halt = killswitch.strategy_halted
    killswitch.strategy_halted = lambda conn, k: "test" if k == "killed" else None
    a = slots.assess(c, {})
    elig = [r["strategy_key"] for r in a if r["eligible"]]
    check("eligible = tradeable, gate-passing, in score order", elig == ["s1", "s2", "s3", "s4", "s5", "s6"], elig)
    why = {r["strategy_key"]: r["reasons"][0] for r in a if not r["eligible"]}
    check("excluded for the reasons that protect money",
          "backtest loses" in why["loser"] and "stop plan" in why["nostop"] and "kill switch" in why["killed"]
          and "ACCOUNTING_PROBLEM" in why["badacct"], why)
    check("no accounting row yet does not block (day one)", "s4" in elig)
    p = slots.plan(c, {"slots": {"max_per_family": 4}})
    got = [r["strategy_key"] for _, r, _ in p["assign"]]
    check("all five slots filled on day one, best first", got == ["s1", "s2", "s3", "s4", "s5"] and not p["cash_slots"],
          (got, p["cash_slots"]))
    killswitch.strategy_halted = real_halt

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
