"""
The null hypothesis, measured. What does doing nothing clever earn?

Every fitness score and every promotion gate in this project compared results
against **zero**. That is not a test of skill. Measured on our own data, buying at
random and holding five days earned:

    2018-19   +0.206% per trade   (+0.003% net of costs)
    2020-22   +0.269% per trade   (+0.066% net of costs)
    2023-26   +0.385% per trade   (+0.182% net of costs)

Positive in every window, because the market went up. So "net P&L > 0" tests
whether a strategy was long during a bull market, not whether it picked well —
which is why 52% of *random, never-evolved* strategies passed the validation gate.

This module computes that null so everything downstream can be scored as **excess
over it**. A strategy that beats zero is uninteresting; one that beats buying at
random, after costs, is the entire point.

Benchmarks are cached per window because the null does not depend on the strategy
being tested, and recomputing it for every candidate would dominate a search.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import costs as costs_mod
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("benchmark")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS benchmarks (
            window_start  TEXT NOT NULL,
            window_end    TEXT NOT NULL,
            horizon_days  INTEGER NOT NULL,
            min_price     REAL, min_dollar_volume REAL,
            n_obs         INTEGER NOT NULL,
            gross_pct     REAL NOT NULL,    -- avg forward return per trade
            cost_pct      REAL NOT NULL,
            net_pct       REAL NOT NULL,    -- what a random entry actually earns
            computed_at   TEXT NOT NULL,
            PRIMARY KEY (window_start, window_end, horizon_days, min_price, min_dollar_volume)
        ) STRICT
    """)
    conn.commit()


def compute(conn, cfg: dict, window: tuple[str, str],
            horizon: int | None = None, refresh: bool = False) -> dict:
    """
    Average net return of a random entry held `horizon` days in this window.

    This is the number a strategy has to beat to have demonstrated anything. It
    is computed over the same filtered universe the strategy trades, so the
    comparison is like for like — benchmarking a liquid-large-cap strategy
    against the whole market including microcaps would be its own kind of
    cheating.
    """
    init(conn)
    horizon = horizon or cfg["labeling"]["horizon_days"]
    mp = cfg["risk"].get("min_price")
    mv = cfg["risk"].get("min_dollar_volume")

    if not refresh:
        row = conn.execute("""
            SELECT * FROM benchmarks WHERE window_start=? AND window_end=?
              AND horizon_days=? AND min_price=? AND min_dollar_volume=?
        """, (window[0], window[1], horizon, mp, mv)).fetchone()
        if row:
            return dict(row)

    log.info(f"Computing the null for {window[0]} -> {window[1]} ({horizon}d hold)")
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1], min_price=mp, min_dollar_volume=mv,
        include_liquidity=True)
    if df.empty:
        return {"net_pct": 0.0, "gross_pct": 0.0, "cost_pct": 0.0, "n_obs": 0}

    df = df.sort_values(["ticker", "date"])
    fwd = df.groupby("ticker", observed=True)["close"].pct_change(horizon).shift(-horizon)
    valid = fwd.dropna()

    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    # Cost of the median name actually traded, not of a hypothetical one.
    median_dv = float(df["dollar_volume_20"].median()) if "dollar_volume_20" in df else 0.0
    cost_pct = float(cm.round_trip(size, median_dv, size / 50) / size * 100)

    gross = float(valid.mean()) * 100
    rec = {"window_start": window[0], "window_end": window[1], "horizon_days": horizon,
           "min_price": mp, "min_dollar_volume": mv, "n_obs": int(len(valid)),
           "gross_pct": gross, "cost_pct": cost_pct, "net_pct": gross - cost_pct,
           "computed_at": storage._now()}
    conn.execute("""
        INSERT OR REPLACE INTO benchmarks
            (window_start, window_end, horizon_days, min_price, min_dollar_volume,
             n_obs, gross_pct, cost_pct, net_pct, computed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, tuple(rec[k] for k in ("window_start", "window_end", "horizon_days", "min_price",
                                "min_dollar_volume", "n_obs", "gross_pct", "cost_pct",
                                "net_pct", "computed_at")))
    conn.commit()
    log.info(f"  null: {gross:+.3f}% gross, {cost_pct:.3f}% costs, "
             f"{rec['net_pct']:+.3f}% net over {len(valid):,} observations")
    return rec


def report(conn, cfg: dict) -> None:
    lab = cfg["lab"]
    windows = [
        (lab["search_start"], lab["search_end"], "search"),
        (lab["validation_start"], lab["validation_end"], "validation"),
        (lab["sealed_start"], "2099-12-31", "sealed"),
    ]
    print(f"\n  {'window':<28}{'gross':>9}{'costs':>9}{'NET NULL':>11}{'obs':>12}")
    print("  " + "-" * 70)
    for a, b, label in windows:
        r = compute(conn, cfg, (a, b))
        print(f"  {label + ' ' + a[:7] + '-' + b[:7]:<28}{r['gross_pct']:>8.3f}%"
              f"{r['cost_pct']:>8.3f}%{r['net_pct']:>10.3f}%{r['n_obs']:>12,}")
    print("\n  A strategy must beat the NET NULL to have demonstrated anything.")
    print("  Beating zero only demonstrates it was long in a rising market.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    init(conn)
    if args.refresh:
        lab = cfg["lab"]
        for a, b in [(lab["search_start"], lab["search_end"]),
                     (lab["validation_start"], lab["validation_end"]),
                     (lab["sealed_start"], "2099-12-31")]:
            compute(conn, cfg, (a, b), refresh=True)
    report(conn, cfg)
    conn.close()


if __name__ == "__main__":
    main()
