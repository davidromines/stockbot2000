"""
The crypto paper fund. Phase 12, item 40.

WHAT IT IS
----------
A paper fund, modelled on `value_fund.py`: its own tables, its own stepper, its
own forward record, NOT folded into the equity league. A 24/7 instrument ranked
on a scoreboard calibrated for equity sessions would be comparing quantities
that are not alike.

It runs a registered strategy — by default the grid-DCA genome recorded in the
research library as `social:sets_machine` — FORWARD, from the day it opened.
That strategy loses to its null after fees in the backtest (0 of 10 symbols).
It is run anyway for the same reason the pair funds were opened after their
backtests failed: the forward record is the only measurement in this project
with no survivorship bias and no look-ahead, and a strategy nobody runs
produces no evidence at all.

ONE ENGINE, NOT TWO
-------------------
Every trade comes from `crypto_grid.simulate()`, the same function the
backtest calls. The fund does not reimplement the strategy, so the forward
record and the backtest cannot drift apart through two implementations of one
rule — the reason `costs.py` is shared on the equity side.

HOW A STEP WORKS — DETERMINISTIC REPLAY
-----------------------------------------
Each step replays every symbol from the fund's start to the newest CLOSED bar
and records what the engine produced. Closed trades are keyed by
(symbol, entry_time), so re-running a step changes nothing — idempotent by
construction rather than by bookkeeping. A trade still running off the end of
the data is held as OPEN, never closed at the last bar: a fund must not book a
fill that never happened.

Only bars whose close came after the fund opened can signal. Everything before
that is history the lookback reads, never an entry — otherwise the "forward"
record would contain trades decided on data the fund existed after.

Capital is split evenly across pairs trading when the fund opened. A pair that
had already been delisted then is excluded rather than given capital it could
never deploy.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import numpy as np

import crypto_benchmark as cb
import crypto_data as cd
import crypto_grid as cg
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cfund")

FUND = "crypto_paper_fund"
INTERVAL = "1h"


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_fund (
            name        TEXT PRIMARY KEY,
            capital_usd REAL NOT NULL,
            started_ts  INTEGER NOT NULL,
            interval    TEXT NOT NULL,
            strategy    TEXT NOT NULL,
            library_ref TEXT,
            symbols     TEXT NOT NULL,
            status      TEXT NOT NULL,
            last_step   TEXT,
            created_at  TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_fund_trades (
            name        TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            entry_ts    INTEGER NOT NULL,
            exit_ts     INTEGER NOT NULL,
            reason      TEXT NOT NULL,
            levels      INTEGER,
            deployed_usd REAL, gross_usd REAL, fees_usd REAL, net_usd REAL,
            ret_pct     REAL,
            null_pct    REAL,
            PRIMARY KEY (name, symbol, entry_ts)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_fund_open (
            name        TEXT NOT NULL,
            symbol      TEXT NOT NULL,
            entry_ts    INTEGER NOT NULL,
            state       TEXT NOT NULL,
            PRIMARY KEY (name, symbol)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_fund_equity (
            name        TEXT NOT NULL,
            date        TEXT NOT NULL,
            equity_usd  REAL NOT NULL,
            realised_usd REAL, unrealised_usd REAL,
            open_positions INTEGER,
            PRIMARY KEY (name, date)
        )
    """)
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_fund(conn, capital: float = 100.0, genome: dict | None = None,
              started_ts: int | None = None) -> dict:
    init(conn)
    if conn.execute("SELECT 1 FROM crypto_fund WHERE name=?", (FUND,)).fetchone():
        raise SystemExit(f"{FUND} already exists. A forward record is only worth "
                         f"what its start date says, so it is never reopened.")
    g = {**cg.DEFAULT, **(genome or {})}
    # Start at the newest CLOSED bar, so the first possible signal is the next
    # bar to close after opening.
    last = conn.execute("SELECT MAX(open_time) FROM crypto_prices WHERE interval=?",
                        (INTERVAL,)).fetchone()[0]
    if last is None:
        raise SystemExit("no crypto bars — run crypto_data.py --load first")
    # The first bar that can signal is the one OPENING after the newest bar
    # already closed — so no entry is decided on data from before the fund.
    start = started_ts or int(last) + cd.INTERVAL_SECONDS[INTERVAL]
    online = [r[0] for r in conn.execute("""
        SELECT l.symbol FROM crypto_listings l
        WHERE l.status='online' AND l.trading_disabled=0
          AND EXISTS (SELECT 1 FROM crypto_prices p WHERE p.symbol=l.symbol
                      AND p.interval=?) ORDER BY l.symbol""", (INTERVAL,))]
    if not online:
        raise SystemExit("no online pairs recorded — run crypto_data.py --status")
    conn.execute("""INSERT INTO crypto_fund (name, capital_usd, started_ts,
        interval, strategy, library_ref, symbols, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (FUND, capital, start, INTERVAL, json.dumps(g, sort_keys=True),
         "social:sets_machine", json.dumps(online), "open", _now_iso()))
    conn.commit()
    return {"name": FUND, "capital": capital, "started_ts": start,
            "symbols": online, "genome": g}


def _fund(conn) -> dict | None:
    r = conn.execute("SELECT * FROM crypto_fund WHERE name=?", (FUND,)).fetchone()
    return dict(r) if r else None


def step(conn) -> dict:
    """Replay every symbol from the fund's start and record the result."""
    init(conn)
    f = _fund(conn)
    if not f:
        return {"stepped": False, "reason": "no crypto fund — run --open"}
    g = json.loads(f["strategy"])
    symbols = json.loads(f["symbols"])
    budget = f["capital_usd"] / len(symbols)
    # A full grid deploys 1 + m + m^2 units, so one unit of capital is the
    # budget divided by that. Deploying the whole grid uses the whole budget.
    unit = budget / sum(g["size_mult"] ** k for k in range(g["levels"]))

    new_trades = 0
    conn.execute("DELETE FROM crypto_fund_open WHERE name=?", (FUND,))
    for sym in symbols:
        rows = conn.execute(
            "SELECT open_time, open, high, low, close FROM crypto_prices "
            "WHERE symbol=? AND interval=? ORDER BY open_time",
            (sym, f["interval"])).fetchall()
        if not rows:
            continue
        ts = np.array([r[0] for r in rows], dtype="int64")
        a = np.array([[r[1], r[2], r[3], r[4]] for r in rows], dtype="float64")
        start_i = int(np.searchsorted(ts, f["started_ts"]))
        if start_i >= len(ts) - 1:
            continue
        res = cg.simulate(a[:, 0], a[:, 1], a[:, 2], a[:, 3], g,
                          start_i=start_i, close_at_end=False)
        for t in res["trades"]:
            deployed = t["deployed"] * unit
            gross = deployed * t["gross_pct"] / 100.0
            net = deployed * t["ret_pct"] / 100.0
            nearest = min(sorted(cb.HOLDS), key=lambda h: abs(h - t["bars"]))
            cur = conn.execute("""INSERT OR IGNORE INTO crypto_fund_trades
                (name, symbol, entry_ts, exit_ts, reason, levels, deployed_usd,
                 gross_usd, fees_usd, net_usd, ret_pct, null_pct)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (FUND, sym, int(ts[t["entry_i"]]), int(ts[t["exit_i"]]),
                 t["reason"], t["levels"], deployed, gross, gross - net, net,
                 t["ret_pct"], cb.null_for(conn, sym, f["interval"], nearest)))
            new_trades += cur.rowcount
        if res["open"]:
            o = res["open"]
            last_close = float(a[-1, 3])
            dollars = sum(d for _, d in o["fills"]) * unit
            qty = sum(d / p for p, d in o["fills"]) * unit
            state = {"fills": o["fills"], "avg": o["avg"], "unit": unit,
                     "deployed_usd": dollars, "qty": qty,
                     "last_close": last_close,
                     "entry_fees_usd": dollars * cg.TAKER_FEE}
            conn.execute("""INSERT OR REPLACE INTO crypto_fund_open
                (name, symbol, entry_ts, state) VALUES (?,?,?,?)""",
                (FUND, sym, int(ts[o["entry_i"]]), json.dumps(state)))
    conn.execute("UPDATE crypto_fund SET last_step=? WHERE name=?",
                 (_now_iso(), FUND))
    conn.commit()
    return {"stepped": True, "new_trades": new_trades}


def mark(conn, date: str | None = None) -> dict:
    """
    One mark per UTC day. Unrealised P&L is charged the entry fees already
    paid, so an open grid never looks better than it is before its exit fee.
    """
    init(conn)
    f = _fund(conn)
    if not f:
        return {"marked": False, "reason": "no crypto fund"}
    date = date or datetime.now(timezone.utc).date().isoformat()
    realised = conn.execute("SELECT COALESCE(SUM(net_usd),0) FROM crypto_fund_trades "
                            "WHERE name=?", (FUND,)).fetchone()[0]
    unreal, n_open = 0.0, 0
    for r in conn.execute("SELECT state FROM crypto_fund_open WHERE name=?", (FUND,)):
        s = json.loads(r[0])
        unreal += s["qty"] * s["last_close"] - s["deployed_usd"] - s["entry_fees_usd"]
        n_open += 1
    equity = f["capital_usd"] + realised + unreal
    conn.execute("""INSERT OR REPLACE INTO crypto_fund_equity (name, date,
        equity_usd, realised_usd, unrealised_usd, open_positions)
        VALUES (?,?,?,?,?,?)""", (FUND, date, equity, realised, unreal, n_open))
    conn.commit()
    return {"marked": True, "date": date, "equity": equity,
            "realised": realised, "unrealised": unreal, "open": n_open}


def status(conn) -> dict:
    init(conn)
    f = _fund(conn)
    if not f:
        return {"exists": False}
    t = conn.execute("""SELECT COUNT(*), COALESCE(SUM(net_usd),0),
        COALESCE(SUM(fees_usd),0), COALESCE(AVG(ret_pct),0),
        COALESCE(AVG(ret_pct - COALESCE(null_pct, 0)),0),
        COALESCE(SUM(CASE WHEN net_usd > 0 THEN 1 ELSE 0 END),0)
        FROM crypto_fund_trades WHERE name=?""", (FUND,)).fetchone()
    eq = conn.execute("SELECT date, equity_usd FROM crypto_fund_equity WHERE name=? "
                      "ORDER BY date DESC LIMIT 1", (FUND,)).fetchone()
    marks = conn.execute("SELECT COUNT(*) FROM crypto_fund_equity WHERE name=?",
                         (FUND,)).fetchone()[0]
    opens = [dict(r) for r in conn.execute(
        "SELECT symbol, entry_ts, state FROM crypto_fund_open WHERE name=?", (FUND,))]
    return {"exists": True, "fund": f, "trades": t[0], "net_usd": t[1],
            "fees_usd": t[2], "mean_ret_pct": t[3], "mean_excess_pct": t[4],
            "wins": t[5], "equity": eq[1] if eq else f["capital_usd"],
            "last_mark": eq[0] if eq else None, "marks": marks, "open": opens}


def render(s: dict) -> str:
    if not s.get("exists"):
        return "\n  No crypto fund. Open one with: crypto_fund.py --open\n"
    f = s["fund"]
    start = datetime.fromtimestamp(f["started_ts"], timezone.utc).strftime("%Y-%m-%d %H:%M")
    ret = s["equity"] / f["capital_usd"] - 1
    L = ["", "  CRYPTO PAPER FUND",
         f"  opened {start} UTC   strategy {f['library_ref']}   "
         f"{len(json.loads(f['symbols']))} pairs",
         f"  equity ${s['equity']:,.2f} on ${f['capital_usd']:,.2f} ({ret:+.2%})   "
         f"{s['marks']} daily marks", "  " + "-" * 70,
         f"  closed trades {s['trades']}   wins {s['wins']}   "
         f"net ${s['net_usd']:,.2f}   fees ${s['fees_usd']:,.2f}"]
    if s["trades"]:
        L.append(f"  mean per trade {s['mean_ret_pct']:+.3f}%   "
                 f"vs its null {s['mean_excess_pct']:+.3f}%")
    L.append(f"  open grids {len(s['open'])}")
    for o in s["open"]:
        st = json.loads(o["state"])
        L.append(f"    {o['symbol']:<10}{len(st['fills'])} level(s)  "
                 f"deployed ${st['deployed_usd']:,.2f}  avg {st['avg']:,.4f}  "
                 f"last {st['last_close']:,.4f}")
    L += ["", "  The backtest of this strategy beat its null on 0 of 10 pairs after",
          "  fees. It runs forward anyway: a strategy nobody runs produces no",
          "  evidence, and this is the only measurement with no look-ahead.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--step", action="store_true")
    ap.add_argument("--mark", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)
    if a.open:
        r = open_fund(conn, a.capital)
        print(f"\n  opened {r['name']} with ${r['capital']:,.2f} across "
              f"{len(r['symbols'])} pairs")
    if a.step:
        r = step(conn)
        print(f"\n  stepped: {r.get('new_trades', 0)} new closed trade(s)"
              if r["stepped"] else f"\n  NOT stepped — {r['reason']}")
    if a.mark:
        r = mark(conn)
        print(f"  marked {r['date']}: ${r['equity']:,.2f}" if r["marked"]
              else f"  NOT marked — {r['reason']}")
    print(render(status(conn)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
