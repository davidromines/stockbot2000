"""
Backtests that include the dead companies. Owner, 2026-09-24: "Use the
synthetic data. Why are you not using the systems we built?"

WHAT WAS WRONG
--------------
The Addendum C generator (universe_synthetic.py) writes price paths for 7,618
dead companies we hold no prices for, and universe_loader.py serves them in
five modes. But every backtest that picks live strategies — the factory, the
Lab evaluations ranking.py reads — ran on `prices` alone, and the synthetic
paths had no indicators, so the simulator could not have traded them anyway.
The only consumer was a sensitivity report.

WHAT THIS DOES
--------------
For every strategy in the ranking pool with an entry rule, one backtest per
mode over the factory backtest window, with the SAME simulator, costs and fills:

    exclude   primary database only (what every backtest here used to be)
    as_is     + the synthetic dead companies as generated — delisting returns
              from the literature (Shumway: -55% NASDAQ performance delistings)
    zero      + the synthetic dead companies, every delisting a total loss

ranking.py then scores a strategy's backtest on **as_is**, gates it on as_is
(a strategy that loses money once dead companies are in the universe is out),
and shows `zero` beside it as the worst case. `exclude` is kept so the cost of
survivorship bias is visible per strategy.

The drawdown exposure check the old promotion ladder applied (promote.py; share
of entries in names already 30% below their 200-day high) is measured here too
and gated in ranking.py.

ASSUMPTIONS — stated because they are not measurements
------------------------------------------------------
- **The generator fails its realism gate** (AUC 0.768 vs < 0.60). The owner
  ruled 2026-09-24 that it is used in the ranking anyway; that overrides the
  Addendum C default "retests and stress bounds only". A biased-toward-
  survivors backtest is the known-wrong alternative.
- **Synthetic volume is unknown** (NULL, never invented). So a synthetic name
  is treated as sitting exactly at the liquidity floor: it may be bought, and
  pays that tier's spread. Volume-derived indicators (vol_ratio, obv_rising,
  chaikin_osc) stay NaN, so rules built on them never fire on a synthetic name
  — `synthetic_trades` shows how many trades each strategy took in them.
- **No fundamentals** exist for synthetic companies, so fundamental screens
  never buy them; their as_is result is close to exclude by construction.
- Synthetic rows trade as `SYN:<company_id>`: a dead company's ticker is often
  reused later by someone else, and two dead companies can share one.

    ./run_bounded.sh ./venv/bin/python survivorship_backtest.py --run
    ./venv/bin/python survivorship_backtest.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import gc
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

log = logging.getLogger("survivorship_backtest")

MODES = ("exclude", "as_is", "zero")
SCORE_MODE = "as_is"
WORST_MODE = "zero"
PREFIX = "SYN:"
WARMUP_DAYS = 400             # calendar days of history before the window, for the 200-day indicators
EXIT_MARGIN_DAYS = 120
VOLUME_COLS = ("vol_ratio", "obv_rising", "chaikin_osc")
MIN_SYNTH_ROWS = 20


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS survivorship_backtests (
            strategy_key     TEXT NOT NULL,
            version          INTEGER NOT NULL,
            mode             TEXT NOT NULL,
            generator        TEXT NOT NULL,
            window           TEXT NOT NULL,
            trades           INTEGER,
            synthetic_trades INTEGER,
            gross_usd        REAL,
            costs_usd        REAL,
            net_usd          REAL,
            per_trade        REAL,
            share_deep       REAL,
            computed_at      TEXT NOT NULL,
            PRIMARY KEY (strategy_key, version, mode, generator, window)
        )""")
    conn.commit()


def generator() -> str | None:
    """Which synthetic build a result used: file name and size, so a rebuild recomputes."""
    import universe_loader as ul
    if not os.path.exists(ul.SYNTH):
        return None
    return f"{os.path.basename(ul.SYNTH)}:{os.path.getsize(ul.SYNTH)}"


def window_of(cfg) -> tuple:
    return tuple((cfg.get("factory") or {}).get("backtest_window") or ("2016-01-01", "2019-12-31"))


# --- the synthetic panel ------------------------------------------------------------

def synthetic_frames(conn, cfg, window, mode: str) -> tuple:
    """
    (panel rows, exit prices) for the synthetic companies in `window` under `mode`,
    shaped like storage.load_training_frame(include_liquidity, include_open).
    """
    import features
    import universe_loader as ul
    from train_model import FEATURE_COLS
    start = (dt.date.fromisoformat(window[0]) - dt.timedelta(days=WARMUP_DAYS)).isoformat()
    end = (dt.date.fromisoformat(window[1]) + dt.timedelta(days=EXIT_MARGIN_DAYS)).isoformat()
    all_real = set(t for (t,) in conn.execute("SELECT DISTINCT ticker FROM symbols"))
    syn = ul._synthetic(start, end, mode, all_real)
    if syn.empty:
        return pd.DataFrame(), pd.DataFrame()
    syn = syn.assign(ticker=PREFIX + syn["company_id"].astype(str),
                     date=pd.to_datetime(syn["date"]))
    floor = float(cfg["risk"].get("min_dollar_volume") or 1e6)
    parts = []
    for _, g in syn.groupby("ticker", sort=False):
        f = features.compute_features_for_ticker(g[["ticker", "date", "open", "high", "low", "close", "volume"]]
                                                 .copy(), min_rows=MIN_SYNTH_ROWS)
        if not f.empty:
            parts.append(f)
    if not parts:
        return pd.DataFrame(), pd.DataFrame()
    f = pd.concat(parts, ignore_index=True)
    for c in VOLUME_COLS:
        f[c] = np.nan                              # volume is unknown, not zero
    f["dollar_volume_20"] = floor                  # stated assumption: at the floor
    f["log_dollar_volume"] = np.log10(floor)
    exits = f[["ticker", "date", "close", "open"]].copy()
    inwin = (f["date"] >= pd.Timestamp(window[0])) & (f["date"] <= pd.Timestamp(window[1]))
    min_price = float(cfg["risk"].get("min_price") or 0)
    need = [c for c in FEATURE_COLS if c not in VOLUME_COLS]
    rows = f[inwin & (f["close"] >= min_price)].dropna(subset=need)
    keep = ["ticker", "date", "close", "open", *FEATURE_COLS, "dollar_volume_20"]
    rows = rows[keep].copy()
    for c in FEATURE_COLS + ["close", "open"]:
        rows[c] = rows[c].astype("float32")
    return rows, exits


# --- strategies -------------------------------------------------------------------

def strategies(conn) -> list:
    """(key, version, genome, needs_fundamentals) for every pool strategy with an entry rule."""
    import ranking
    import slots
    import storage
    out = []
    for key, ver, _ in ranking.pool(conn):
        try:
            g = slots.genome_for(conn, key, ver)
        except Exception as e:                                  # noqa: BLE001
            log.warning(f"{key} v{ver}: genome unavailable ({type(e).__name__})")
            continue
        if not g or not g.get("entry"):
            continue
        text = json.dumps(g)
        out.append((key, ver, g, any(c in text for c in storage.FUNDAMENTAL_PANEL_COLS)))
    return out


def _done(conn, gen, window) -> set:
    return {(k, v, m) for k, v, m in conn.execute(
        "SELECT strategy_key, version, mode FROM survivorship_backtests WHERE generator=? AND window=?",
        (gen, json.dumps(list(window))))}


def _real(conn, cfg, window, fundamentals: bool) -> tuple:
    import storage
    from train_model import FEATURE_COLS
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"), min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True, include_open=True)
    if fundamentals and not df.empty:
        df = storage.attach_fundamentals(conn, df)
    end = (dt.date.fromisoformat(window[1]) + dt.timedelta(days=EXIT_MARGIN_DAYS)).isoformat()
    ex = storage.load_exit_prices(conn, df["ticker"].astype(str).unique(), window[0], end) if not df.empty \
        else pd.DataFrame(columns=["ticker", "date", "close", "open"])
    return df, ex


def _combine(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    if b is None or b.empty:
        return a
    out = pd.concat([a.assign(ticker=a["ticker"].astype(str)), b.assign(ticker=b["ticker"].astype(str))],
                    ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out["ticker"] = out["ticker"].astype("category")
    return out


def run(conn, cfg, only: list | None = None) -> dict:
    """Compute every missing (strategy, mode) for the current generator and window. Resumable."""
    import bias_exposure as bias
    import costs as costs_mod
    import simulator
    init(conn)
    gen = generator()
    if gen is None:
        raise SystemExit("no synthetic build — run universe_synthetic.py --build first")
    window = window_of(cfg)
    wkey = json.dumps(list(window))
    todo = [s for s in (only or strategies(conn))]
    done = _done(conn, gen, window)
    size = float(cfg["risk"]["position_size_usd"])
    cap = int((cfg.get("factory") or {}).get("max_entries_per_backtest", 5000))
    cm = costs_mod.CostModel(cfg)
    wrote = 0
    for fund in (False, True):                       # one real panel at a time keeps memory bounded
        group = [s for s in todo if s[3] == fund]
        if not any((k, v, m) not in done for k, v, _, _ in group for m in MODES):
            continue
        real, real_ex = _real(conn, cfg, window, fund)
        if real.empty:
            log.warning(f"empty real panel for {window}")
            continue
        for mode in MODES:
            pending = [s for s in group if (s[0], s[1], mode) not in done]
            if not pending:
                continue
            if mode == "exclude":
                df, ex = real, real_ex
            else:
                srows, sex = synthetic_frames(conn, cfg, window, mode)
                df, ex = _combine(real, srows), _combine(real_ex, sex)
            panel = simulator.Panel(df, exit_prices=ex)
            dd = bias.drawdown_column(panel.df)
            is_syn = panel.df["ticker"].astype(str).str.startswith(PREFIX).to_numpy()
            for key, ver, g, _ in pending:
                try:
                    r = simulator.simulate(g, panel, cm, size, max_entries=cap)
                except Exception as e:                           # noqa: BLE001
                    log.warning(f"{key} v{ver} {mode}: {type(e).__name__}: {e}")
                    continue
                n = int(r.get("n_trades") or 0)
                rows = np.asarray(r.get("entry_rows", []), dtype=int)
                conn.execute("INSERT OR REPLACE INTO survivorship_backtests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (key, ver, mode, gen, wkey, n, int(is_syn[rows].sum()) if n else 0,
                              float(r.get("gross_pnl_usd") or 0), float(r.get("costs_usd") or 0),
                              float(r.get("net_pnl_usd") or 0),
                              (float(r["net_pnl_usd"]) / n / size) if n else None,
                              bias.exposure(r, dd)["share_deep"] if n else None,
                              datetime.now(timezone.utc).isoformat(timespec="seconds")))
                conn.commit()
                wrote += 1
                log.info(f"{key} v{ver} {mode}: {n:,} trades ({int(is_syn[rows].sum()) if n else 0} synthetic) "
                         f"net ${float(r.get('net_pnl_usd') or 0):,.2f}")
            # Release this mode's combined frames BEFORE the next mode builds its own:
            # holding both (real + synthetic, twice) exceeded the 6 GB cap (exit 137,
            # 2026-09-25). `real` stays; everything derived from it goes.
            del panel, dd, is_syn, df, ex
            if mode != "exclude":
                del srows, sex
            gc.collect()
        del real, real_ex
        gc.collect()
    return {"generator": gen, "window": list(window), "strategies": len(todo), "rows_written": wrote}


# --- read side, for ranking.py ------------------------------------------------------

def result(conn, key: str, version: int, mode: str) -> dict | None:
    """The newest result for (strategy, mode) under the current generator, or None."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='survivorship_backtests'").fetchone():
        return None
    gen = generator()
    if gen is None:
        return None
    cur = conn.execute("SELECT * FROM survivorship_backtests WHERE strategy_key=? AND version=? AND mode=? "
                       "AND generator=? ORDER BY computed_at DESC LIMIT 1", (key, version, mode, gen))
    r = cur.fetchone()
    return dict(zip([c[0] for c in cur.description], r)) if r else None


def render(conn) -> str:
    init(conn)
    gen = generator()
    rows = conn.execute("SELECT strategy_key, version, mode, trades, synthetic_trades, gross_usd, costs_usd, "
                        "net_usd, per_trade, share_deep FROM survivorship_backtests WHERE generator=? "
                        "ORDER BY strategy_key, version, mode", (gen,)).fetchall()
    by = {}
    for r in rows:
        by.setdefault((r[0], r[1]), {})[r[2]] = r
    L = ["", f"  SURVIVORSHIP BACKTESTS — {gen}",
         f"  {'strategy':<34}{'mode':<9}{'trades':>7}{'synth':>6}{'gross':>9}{'costs':>8}{'net':>9}"
         f"{'per trade':>10}{'deep':>6}"]
    for (k, v), modes in by.items():
        for m in MODES:
            r = modes.get(m)
            if not r:
                continue
            pt = "     —" if r[8] is None else f"{r[8]:+.2%}"
            deep = "  —" if r[9] is None else f"{r[9]:.0%}"
            L.append(f"  {(k + ' v' + str(v))[:33]:<34}{m:<9}{r[3]:>7,}{r[4]:>6}{r[5]:>9.2f}{-r[6]:>8.2f}"
                     f"{r[7]:>9.2f}{pt:>10}{deep:>6}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Backtests including synthetic dead companies.")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    runtime.be_nice()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    if a.run:
        print(json.dumps(run(conn, cfg), indent=1))
    if a.report or not a.run:
        print(render(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
