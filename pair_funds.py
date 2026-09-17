"""
Five long/inverse ETF switching funds, searched, opened and stepped daily.

WHAT THESE ARE
--------------
Each fund holds exactly one of a bull/bear ETF pair at any moment — never both,
never cash. A momentum signal on the UNLEVERAGED index decides which leg. When
the signal flips the fund switches at the next open and pays the round trip.

**These are expected to underperform buy-and-hold on the index pairs.** That is
measured, not feared: over 2010-2019 S&P switching returned +6.8%/yr against
SPY's +13.3%, and across the 2020-2022 crash and bear it returned -4.1% against
+7.7%. It was opened anyway, deliberately, because the forward record is the one
measurement in this project with no survivorship bias and no look-ahead, and a
strategy nobody runs produces no evidence at all.

Energy is the exception worth watching: switching beat holding ERX by 10 points
in the bull window and 39 through the crash, then lost 37%/yr since 2023. Two
wins and a catastrophe is variance rather than an edge, and watching it forward
is how that question gets settled instead of argued.

WHY THE EQUITY CURVE IS RECOMPUTED, NOT ACCUMULATED
----------------------------------------------------
Each step replays the whole curve from the fund's start date rather than
advancing a stored position. Incremental state is where paper trading goes
quietly wrong — a missed day, a double-step, a partial write, and the ledger
drifts from what the rules actually produce, with nothing to compare against.
Replaying is idempotent by construction: run it five times, get the same answer.
The series are a few thousand bars, so it costs nothing worth saving.

Usage:
    python pair_funds.py --search        # best method per pair, no writes
    python pair_funds.py --open          # create the funds from that search
    python pair_funds.py --step          # mark every fund to the latest close
    python pair_funds.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import date

import costs as costs_mod
import storage
from erx_momentum import METHODS, random_null, run_switch
from pair_momentum import best_method, buy_and_hold, load_pair
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pairfunds")

# Five funds: two leverage levels on the S&P, the Nasdaq and Russell at 1x, and
# the energy pair that prompted all of this. Deliberately spans leverage, since
# the share of buy-and-hold a switcher captures falls as leverage rises.
FUNDS = [
    ("sp500_1x",  "S&P Switch 1x",     "SPY",  "SH",   "SPY"),
    ("sp500_2x",  "S&P Switch 2x",     "SSO",  "SDS",  "SPY"),
    ("nasdaq_1x", "Nasdaq Switch 1x",  "QQQ",  "PSQ",  "QQQ"),
    ("russell_1x", "Russell Switch 1x", "IWM", "RWM",  "IWM"),
    ("energy_2x", "Energy Switch 2x",  "ERX",  "ERY",  "XLE"),
]

SEARCH_WIN = ("2010-01-01", "2019-12-31")
START = "2026-09-15"   # funds open at the latest complete bar, not in the past


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pair_funds (
            name        TEXT PRIMARY KEY,
            label       TEXT NOT NULL,
            bull        TEXT NOT NULL,
            bear        TEXT NOT NULL,
            signal      TEXT NOT NULL,
            method      TEXT NOT NULL,
            param       INTEGER NOT NULL,
            min_hold    INTEGER NOT NULL,
            capital_usd REAL NOT NULL,
            started_on  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'open',
            search_note TEXT
        ) STRICT
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pair_fund_equity (
            name       TEXT NOT NULL,
            date       TEXT NOT NULL,
            equity_usd REAL NOT NULL,
            held       TEXT,
            switches   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (name, date)
        ) STRICT, WITHOUT ROWID
    """)
    conn.commit()


def search_all(conn, cfg) -> dict:
    """Best method per pair, each chosen on the search window only."""
    out = {}
    for name, label, bull, bear, sig in FUNDS:
        b = best_method(conn, cfg, bull, bear, sig, SEARCH_WIN)
        if not b:
            log.warning(f"{label}: insufficient data")
            continue
        out[name] = {"label": label, "bull": bull, "bear": bear, "signal": sig,
                     "method": b["method"], "param": b["param"],
                     "min_hold": b["min_hold"], "cagr": b["cagr"],
                     "bh": b["bh"], "null_p95": b["null"]["p95"],
                     "switches": b["n_switches"], "max_dd": b["max_dd"]}
        log.info(f"  {label:<20}{b['method']}({b['param']}) min_hold={b['min_hold']}"
                 f"  search CAGR {b['cagr']*100:+.2f}%  buy&hold {b['bh']*100:+.2f}%")
    return out


def open_funds(conn, cfg, capital: float = 100.0) -> None:
    init(conn)
    found = search_all(conn, cfg)
    for name, f in found.items():
        note = (f"chosen on {SEARCH_WIN[0]}..{SEARCH_WIN[1]}: CAGR "
                f"{f['cagr']*100:+.2f}% vs buy&hold {f['bh']*100:+.2f}% "
                f"vs null p95 {f['null_p95']*100:+.2f}%, maxDD {f['max_dd']*100:.1f}%")
        conn.execute("""INSERT OR REPLACE INTO pair_funds
            (name,label,bull,bear,signal,method,param,min_hold,capital_usd,
             started_on,status,search_note) VALUES (?,?,?,?,?,?,?,?,?,?,'open',?)""",
            (name, f["label"], f["bull"], f["bear"], f["signal"], f["method"],
             int(f["param"]), int(f["min_hold"]), capital, START, note))
    conn.commit()
    log.info(f"opened {len(found)} pair funds at ${capital:.2f} each, from {START}")


def step(conn, cfg) -> None:
    """
    Mark every open fund to the newest bar by replaying its whole curve.

    Replay rather than accumulate: see the module docstring. The consequence
    that matters is that a missed day self-heals — the next run produces the
    same curve it would have produced anyway.
    """
    init(conn)
    cm = costs_mod.CostModel(cfg)
    latest = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    for r in conn.execute("SELECT * FROM pair_funds WHERE status='open'"):
        w = load_pair(conn, r["bull"], r["bear"], r["signal"], r["started_on"], latest)
        if w.empty or len(w) < 2:
            log.info(f"  {r['label']}: no bars since {r['started_on']} yet")
            continue
        fn, _ = METHODS[r["method"]]
        # The signal needs history from BEFORE the fund opened, or its first
        # weeks are scored on a half-formed moving average. Loaded long, sliced
        # short: the curve still starts at started_on.
        warm = load_pair(conn, r["bull"], r["bear"], r["signal"],
                         "2005-01-01", latest)
        sig_full = fn(warm["close_XLE"], r["param"])
        res = run_switch(w, sig_full.reindex(w.index), cm,
                         capital=float(r["capital_usd"]), min_hold=int(r["min_hold"]))
        held = "?"
        try:
            held = r["bull"] if bool(sig_full.reindex(w.index).ffill().iloc[-2]) else r["bear"]
        except Exception:
            pass
        conn.execute("INSERT OR REPLACE INTO pair_fund_equity "
                     "(name,date,equity_usd,held,switches) VALUES (?,?,?,?,?)",
                     (r["name"], latest, float(res["final"]), held,
                      int(res["n_switches"])))
        pct = (res["final"] / float(r["capital_usd"]) - 1) * 100
        log.info(f"  {r['label']:<20}${res['final']:>7.2f}  {pct:+6.2f}%  "
                 f"holding {held}  switches {res['n_switches']}")
    conn.commit()


def rows(conn) -> list:
    init(conn)
    return [dict(r) for r in conn.execute("""
        SELECT f.name, f.label, f.bull, f.bear, f.method, f.param, f.min_hold,
               f.capital_usd, f.started_on, f.search_note,
               e.equity_usd, e.date, e.held, e.switches
        FROM pair_funds f
        LEFT JOIN pair_fund_equity e ON e.name = f.name
         AND e.date = (SELECT MAX(date) FROM pair_fund_equity e2 WHERE e2.name = f.name)
        WHERE f.status='open' ORDER BY f.name""")]


def render(conn) -> str:
    rs = rows(conn)
    if not rs:
        return "PAIR FUNDS  none open"
    L = [f"PAIR FUNDS  ({len(rs)} open, bull/bear ETF switching, simulated)"]
    for r in rs:
        cap = float(r["capital_usd"])
        eq = r["equity_usd"]
        if eq is None:
            L.append(f"    {r['label']:<20}   opened {r['started_on']}, not yet marked")
            continue
        pct = (eq / cap - 1) * 100
        L.append(f"    {r['label']:<20}{pct:>+7.2f}%  ${eq:>7.2f}  "
                 f"holding {r['held']}  {r['method']}({r['param']})")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--step", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--capital", type=float, default=100.0)
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)

    if a.search:
        found = search_all(conn, cfg)
        print(f"\n  BEST METHOD PER PAIR — chosen on {SEARCH_WIN[0]}..{SEARCH_WIN[1]}")
        print("  " + "-" * 82)
        print(f"  {'fund':<20}{'method':<16}{'CAGR':>9}{'buy&hold':>10}"
              f"{'null p95':>10}{'maxDD':>8}{'switch':>8}")
        for f in found.values():
            print(f"  {f['label']:<20}{f['method']+'('+str(f['param'])+')':<16}"
                  f"{f['cagr']*100:>8.2f}%{f['bh']*100:>9.2f}%"
                  f"{f['null_p95']*100:>9.2f}%{f['max_dd']*100:>7.1f}%{f['switches']:>8}")
    if a.open:
        open_funds(conn, cfg, a.capital)
    if a.step:
        step(conn, cfg)
    if a.report or not any((a.search, a.open, a.step)):
        print("\n" + render(conn))
    conn.close()


if __name__ == "__main__":
    main()
