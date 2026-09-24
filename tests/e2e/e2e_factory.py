"""
Phase 13 H15 + Addendum A I14 (SIMULATION -> SHADOW): the whole machine, end to
end, on real market data in a throwaway database.

Why a fixture database: the pipeline writes lifecycle decisions, metrics and
paper runs. Run against market_data.db, a test would put invented strategies
into the forward record — the one measurement this project cannot afford to
contaminate. So this copies a slice of the REAL data (the most liquid ~120
common stocks + SPY, 2015-06 to 2023-06, prices / features / symbols /
daily_fundamentals) into a temp file and runs everything there:

  1. strategy_factory.generate for four representative families: momentum,
     mean reversion, a fundamental combo, and one whose data does not exist
  2. discovery.plan + factory_pipeline.run  (backtest, robustness, validation,
     rejection with a failure record, or enrolment in paper trading)
  3. leagues.standings, factory_report      (no forward evidence -> nothing ranked)
  4. slots.plan                              (-> every slot in CASH, B6)
  5. forward evidence is then GIVEN to one PAPER strategy (fund_accounting +
     paper_equity), and the chain continues: evaluate_forward -> QUALIFIED ->
     LIVE_CANDIDATE -> slots.apply -> slot_trader.trade (SIMULATION, injected
     quotes) -> a stop exit -> SHADOW run places nothing
  6. the global switch (env var, never data/KILL_SWITCH) flattens the slot

It is NOT collected by run_tests.sh (heavy: ~a minute, ~1-2 GB). Run it with:

    ./run_bounded.sh ./venv/bin/python tests/e2e/e2e_factory.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

import runtime  # noqa: F401,E402  — must precede numpy/pandas
import sqlite3  # noqa: E402
import tempfile  # noqa: E402

import accounting
import discovery
import factory_pipeline as fp
import factory_report
import league
import leagues
import paper_trading
import quotes as qt
import slot_trader as st
import slots
import strategy_factory as sf
import strategy_objects as so
from universe import load_config

FAILED = []
FAMILIES = ("xs_momentum", "rsi_reversion", "value_quality", "dividend")


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def build_fixture(src_path: str, dst_path: str, n: int = 120) -> None:
    c = sqlite3.connect(dst_path)
    c.execute(f"ATTACH DATABASE 'file:{src_path}?mode=ro' AS src")
    for t in ("prices", "features", "symbols", "daily_fundamentals"):
        sql = c.execute("SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0]
        c.execute(sql)
    c.execute("""CREATE TEMP TABLE pick AS
                 SELECT f.ticker FROM src.features f JOIN src.symbols s ON s.ticker=f.ticker
                 WHERE f.date BETWEEN '2016-01-01' AND '2016-03-31' AND s.security_type='common_stock'
                   AND COALESCE(s.data_quality,'') = ''
                 GROUP BY f.ticker ORDER BY AVG(f.dollar_volume_20) DESC LIMIT ?""", (n,))
    c.execute("INSERT INTO temp.pick VALUES ('SPY')")
    lo, hi = "2015-06-01", "2023-06-30"
    c.execute("INSERT INTO prices SELECT * FROM src.prices WHERE ticker IN (SELECT ticker FROM temp.pick) "
              "AND date BETWEEN ? AND ?", (lo, hi))
    c.execute("INSERT INTO features SELECT * FROM src.features WHERE ticker IN (SELECT ticker FROM temp.pick) "
              "AND date BETWEEN ? AND ?", (lo, hi))
    c.execute("INSERT INTO daily_fundamentals SELECT * FROM src.daily_fundamentals WHERE ticker IN "
              "(SELECT ticker FROM temp.pick) AND date BETWEEN ? AND ?", (lo, hi))
    c.execute("INSERT INTO symbols SELECT * FROM src.symbols WHERE ticker IN (SELECT ticker FROM temp.pick)")
    c.commit()
    c.execute("DETACH DATABASE src")
    for t in ("prices", "features", "daily_fundamentals"):
        c.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_td ON {t}(ticker, date)")
        c.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_d ON {t}(date)")
    c.commit()
    c.close()


def main() -> int:
    cfg = load_config()
    src = cfg["database"]["market_data_path"]
    tmp = tempfile.mkdtemp(prefix="stockbot_e2e_")
    db = os.path.join(tmp, "e2e.db")
    build_fixture(src, db)
    conn = sqlite3.connect(db, timeout=60)
    conn.row_factory = sqlite3.Row
    n_tickers = conn.execute("SELECT COUNT(DISTINCT ticker) FROM prices").fetchone()[0]
    check("fixture built from real data", n_tickers > 50, n_tickers)

    # 1. templates
    for fam in FAMILIES:
        sf.generate(conn, cfg, only=fam)
    fams = {r[0] for r in conn.execute("SELECT DISTINCT family FROM strategy_meta")}
    check("four families registered", len(fams) == 4, fams)

    # 2. the pipeline, budget 4 — at most two per family per run
    summary = fp.run(conn, cfg, budget=4)
    ends = summary["processed"]
    print("  ends:", ends)
    check("pipeline processed its budget", 1 <= len(ends) <= 4, ends)
    legal = {league.REJECTED, league.PAPER, league.DISCOVERED, league.SPECIFIED, "ERROR"}
    check("every processed strategy ended in a legal state", set(ends.values()) <= legal, ends)
    check("no pipeline errors", "ERROR" not in ends.values(), ends)
    bt = conn.execute("SELECT COUNT(*) FROM strategy_metrics WHERE phase='backtest'").fetchone()[0]
    check("backtest metrics recorded with a survivorship tag",
          bt > 0 and conn.execute("SELECT COUNT(*) FROM strategy_metrics WHERE phase='backtest' AND "
                                  "survivorship_status='SURVIVORSHIP_LIMITED'").fetchone()[0] == bt, bt)
    rej = [k for k, v in ends.items() if v == league.REJECTED]
    if rej:
        n = conn.execute("SELECT COUNT(*) FROM failure_log").fetchone()[0]
        check("every rejection has a failure record", n >= len(rej), (n, rej))
    # Data-less family: never tested, recorded as DATA_PROBLEM, not dropped.
    discovery.plan(conn, cfg)
    blocked = conn.execute("SELECT COUNT(*) FROM research_queue WHERE family='dividend' AND status='blocked'"
                           ).fetchone()[0]
    check("data-less family blocked in the queue, not dropped", blocked >= 1, blocked)

    # 3-4. no forward evidence yet: nothing ranked, every slot in cash
    st_ = leagues.standings(conn, cfg)
    tiers = {r["tier"] for rows in st_.values() for r in rows}
    check("no forward evidence -> nothing eligible", tiers <= {"INSUFFICIENT_SAMPLE"}, tiers)
    rep = factory_report.daily_report(conn, days=1)
    check("factory report builds", "discovery" in rep and "accounting" in rep)
    p = slots.plan(conn, cfg)
    check("every slot in CASH without forward evidence (B6)", p["cash_slots"] == [1, 2, 3, 4, 5], p["cash_slots"])

    # 5. give ONE strategy forward evidence and follow the chain to a slot.
    paper = [(k, v) for k, v in so.in_state(conn, league.PAPER)]
    if not paper:
        # Nothing survived honestly on this slice: walk one strategy through the
        # allowed chain by hand so the downstream half is still exercised.
        k, v = next((r[0], r[1]) for r in conn.execute(
            "SELECT strategy_key, version FROM strategy_meta WHERE family='xs_momentum' LIMIT 1"))
        cur = league.canonical(league.state(conn, k, v))
        for s_ in (league.SPECIFIED, league.BACKTESTED, league.VALIDATED, league.PROMISING):
            if cur in (league.DISCOVERED, league.SPECIFIED, league.BACKTESTED, league.VALIDATED):
                so.decide(conn, k, v, "PROMOTE", "e2e fixture walk", to_state=s_)
                cur = s_
        fp.enroll(conn, cfg, k, v, so.meta(conn, k, v), so.genome(conn, k, v))
        paper = [(k, v)]
        print("  note  no strategy survived on the slice; one was walked to PAPER by hand")
    k, v = paper[0]
    run_id = leagues.fund_ref(conn, k, v)[1]
    accounting.init(conn)
    dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM prices WHERE ticker='SPY' "
                                        "ORDER BY date DESC LIMIT 25")][::-1]
    for i, d in enumerate(dates):
        conn.execute("INSERT OR REPLACE INTO paper_equity (run_id, date, cash_usd, positions_usd, equity_usd, "
                     "open_positions) VALUES (?,?,?,?,?,?)", (run_id, d, 50, 50 + i * 0.3, 100 + i * 0.3, 2))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(fund_accounting)")]
    row = {c: 0 for c in cols}
    row.update(equity_original=107.2, equity_restated=107.2, open_positions=2, cost_basis=50.0, note="e2e")
    row.update(as_of=dates[-1], fund_kind="paper", fund_id=run_id, label="e2e", capital_usd=100.0,
               gross_usd=8.0, costs_realized=0.5, costs_open=0.3, costs_usd=0.8, net_usd=7.2,
               closed_trades=12, recon_status="RECONCILED", reconciled=1, accounting_version=1,
               computed_at="2099-01-01T00:00:00")
    conn.execute(f"INSERT INTO fund_accounting ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 [row[c] for c in cols])
    conn.commit()
    moved = fp.evaluate_forward(conn, cfg)
    check("forward evidence qualifies the strategy", moved["qualified"] >= 1, moved)
    check("QUALIFIED -> LIVE_CANDIDATE (one per family)",
          league.canonical(league.state(conn, k, v)) == league.LIVE_CANDIDATE, league.state(conn, k, v))
    r = slots.apply(conn, cfg, "SIMULATION")
    check("the candidate takes a slot; the rest stay cash", r["assigned"] == 1 and len(r["cash_slots"]) == 4, r)
    check("SIMULATION assignment does not make it LIVE",
          league.canonical(league.state(conn, k, v)) == league.LIVE_CANDIDATE)

    import pandas as pd
    paper_trading._genome_signals = lambda c_, cfg_, g: (pd.DataFrame({"ticker": ["AAPL", "MSFT"]}), set())
    conn.execute("INSERT OR IGNORE INTO features (ticker, date, atr_14, dollar_volume_20) VALUES "
                 "('AAPL', '2023-06-30', 2.0, 5e9)")
    conn.commit()
    res = st.trade(conn, cfg, "SIMULATION", qt.FixedQuotes({"AAPL": 50.0, "MSFT": 60.0}))
    check("slot trader opens the slot's first position", any(x["action"] == "BUY" and x["status"] == "filled"
                                                             for x in res), res)
    res = st.monitor(conn, cfg, "SIMULATION", qt.FixedQuotes({"AAPL": 30.0}))
    check("a breached stop closes it", any(x["action"] == "CLOSE" and x["status"] == "filled" for x in res), res)
    pnl = st.pnl(conn, cfg, "SIMULATION")
    check("slot P&L reported gross / costs / net", pnl["closed_trades"] == 1 and pnl["gross_usd"] < 0, pnl)
    res = st.trade(conn, cfg, "SHADOW", qt.FixedQuotes({"AAPL": 50.0, "MSFT": 60.0}))
    check("SHADOW run approves and places nothing",
          any(x["status"] == "shadow" for x in res) and not st.open_positions(conn, "SHADOW"), res)

    # 6. the global switch — the env var, never the real data/KILL_SWITCH file
    import notify
    notify.notify = lambda *a, **k: []
    # A fresh decision: the same symbol in the same session is (correctly) a
    # duplicate, so clear this session's slot ledger first, as the unit test does.
    for t in ("signals", "orders", "slot_trades"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    st.trade(conn, cfg, "SIMULATION", qt.FixedQuotes({"AAPL": 51.0, "MSFT": 60.0}))
    had = len(st.open_positions(conn, "SIMULATION"))
    os.environ["TRADING_ENABLED"] = "false"
    try:
        st.monitor(conn, cfg, "SIMULATION", qt.FixedQuotes({"AAPL": 51.0}))
        check("kill switch flattens the slot", had == 1 and not st.open_positions(conn, "SIMULATION"), had)
    finally:
        os.environ.pop("TRADING_ENABLED", None)

    print(st.report(conn, cfg, "SIMULATION"))
    conn.close()
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}   (fixture kept at {db})")
        return 1
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
