"""Stage K4: forward paper funds for crypto_trend genomes.

Reuses the crypto_fund tables so accounting.py and leagues.py pick these funds
up with no changes. A fund is a deterministic replay: every step re-simulates
each symbol from the fund's start and INSERT OR IGNOREs closed trades keyed by
(name, symbol, entry_ts), so re-running a step is a no-op.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import json
import sys
from datetime import datetime, timezone

import crypto_backtest
import crypto_costs
import crypto_data
import crypto_fund
import crypto_trend
import storage
from universe import load_config

DAY = 86400
ENGINE = "crypto_trend"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _utc_date(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")


def _online_symbols(conn):
    rows = conn.execute(
        "SELECT l.symbol FROM crypto_listings l WHERE l.status = 'online'"
        " AND l.trading_disabled = 0"
        " AND EXISTS (SELECT 1 FROM crypto_prices p WHERE p.symbol = l.symbol"
        "             AND p.interval = '1d')"
        " ORDER BY l.symbol"
    ).fetchall()
    return [r[0] for r in rows]


def _bars(conn, symbol, interval="1d"):
    rows = conn.execute(
        "SELECT open_time, open, high, low, close FROM crypto_prices"
        " WHERE symbol = ? AND interval = ? ORDER BY open_time",
        (symbol, interval),
    ).fetchall()
    return rows


def _latest_open_time(conn):
    row = conn.execute(
        "SELECT MAX(open_time) FROM crypto_prices WHERE interval = '1d'"
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _strategy(conn, name):
    row = conn.execute(
        "SELECT strategy FROM crypto_fund WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def open_fund(conn, name, genome, capital=100.0, symbols=None, cfg=None,
              started_ts=None):
    if conn.execute("SELECT 1 FROM crypto_fund WHERE name = ?", (name,)).fetchone():
        raise SystemExit(f"crypto fund already exists: {name}")
    if cfg is None:
        cfg = load_config()
    if symbols is None:
        symbols = _online_symbols(conn)
    symbols = sorted(symbols)
    if not symbols:
        raise SystemExit("no symbols available for crypto fund")
    if started_ts is None:
        latest = _latest_open_time(conn)
        if latest is None:
            raise SystemExit("no 1d bars to anchor the fund start")
        # The next bar to open, so the first replayable bar is a fresh one.
        started_ts = int(latest) + DAY
    # Spreads are frozen at open: later measurements must not rewrite the
    # forward record of a fund that is already running.
    hs = {s: float(crypto_costs.half_spread(conn, s, cfg)) for s in symbols}
    strategy = {
        "engine": ENGINE,
        "genome": genome,
        "strategy_id": crypto_backtest.strategy_id(genome),
        "hs": hs,
    }
    conn.execute(
        "INSERT INTO crypto_fund (name, capital_usd, started_ts, interval,"
        " strategy, library_ref, symbols, status, last_step, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (name, float(capital), int(started_ts), "1d", json.dumps(strategy),
         strategy["strategy_id"], json.dumps(symbols), "open", None, _now()),
    )
    conn.commit()
    return {"name": name, "capital_usd": float(capital),
            "started_ts": int(started_ts), "symbols": symbols,
            "strategy_id": strategy["strategy_id"], "hs": hs}


def step(conn, name):
    strat = _strategy(conn, name)
    if strat is None:
        return {"stepped": False, "reason": "unknown fund"}
    if strat.get("engine") != ENGINE:
        return {"stepped": False, "reason": "not a crypto_trend fund"}
    row = conn.execute(
        "SELECT capital_usd, started_ts, symbols FROM crypto_fund WHERE name = ?",
        (name,),
    ).fetchone()
    capital, started_ts, symbols_json = row
    symbols = json.loads(symbols_json)
    genome = strat["genome"]
    hs_map = strat.get("hs", {})
    per_symbol = float(capital) / len(symbols)
    new_trades = 0
    open_rows = []
    for symbol in symbols:
        bars = _bars(conn, symbol)
        if not bars:
            continue
        o = [b[1] for b in bars]
        h = [b[2] for b in bars]
        l = [b[3] for b in bars]
        c = [b[4] for b in bars]
        start_i = 0
        for i, b in enumerate(bars):
            if b[0] >= started_ts:
                start_i = i
                break
        else:
            # Every bar predates the fund: nothing may be entered yet.
            start_i = len(bars)
        hs = float(hs_map.get(symbol, 0.0))
        res = crypto_trend.simulate(o, h, l, c, genome, hs, start_i=start_i, close_at_end=False)
        for t in res.get("trades", []):
            entry_ts = int(bars[t["entry_i"]][0])
            exit_ts = int(bars[t["exit_i"]][0])
            gross = float(t["gross"])
            net = float(t["net"])
            gross_usd = per_symbol * gross
            net_usd = per_symbol * net
            cur = conn.execute(
                "INSERT OR IGNORE INTO crypto_fund_trades (name, symbol,"
                " entry_ts, exit_ts, reason, levels, deployed_usd, gross_usd,"
                " fees_usd, net_usd, ret_pct, null_pct)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, symbol, entry_ts, exit_ts, t["reason"], 1, per_symbol,
                 gross_usd, gross_usd - net_usd, net_usd, net * 100.0, None),
            )
            new_trades += cur.rowcount
        op = res.get("open")
        if op is not None:
            entry_px = float(op["entry_px"])
            open_rows.append((
                name, symbol, int(bars[op["entry_i"]][0]),
                json.dumps({
                    "entry_px": entry_px,
                    "stop": op["stop"],
                    "deployed_usd": per_symbol,
                    "qty": per_symbol * (1.0 - hs) / entry_px,
                    "last_close": float(c[-1]),
                    "entry_fees_usd": per_symbol * hs,
                    "hs": hs,
                }),
            ))
    # The open set is rewritten wholesale: it is derived state, not history.
    conn.execute("DELETE FROM crypto_fund_open WHERE name = ?", (name,))
    conn.executemany(
        "INSERT INTO crypto_fund_open (name, symbol, entry_ts, state)"
        " VALUES (?,?,?,?)", open_rows)
    conn.execute("UPDATE crypto_fund SET last_step = ? WHERE name = ?",
                 (_now(), name))
    conn.commit()
    return {"stepped": True, "new_trades": new_trades}


def mark(conn, name, date=None):
    row = conn.execute(
        "SELECT capital_usd FROM crypto_fund WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return {"marked": False, "reason": "unknown fund"}
    capital = float(row[0])
    realised = conn.execute(
        "SELECT COALESCE(SUM(net_usd), 0) FROM crypto_fund_trades WHERE name = ?",
        (name,),
    ).fetchone()[0]
    realised = float(realised or 0.0)
    unrealised = 0.0
    n_open = 0
    for state_json in conn.execute(
        "SELECT state FROM crypto_fund_open WHERE name = ?", (name,)
    ).fetchall():
        st = json.loads(state_json[0])
        unrealised += float(st["qty"]) * float(st["last_close"]) - float(st["deployed_usd"])
        n_open += 1
    equity = capital + realised + unrealised
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT OR REPLACE INTO crypto_fund_equity (name, date, equity_usd,"
        " realised_usd, unrealised_usd, open_positions) VALUES (?,?,?,?,?,?)",
        (name, date, equity, realised, unrealised, n_open),
    )
    conn.commit()
    return {"marked": True, "date": date, "equity_usd": equity,
            "realised_usd": realised, "unrealised_usd": unrealised,
            "open_positions": n_open}


def funds(conn):
    out = []
    for name, strategy in conn.execute(
        "SELECT name, strategy FROM crypto_fund ORDER BY name"
    ).fetchall():
        try:
            strat = json.loads(strategy)
        except (TypeError, ValueError):
            continue
        if isinstance(strat, dict) and strat.get("engine") == ENGINE:
            out.append(name)
    return out


def _status(conn, name):
    row = conn.execute(
        "SELECT capital_usd FROM crypto_fund WHERE name = ?", (name,)
    ).fetchone()
    capital = float(row[0]) if row else 0.0
    realised = float(conn.execute(
        "SELECT COALESCE(SUM(net_usd), 0) FROM crypto_fund_trades WHERE name = ?",
        (name,),
    ).fetchone()[0] or 0.0)
    n_closed = conn.execute(
        "SELECT COUNT(*) FROM crypto_fund_trades WHERE name = ?", (name,)
    ).fetchone()[0]
    n_open = conn.execute(
        "SELECT COUNT(*) FROM crypto_fund_open WHERE name = ?", (name,)
    ).fetchone()[0]
    unrealised = 0.0
    for state_json in conn.execute(
        "SELECT state FROM crypto_fund_open WHERE name = ?", (name,)
    ).fetchall():
        st = json.loads(state_json[0])
        unrealised += float(st["qty"]) * float(st["last_close"]) - float(st["deployed_usd"])
    return capital + realised + unrealised, n_closed, n_open


def main(argv=None):
    ap = argparse.ArgumentParser(description="crypto_trend forward paper funds")
    ap.add_argument("--open", metavar="NAME")
    ap.add_argument("--genome")
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--step", action="store_true")
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)
    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    try:
        crypto_data.init(conn)
        crypto_fund.init(conn)
        if args.open:
            if not args.genome:
                raise SystemExit("--open requires --genome")
            print(json.dumps(open_fund(conn, args.open, json.loads(args.genome),
                                       capital=args.capital, cfg=cfg)))
        if args.step:
            for name in funds(conn):
                print(name, json.dumps(step(conn, name)))
        if args.mark:
            for name in funds(conn):
                print(name, json.dumps(mark(conn, name)))
        if args.status:
            for name in funds(conn):
                equity, n_closed, n_open = _status(conn, name)
                print(f"{name} equity={equity:.2f} closed={n_closed} open={n_open}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
