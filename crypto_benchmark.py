"""
What does chance earn in crypto? Phase 12.

THE RULE THIS EXISTS TO ENFORCE
---------------------------------
Scoring against zero rewards being long in a rising market, not selection. On
equities that mistake let 57% of random strategies pass validation, and fixing
it took two attempts: a flat null was a loophole in holding period (+0.07% at
5 days against +2.1% at 45), and then again in price (+25.2% for $5-6 names
against -0.5% above $100 over a 45-day hold).

**An equity null is not a crypto null.** Different drift, different volatility,
no sessions, and ten instruments rather than thirteen thousand. Reusing
`benchmark.py`'s surface here would charge a crypto strategy the drift of the
US equity market, which it neither earned nor was exposed to.

WHAT IS COMPUTED
----------------
A surface over holding period, per symbol and pooled: buy at a uniformly random
bar's NEXT open, hold N bars, sell at that bar's open. Fills match
`crypto_data`'s recorded convention exactly — a bar is a session — because a
null computed on a different fill convention than the strategy makes the
comparison rigged, which is a mistake this project has had to correct twice.

Per symbol as well as pooled, because pooling alone would repeat the price-band
error in a new form: BTC and a small-cap alt have different drift, and a
strategy that only ever traded one of them should be charged that one's null
rather than the average.

DELISTED PAIRS ARE INCLUDED
-----------------------------
MATIC-USD stopped trading in 2025 and its bars are in the table. It is included
here deliberately. A null computed only on survivors is exactly the bias that
makes a backtest look good, and crypto delists far more readily than the US
equity market.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import numpy as np

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cbench")

HOLDS = (1, 4, 12, 24, 72, 168, 336)   # bars; at 1h these are 1h .. 2 weeks
DRAWS = 4000


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_benchmarks (
            symbol    TEXT NOT NULL,
            interval  TEXT NOT NULL,
            hold_bars INTEGER NOT NULL,
            mean_pct  REAL, median_pct REAL, p25 REAL, p75 REAL,
            stdev_pct REAL, n_draws INTEGER,
            computed_at TEXT NOT NULL,
            PRIMARY KEY (symbol, interval, hold_bars)
        )
    """)
    conn.commit()


def _opens(conn, symbol: str, interval: str):
    rows = conn.execute(
        "SELECT open_time, open FROM crypto_prices WHERE symbol=? AND interval=? "
        "ORDER BY open_time", (symbol, interval)).fetchall()
    return np.array([r[1] for r in rows], dtype="float64")


def surface(conn, interval: str = "1h", holds=HOLDS, draws: int = DRAWS,
            seed: int = 20260923) -> dict:
    """
    Random-entry returns per symbol and pooled.

    Entry is the NEXT bar's open after a randomly chosen bar, matching the
    convention crypto_data records: a signal from a bar's close cannot be
    filled at that close.
    """
    init(conn)
    rng = np.random.default_rng(seed)
    symbols = [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM crypto_prices WHERE interval=? ORDER BY symbol",
        (interval,))]
    out, pooled = {}, {h: [] for h in holds}

    for sym in symbols:
        o = _opens(conn, sym, interval)
        if o.size < max(holds) + 4:
            continue
        out[sym] = {}
        for h in holds:
            # entry at i+1, exit at i+1+h, so the last usable i is n-h-2
            hi = o.size - h - 2
            if hi <= 1:
                continue
            idx = rng.integers(0, hi, size=min(draws, hi))
            entry, exit_ = o[idx + 1], o[idx + 1 + h]
            ok = np.isfinite(entry) & np.isfinite(exit_) & (entry > 0)
            r = (exit_[ok] - entry[ok]) / entry[ok] * 100.0
            if r.size < 50:
                continue
            out[sym][h] = {
                "mean": float(r.mean()), "median": float(np.median(r)),
                "p25": float(np.percentile(r, 25)),
                "p75": float(np.percentile(r, 75)),
                "stdev": float(r.std(ddof=1)), "n": int(r.size)}
            pooled[h].append(r)

    pooled_out = {}
    for h, parts in pooled.items():
        if not parts:
            continue
        r = np.concatenate(parts)
        pooled_out[h] = {"mean": float(r.mean()), "median": float(np.median(r)),
                         "p25": float(np.percentile(r, 25)),
                         "p75": float(np.percentile(r, 75)),
                         "stdev": float(r.std(ddof=1)), "n": int(r.size)}
    return {"interval": interval, "per_symbol": out, "pooled": pooled_out,
            "symbols": len(out)}


def store(conn, s: dict) -> int:
    init(conn)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for sym, hs in s["per_symbol"].items():
        for h, v in hs.items():
            rows.append((sym, s["interval"], h, v["mean"], v["median"],
                         v["p25"], v["p75"], v["stdev"], v["n"], at))
    for h, v in s["pooled"].items():
        rows.append(("__POOLED__", s["interval"], h, v["mean"], v["median"],
                     v["p25"], v["p75"], v["stdev"], v["n"], at))
    conn.executemany("""INSERT OR REPLACE INTO crypto_benchmarks (symbol,
        interval, hold_bars, mean_pct, median_pct, p25, p75, stdev_pct,
        n_draws, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)""", rows)
    conn.commit()
    return len(rows)


def null_for(conn, symbol: str, interval: str, hold_bars: int):
    """
    The null a trade in `symbol` held `hold_bars` must beat.

    Falls back to the pooled surface when the symbol has none, and returns None
    when neither exists — an unknown null is NOT zero. Treating it as zero
    would restore exactly the loophole this module was built to close.
    """
    # Create the table if the null has never been computed. Without this the
    # call RAISED on a fresh database instead of returning None, and the crypto
    # fund's step — which runs under `|| true` in daily.sh — would have failed
    # silently every morning, recording nothing. Found by TASK-015's test.
    init(conn)
    r = conn.execute("""SELECT mean_pct FROM crypto_benchmarks
        WHERE symbol=? AND interval=? AND hold_bars=?""",
        (symbol, interval, hold_bars)).fetchone()
    if r:
        return float(r[0])
    r = conn.execute("""SELECT mean_pct FROM crypto_benchmarks
        WHERE symbol='__POOLED__' AND interval=? AND hold_bars=?""",
        (interval, hold_bars)).fetchone()
    return float(r[0]) if r else None


def render(s: dict) -> str:
    L = ["", f"  CRYPTO NULL SURFACE — {s['interval']} bars, "
             f"{s['symbols']} symbols",
         "  Random entry at the NEXT bar's open, held N bars. Mean return %.",
         "  " + "-" * 74,
         "  " + f"{'symbol':<12}" + "".join(f"{h:>9}" for h in HOLDS)]
    for sym, hs in sorted(s["per_symbol"].items()):
        cells = "".join(f"{hs[h]['mean']:>9.3f}" if h in hs else f"{'—':>9}"
                        for h in HOLDS)
        L.append(f"  {sym:<12}{cells}")
    if s["pooled"]:
        cells = "".join(f"{s['pooled'][h]['mean']:>9.3f}" if h in s["pooled"]
                        else f"{'—':>9}" for h in HOLDS)
        L.append("  " + "-" * 74)
        L.append(f"  {'POOLED':<12}{cells}")
    L += ["  " + "-" * 74, "",
          "  A strategy is charged the null of the SYMBOL it traded, not the",
          "  pooled figure. Pooling alone would repeat the equity price-band",
          "  error: a strategy that only ever bought one pair would be judged",
          "  against the average of ten.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--draws", type=int, default=DRAWS)
    ap.add_argument("--store", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    s = surface(conn, a.interval, draws=a.draws)
    print(render(s))
    if a.store:
        print(f"  stored {store(conn, s)} cells\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
