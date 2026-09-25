"""Stage K3: backtest a fixed grid of crypto_trend genomes over daily crypto bars.

Every number here is net of a *measured* Robinhood half-spread (crypto_costs),
not a modelled one, because the whole point of this stage is to find out whether
the trend genomes survive the spread the account actually pays.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy import)

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np

import crypto_costs
import crypto_data
import crypto_trend
import storage
from universe import load_config

GRID = {
    "trend_sma": (20, 50, 100, 200),
    "tsmom": (30, 90, 180),
    "breakout": (20, 55),
}
STOP_ATRS = (3.0, 5.0)
UNIVERSES = ("btc_eth", "all")
UNIVERSE_SYMBOLS = {"btc_eth": ["BTC-USD", "ETH-USD"]}

DEFAULT_WINDOW_START = "2016-01-01"


def genomes():
    """The 36 genomes in a stable order (family, n, stop_atr, universe)."""
    out = []
    for family in sorted(GRID):
        for n in GRID[family]:
            for stop_atr in STOP_ATRS:
                for universe in UNIVERSES:
                    out.append({
                        "family": family,
                        "n": int(n),
                        "stop_atr": float(stop_atr),
                        "universe": universe,
                    })
    return out


def strategy_id(genome):
    blob = json.dumps(genome, sort_keys=True)
    return "ctrend_" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_backtests (
            strategy_id      TEXT PRIMARY KEY,
            genome           TEXT NOT NULL,
            window_start     TEXT,
            window_end       TEXT,
            symbols          TEXT,
            trades           INTEGER,
            gross_per_trade  REAL,
            net_per_trade    REAL,
            win_rate         REAL,
            mean_bars        REAL,
            null_per_trade   REAL,
            excess_per_trade REAL,
            bh_mean          REAL,
            half_spread_mean REAL,
            by_year          TEXT,
            run_at           TEXT
        )
        """
    )
    conn.commit()


def load_bars(conn, symbol):
    rows = conn.execute(
        "SELECT open_time, open, high, low, close FROM crypto_prices "
        "WHERE symbol = ? AND interval = '1d' ORDER BY open_time",
        (symbol,),
    ).fetchall()
    if not rows:
        return None
    arr = np.array(rows, dtype=object)
    open_time = np.array([int(r[0]) for r in rows], dtype=np.int64)
    o = np.array([float(r[1]) for r in rows], dtype=float)
    h = np.array([float(r[2]) for r in rows], dtype=float)
    l = np.array([float(r[3]) for r in rows], dtype=float)
    c = np.array([float(r[4]) for r in rows], dtype=float)
    del arr
    return open_time, o, h, l, c


def symbols_1d(conn):
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM crypto_prices WHERE interval = '1d' ORDER BY symbol"
    ).fetchall()
    return [r[0] for r in rows]


def _window_start_epoch(window_start):
    dt = datetime.strptime(window_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _iso_date(epoch_seconds):
    return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).strftime("%Y-%m-%d")


def _universe_symbols(conn, universe):
    if universe in UNIVERSE_SYMBOLS:
        return list(UNIVERSE_SYMBOLS[universe])
    return symbols_1d(conn)


def run_one(conn, genome, cfg=None, window_start=DEFAULT_WINDOW_START):
    if cfg is None:
        cfg = load_config()
    cost_cfg = cfg.get("crypto_costs")
    start_epoch = _window_start_epoch(window_start)

    symbols = _universe_symbols(conn, genome["universe"])
    all_trades = []
    nulls = []          # (n_trades, null_per_trade) for the weighted mean
    bh_values = []
    hs_values = []
    by_year = {}
    used_symbols = []
    last_epoch = None

    for symbol in symbols:
        bars = load_bars(conn, symbol)
        if bars is None:
            continue
        open_time, o, h, l, c = bars
        n = len(open_time)
        # start_i is the first bar inside the window; indicators may still read
        # the earlier bars, which is why we slice by index rather than by array.
        idx = np.nonzero(open_time >= start_epoch)[0]
        if len(idx) == 0:
            continue
        start_i = int(idx[0])
        hi_i = n - 1
        if hi_i <= start_i:
            continue

        hs = crypto_costs.half_spread(conn, symbol, cost_cfg)
        sim = crypto_trend.simulate(o, h, l, c, genome, hs, start_i=start_i, close_at_end=True)
        trades = sim["trades"]
        used_symbols.append(symbol)
        hs_values.append(float(hs))
        if last_epoch is None or open_time[hi_i] > last_epoch:
            last_epoch = int(open_time[hi_i])

        if trades:
            all_trades.extend(trades)
            null = crypto_trend.null_per_trade(o, trades, hs, start_i, hi_i)
            if null is not None:
                nulls.append((len(trades), float(null)))
            for t in trades:
                year = _iso_date(open_time[int(t["entry_i"])])[:4]
                bucket = by_year.setdefault(year, {"trades": 0, "net_sum": 0.0})
                bucket["trades"] += 1
                bucket["net_sum"] += float(t["net"])

        bh = crypto_trend.buy_and_hold(o, c, start_i, hi_i, hs)
        if bh is not None:
            bh_values.append(float(bh))

    summary = crypto_trend.summarize(all_trades) if all_trades else {
        "trades": 0, "gross_per_trade": None, "net_per_trade": None,
        "win_rate": None, "mean_bars": None,
    }

    if nulls:
        total = sum(w for w, _ in nulls)
        null_per_trade = sum(w * v for w, v in nulls) / total if total else None
    else:
        null_per_trade = None

    net = summary.get("net_per_trade")
    excess = None if (net is None or null_per_trade is None) else net - null_per_trade

    by_year_out = {
        y: {"trades": b["trades"], "net_per_trade": (b["net_sum"] / b["trades"]) if b["trades"] else None}
        for y, b in sorted(by_year.items())
    }

    return {
        "strategy_id": strategy_id(genome),
        "genome": json.dumps(genome, sort_keys=True),
        "window_start": window_start,
        "window_end": _iso_date(last_epoch) if last_epoch is not None else None,
        "symbols": json.dumps(used_symbols),
        "trades": int(summary.get("trades") or 0),
        "gross_per_trade": summary.get("gross_per_trade"),
        "net_per_trade": net,
        "win_rate": summary.get("win_rate"),
        "mean_bars": summary.get("mean_bars"),
        "null_per_trade": null_per_trade,
        "excess_per_trade": excess,
        "bh_mean": (sum(bh_values) / len(bh_values)) if bh_values else None,
        "half_spread_mean": (sum(hs_values) / len(hs_values)) if hs_values else None,
        "by_year": json.dumps(by_year_out, sort_keys=True),
    }


_COLUMNS = (
    "strategy_id", "genome", "window_start", "window_end", "symbols", "trades",
    "gross_per_trade", "net_per_trade", "win_rate", "mean_bars",
    "null_per_trade", "excess_per_trade", "bh_mean", "half_spread_mean",
    "by_year", "run_at",
)


def run(conn, cfg=None, window_start=DEFAULT_WINDOW_START, only=None):
    if cfg is None:
        cfg = load_config()
    init(conn)
    rows = []
    for genome in genomes():
        sid = strategy_id(genome)
        if only is not None and sid not in only:
            continue
        row = run_one(conn, genome, cfg=cfg, window_start=window_start)
        row["run_at"] = datetime.now(timezone.utc).isoformat()
        placeholders = ", ".join("?" for _ in _COLUMNS)
        conn.execute(
            "INSERT OR REPLACE INTO crypto_backtests (%s) VALUES (%s)"
            % (", ".join(_COLUMNS), placeholders),
            tuple(row[c] for c in _COLUMNS),
        )
        rows.append(row)
    conn.commit()
    return rows


def result(conn, strategy_id_):
    try:
        cur = conn.execute(
            "SELECT %s FROM crypto_backtests WHERE strategy_id = ?" % ", ".join(_COLUMNS),
            (strategy_id_,),
        )
    except sqlite3.OperationalError:
        return None
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip(_COLUMNS, row))


def _pct(value):
    return "n/a" if value is None else "%.2f" % (100.0 * value)


def _report(conn):
    try:
        rows = conn.execute(
            "SELECT %s FROM crypto_backtests" % ", ".join(_COLUMNS)
        ).fetchall()
    except sqlite3.OperationalError:
        return
    records = [dict(zip(_COLUMNS, r)) for r in rows]
    records.sort(key=lambda r: (r["net_per_trade"] is None, -(r["net_per_trade"] or 0.0)))
    for r in records:
        g = json.loads(r["genome"])
        print(
            "%s %s n=%s stop_atr=%s %s trades=%s gross=%s%% net=%s%% null=%s%% "
            "excess=%s%% bh=%s%%"
            % (
                r["strategy_id"], g["family"], g["n"], g["stop_atr"], g["universe"],
                r["trades"], _pct(r["gross_per_trade"]), _pct(r["net_per_trade"]),
                _pct(r["null_per_trade"]), _pct(r["excess_per_trade"]), _pct(r["bh_mean"]),
            )
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Crypto trend genome backtests (Stage K3)")
    parser.add_argument("--run", action="store_true", help="run the genome grid")
    parser.add_argument("--report", action="store_true", help="print stored results")
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    args = parser.parse_args(argv)

    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    try:
        crypto_data.init(conn)
        if args.run:
            rows = run(conn, cfg=cfg, window_start=args.window_start)
            print("ran %d genomes" % len(rows))
        if args.report:
            _report(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
