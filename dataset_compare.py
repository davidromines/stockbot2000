"""
Cross-dataset validation: the primary database against FINSABER.

The primary database is survivorship-biased — 22.6% of the knowable 2008
universe is priceable here — and FINSABER is the only series this project holds
that kept the companies that died. Comparing the two is how the size of that
bias gets measured rather than asserted.

Two rules govern everything in this module.

**Discrepancies are reported, never reconciled.** Addendum B §B19: a comparison
that silently drops the rows it cannot explain is worse than no comparison,
because it produces a clean number that means nothing. Every mismatch is
counted, sampled and stored.

**The two datasets are never merged.** They have different adjustment
conventions and different universes. A strategy is run on each separately and
the two results are compared; a frame built from both would be neither series
and every number derived from it would be uninterpretable.

Nothing here writes to `prices`, `features` or `fundamentals`. The only tables
this module creates are its own two.
"""
import runtime  # noqa: F401  — must precede numpy/pandas

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import costs
import data_providers as dp
import features as feat
import simulator as sim
from universe import load_config

log = logging.getLogger("dataset_compare")

# Ratios within this relative distance of a split factor are counted as
# corporate-action candidates rather than as price errors. 2% is loose enough to
# catch a split applied on a slightly different ex-date and tight enough that
# ordinary price disagreement does not land in the bucket.
SPLIT_TOLERANCE = 0.02
SPLIT_FACTORS = [2, 3, 4, 5, 6, 7, 8, 10, 15, 20,
                 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 7, 1 / 8, 1 / 10,
                 1 / 15, 1 / 20]

# Volume is a coarser series than price — different vendors aggregate odd lots
# and dark pool prints differently — so the threshold is deliberately wide.
VOLUME_TOLERANCE = 0.05
# Daily-return disagreement above 0.5 percentage points is a data difference;
# below it is rounding and adjustment-factor precision.
RETURN_TOLERANCE = 0.005
# A per-ticker level ratio moving more than 2% within a window.
LEVEL_DRIFT_TOLERANCE = 0.02

# Feature warm-up. compute_features_for_ticker needs 210 rows before it returns
# anything, and the longest indicator window is 252 sessions, so the fetch has
# to start well before the requested window or every early row is NaN.
WARMUP_DAYS = 300
# Forward bars for exits. MAX_HOLD_CAP is 60 sessions; 120 calendar days covers
# that with room for holidays.
TAIL_DAYS = 120

MAX_EXAMPLES = 50
MAX_WORST = 20
MAX_COVERAGE_ROWS = 200


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def init(conn: sqlite3.Connection) -> None:
    """Create this module's two tables if absent. Safe to call on every run."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dataset_comparisons (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            at             TEXT,
            primary_name   TEXT,
            secondary_name TEXT,
            start          TEXT,
            end            TEXT,
            report         TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cross_validations (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            at                  TEXT,
            strategy_key        TEXT,
            version             INTEGER,
            start               TEXT,
            end                 TEXT,
            report              TEXT,
            survivorship_status TEXT,
            data_confidence     REAL
        )
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _json_default(o):
    """numpy scalars are not JSON-serialisable and appear throughout the reports."""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def store_comparison(conn: sqlite3.Connection, report: dict) -> int:
    init(conn)
    cur = conn.execute(
        "INSERT INTO dataset_comparisons (at, primary_name, secondary_name, "
        "start, end, report) VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), report.get("datasets", {}).get("primary"),
         report.get("datasets", {}).get("secondary"),
         report.get("date_range", {}).get("start"),
         report.get("date_range", {}).get("end"),
         json.dumps(report, default=_json_default)))
    conn.commit()
    return int(cur.lastrowid)


def store_cross_validation(conn: sqlite3.Connection, key: str, version: int,
                           report: dict, status: str) -> int:
    init(conn)
    cur = conn.execute(
        "INSERT INTO cross_validations (at, strategy_key, version, start, end, "
        "report, survivorship_status, data_confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_now(), key, int(version) if version is not None else None,
         report.get("start"), report.get("end"),
         json.dumps(report, default=_json_default), status,
         report.get("data_confidence")))
    conn.commit()
    return int(cur.lastrowid)


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

def _bars_frame(provider: dp.DataProvider, tickers, start: str, end: str,
                adjusted: bool = False) -> pd.DataFrame:
    """
    Fetch and normalise. `daily_bars` already guarantees BAR_COLUMNS and string
    dates, but a provider that returns an empty frame with no columns would
    break every downstream merge, so the shape is re-asserted here.
    """
    # The primary `prices.close` is yfinance auto-adjusted, so it is compared
    # against a secondary's ADJUSTED close where the provider has one.
    fetch = getattr(provider, "adjusted_bars", None) if adjusted else None
    df = (fetch or provider.daily_bars)(tickers, start, end)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=dp.BAR_COLUMNS)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = df["ticker"].astype(str)
    return df


def _duplicate_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    return int(df.duplicated(subset=["ticker", "date"]).sum())


def _is_split_ratio(ratio: float) -> bool:
    if not np.isfinite(ratio) or ratio <= 0:
        return False
    return any(abs(ratio - f) / f <= SPLIT_TOLERANCE for f in SPLIT_FACTORS)


def compare(primary: dp.DataProvider, secondary: dp.DataProvider,
            start: str, end: str, tickers: list | None = None,
            price_tol: float = 0.01) -> dict:
    """
    Compare two providers over [start, end].

    `tickers` restricts the comparison to a set; None means every ticker each
    provider holds in the window. The two are fetched separately and joined on
    (ticker, date) — never concatenated, because a row present in only one
    dataset is a finding, not a gap to be filled.
    """
    p = _bars_frame(primary, tickers, start, end)
    s = _bars_frame(secondary, tickers, start, end, adjusted=True)

    p_tickers = set(p["ticker"].unique()) if not p.empty else set()
    s_tickers = set(s["ticker"].unique()) if not s.empty else set()
    both = p_tickers & s_tickers

    only_p = sorted(p_tickers - s_tickers)
    only_s = sorted(s_tickers - p_tickers)

    # --- per-(ticker, date) comparison on the common universe --------------
    pc = p[p["ticker"].isin(both)][["ticker", "date", "close", "volume"]]
    sc = s[s["ticker"].isin(both)][["ticker", "date", "close", "volume"]]

    # Duplicates are counted before the merge. A duplicated (ticker, date) in
    # either side would fan out the join and inflate every discrepancy count
    # below it, so the count is reported and the merge is done on de-duplicated
    # frames — the first occurrence wins, which is the conservative reading.
    dup_p = _duplicate_count(pc)
    dup_s = _duplicate_count(sc)
    if dup_p:
        log.warning(f"{dup_p} duplicate (ticker, date) rows in {primary.name()}")
        pc = pc.drop_duplicates(subset=["ticker", "date"], keep="first")
    if dup_s:
        log.warning(f"{dup_s} duplicate (ticker, date) rows in {secondary.name()}")
        sc = sc.drop_duplicates(subset=["ticker", "date"], keep="first")

    merged = pc.merge(sc, on=["ticker", "date"], how="outer",
                      suffixes=("_p", "_s"), indicator=True)

    missing_in_primary = int((merged["_merge"] == "right_only").sum())
    missing_in_secondary = int((merged["_merge"] == "left_only").sum())

    common = merged[merged["_merge"] == "both"].copy()
    common = common[np.isfinite(common["close_p"]) & np.isfinite(common["close_s"])
                    & (common["close_s"] > 0) & (common["close_p"] > 0)]
    common["ratio"] = common["close_p"] / common["close_s"]
    common["price_diff"] = (common["ratio"] - 1.0).abs()

    price_bad = common[common["price_diff"] > price_tol]
    n_price_disc = int(len(price_bad))

    # A ratio sitting on a split factor is a corporate-action mismatch, not a
    # data error: the two vendors applied the same split on different dates or
    # adjusted one series and not the other. Counted separately so the price
    # discrepancy count is not dominated by a handful of split names.
    ca_mask = price_bad["ratio"].map(_is_split_ratio)
    n_ca = int(ca_mask.sum())

    worst = (price_bad.sort_values("price_diff", ascending=False)
             .head(MAX_WORST)[["ticker", "date", "close_p", "close_s", "ratio"]])
    worst_rows = [
        {"ticker": r.ticker, "date": r.date, "close_p": float(r.close_p),
         "close_s": float(r.close_s), "ratio": float(r.ratio)}
        for r in worst.itertuples(index=False)
    ]

    # Daily returns — the test that means something across vendors. Two
    # dividend-adjusted series anchored at different download dates differ in
    # LEVEL by a per-ticker factor while agreeing on every return; measured
    # 2026-09-24 against FINSABER, 99.5% of returns agree within 0.1pp while
    # only ~26% of levels sit within 1%. A level difference is reported above
    # for completeness; a return difference is a data disagreement.
    common = common.sort_values(["ticker", "date"])
    grp = common.groupby("ticker")
    ret_diff = (grp["close_p"].pct_change() - grp["close_s"].pct_change()).abs().dropna()
    n_ret = int(len(ret_diff))
    n_ret_disc = int((ret_diff > RETURN_TOLERANCE).sum())
    # A level ratio that drifts within the window is either a missed corporate
    # action or a ticker reused by a different company (PARA, UPC).
    drift = grp["ratio"].agg(lambda x: x.max() / x.min() - 1.0)
    drifting = drift[drift > LEVEL_DRIFT_TOLERANCE].sort_values(ascending=False)

    # Volume: relative difference, guarded against a zero denominator. A zero
    # volume on one side and a real one on the other is a discrepancy, not a
    # division by zero.
    vol = common[np.isfinite(common["volume_p"]) & np.isfinite(common["volume_s"])].copy()
    denom = np.maximum(vol["volume_p"].abs(), vol["volume_s"].abs())
    vol_diff = np.where(denom > 0, (vol["volume_p"] - vol["volume_s"]).abs() / denom, 0.0)
    n_vol_disc = int((vol_diff > VOLUME_TOLERANCE).sum())

    # --- coverage by year --------------------------------------------------
    coverage_by_year: dict = {}
    for label, frame in (("primary", p), ("secondary", s)):
        if frame.empty:
            continue
        years = pd.to_datetime(frame["date"]).dt.year
        for year, grp in frame.assign(_year=years).groupby("_year"):
            entry = coverage_by_year.setdefault(int(year), {"primary": 0, "secondary": 0, "both": 0})
            entry[label] = int(grp["ticker"].nunique())
    if not p.empty and not s.empty:
        py = p[p["ticker"].isin(both)].assign(_year=pd.to_datetime(p["date"]).dt.year)
        sy = s[s["ticker"].isin(both)].assign(_year=pd.to_datetime(s["date"]).dt.year)
        for year in set(py["_year"]).intersection(set(sy["_year"])):
            entry = coverage_by_year.setdefault(int(year), {"primary": 0, "secondary": 0, "both": 0})
            entry["both"] = int(len(set(py[py["_year"] == year]["ticker"])
                                   & set(sy[sy["_year"] == year]["ticker"])))

    # --- coverage by security ---------------------------------------------
    coverage_by_security = []
    if both:
        pg = p[p["ticker"].isin(both)].groupby("ticker")["date"]
        sg = s[s["ticker"].isin(both)].groupby("ticker")["date"]
        p_stats = pg.agg(["count", "min", "max"])
        s_stats = sg.agg(["count", "min", "max"])
        for t in sorted(both)[:MAX_COVERAGE_ROWS]:
            pr = p_stats.loc[t] if t in p_stats.index else None
            sr = s_stats.loc[t] if t in s_stats.index else None
            coverage_by_security.append({
                "ticker": t,
                "bars_primary": int(pr["count"]) if pr is not None else 0,
                "bars_secondary": int(sr["count"]) if sr is not None else 0,
                "first_primary": pr["min"] if pr is not None else None,
                "last_primary": pr["max"] if pr is not None else None,
                "first_secondary": sr["min"] if sr is not None else None,
                "last_secondary": sr["max"] if sr is not None else None,
            })

    return {
        "datasets": {"primary": primary.name(), "secondary": secondary.name()},
        "date_range": {"start": start, "end": end},
        "securities_primary": len(p_tickers),
        "securities_secondary": len(s_tickers),
        "securities_both": len(both),
        "only_in_primary": {"count": len(only_p), "examples": only_p[:MAX_EXAMPLES]},
        "only_in_secondary": {"count": len(only_s), "examples": only_s[:MAX_EXAMPLES]},
        "bars_primary": int(len(p)),
        "bars_secondary": int(len(s)),
        "missing_bars_in_primary": missing_in_primary,
        "missing_bars_in_secondary": missing_in_secondary,
        "duplicate_bars_primary": dup_p,
        "duplicate_bars_secondary": dup_s,
        "returns_compared": n_ret,
        "return_discrepancies": n_ret_disc,
        "return_agreement": round(1 - n_ret_disc / n_ret, 4) if n_ret else None,
        "level_drift_tickers": {"count": int(len(drifting)),
                                "examples": {t: round(float(v), 3)
                                             for t, v in drifting.head(MAX_EXAMPLES).items()}},
        "price_discrepancies": n_price_disc,
        "corporate_action_candidates": n_ca,
        "volume_discrepancies": n_vol_disc,
        "worst_price_discrepancies": worst_rows,
        "coverage_by_year": coverage_by_year,
        "coverage_by_security": coverage_by_security,
        "price_tolerance": price_tol,
        "return_tolerance": RETURN_TOLERANCE,
        "volume_tolerance": VOLUME_TOLERANCE,
    }


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------

def provider_panel(provider: dp.DataProvider, tickers, start: str, end: str):
    """
    Build a simulator.Panel from a provider, or None if nothing is usable.

    The fetch window is wider than the requested one on both sides. Before
    `start` because every indicator needs history — a 200-day SMA is NaN for the
    first 200 rows, and compute_features_for_ticker returns nothing at all below
    210 rows. After `end` because exits fill on the bar following the trigger and
    a position opened on the last day needs forward bars to close against.

    `exit_prices` is the FULL fetched frame, not the windowed one. The simulator
    prices exits off the unfiltered series deliberately (see Panel.__init__): a
    position already open must be priced wherever it goes, including below the
    tradeability floor. Passing the windowed frame here would reintroduce the
    truncation defect that was fixed once already.
    """
    if tickers is not None:
        tickers = list(tickers)
        if not tickers:
            return None

    fetch_start = (pd.Timestamp(start) - timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
    fetch_end = (pd.Timestamp(end) + timedelta(days=TAIL_DAYS)).strftime("%Y-%m-%d")

    bars = _bars_frame(provider, tickers, fetch_start, fetch_end)
    if bars.empty:
        log.warning(f"{provider.name()}: no bars in {fetch_start}..{fetch_end}")
        return None

    # Features are computed per ticker on that ticker's own contiguous history.
    # Computing them on the concatenated frame would let one ticker's last close
    # leak into the next ticker's first rolling window.
    parts = []
    for _, group in bars.groupby("ticker", sort=False):
        computed = feat.compute_features_for_ticker(group)
        if computed is None or len(computed) == 0:
            continue
        parts.append(computed)
    if not parts:
        log.warning(f"{provider.name()}: no ticker had enough history for features")
        return None

    full = pd.concat(parts, ignore_index=True)
    full["date"] = pd.to_datetime(full["date"]).dt.strftime("%Y-%m-%d")

    window = full[(full["date"] >= start) & (full["date"] <= end)].copy()
    if window.empty:
        log.warning(f"{provider.name()}: no feature rows inside {start}..{end}")
        return None

    # exit_prices needs ticker, date, close, open. `full` carries all four.
    exit_prices = full[["ticker", "date", "close", "open"]].copy()
    return sim.Panel(window, exit_prices=exit_prices)


# --------------------------------------------------------------------------
# Cross-validation
# --------------------------------------------------------------------------

def _max_drawdown(pnl: np.ndarray) -> float:
    """
    Max drawdown of the cumulative per-trade net P&L, in dollars.

    Positive number. Computed on the trade sequence in the order the simulator
    returned it, which is entry order — the same order the ledger would replay.
    """
    if pnl is None or len(pnl) == 0:
        return 0.0
    equity = np.cumsum(np.asarray(pnl, dtype="float64"))
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity)) if len(equity) else 0.0


def _sharpe(pnl: np.ndarray) -> float:
    """
    Per-trade Sharpe: mean/std of net P&L, scaled by sqrt(n_trades).

    Zero when undefined — fewer than two trades, or zero dispersion. Returning
    NaN would propagate into every downstream comparison and turn a missing
    measurement into a poisoned one.
    """
    if pnl is None or len(pnl) < 2:
        return 0.0
    pnl = np.asarray(pnl, dtype="float64")
    sd = float(np.std(pnl, ddof=1))
    if not np.isfinite(sd) or sd == 0:
        return 0.0
    return float(np.mean(pnl) / sd * np.sqrt(len(pnl)))


def _run(provider: dp.DataProvider, genome: dict, tickers, start: str, end: str,
         cost_model, size: float, max_entries: int | None) -> dict:
    panel = provider_panel(provider, tickers, start, end)
    if panel is None:
        return {"net_pnl_usd": 0.0, "gross_pnl_usd": 0.0, "costs_usd": 0.0,
                "n_trades": 0, "win_rate": 0.0, "pnl_series": np.array([]),
                "securities": 0}
    result = sim.simulate(genome, panel, cost_model, size, max_entries=max_entries)
    result["securities"] = int(panel.df["ticker"].nunique())
    return result


def _tickers_with_bars(provider: dp.DataProvider, tickers, start: str, end: str) -> set:
    """
    The tickers a provider actually returns bars for in the window.

    Fetched over the same widened window provider_panel uses, because a ticker
    with no bars inside [start, end] but plenty before it still contributes
    nothing to the panel — and a ticker whose only bars are in the warm-up is
    not a ticker the strategy can trade. Using the widened window here would
    overstate the intersection; using the narrow one would understate it for a
    ticker whose first tradeable bar sits just after `start`. The narrow window
    is the conservative reading: it counts only tickers that can actually be
    traded inside the requested period.
    """
    if tickers is not None:
        tickers = list(tickers)
        if not tickers:
            return set()
    bars = _bars_frame(provider, tickers, start, end)
    if bars.empty:
        return set()
    return set(bars["ticker"].unique())


def cross_validate(primary: dp.DataProvider, secondary: dp.DataProvider,
                   genome: dict, start: str, end: str, tickers,
                   cfg: dict | None = None, size: float = 20.0,
                   max_entries: int | None = 5000) -> dict:
    """
    Run one genome on both datasets over the SAME tickers.

    The ticker set is the intersection of what each provider actually returns
    bars for in the window — not the intersection of their declared universes,
    and not the requested list. Running each side on its own universe would
    confound the survivorship question with a universe difference: the secondary
    would look better simply for holding more names, which is the finding we are
    trying to measure rather than assume. A ticker that exists in both datasets
    but has no bars in one of them is the same problem in miniature, so the
    intersection is taken on observed bars.

    The tickers dropped from each side are reported rather than discarded. A
    comparison that quietly narrows its own universe produces a clean number
    that means nothing (Addendum B §B19).
    """
    cfg = cfg or {}
    cost_model = costs.CostModel(cfg)

    if tickers is None:
        p_t = set(primary.universe(end))
        s_t = set(secondary.universe(end))
        requested = sorted(p_t | s_t)
    else:
        requested = sorted(set(tickers))

    p_have = _tickers_with_bars(primary, requested, start, end)
    s_have = _tickers_with_bars(secondary, requested, start, end)
    common = sorted(p_have & s_have)

    only_primary = sorted(p_have - s_have)
    only_secondary = sorted(s_have - p_have)

    if not common:
        log.warning("cross_validate: no tickers with bars in both providers")

    p_res = _run(primary, genome, common, start, end, cost_model, size, max_entries)
    s_res = _run(secondary, genome, common, start, end, cost_model, size, max_entries)

    net_p = float(p_res["net_pnl_usd"])
    net_s = float(s_res["net_pnl_usd"])
    n_p = int(p_res["n_trades"])
    n_s = int(s_res["n_trades"])
    wr_p = float(p_res["win_rate"])
    wr_s = float(s_res["win_rate"])
    dd_p = _max_drawdown(p_res["pnl_series"])
    dd_s = _max_drawdown(s_res["pnl_series"])
    sh_p = _sharpe(p_res["pnl_series"])
    sh_s = _sharpe(s_res["pnl_series"])

    # Confidence is agreement between the two runs, not the size of either. A
    # strategy that makes $500 on one dataset and $5 on the other is not
    # confirmed by the larger number; it is contradicted by the smaller one.
    denom = max(abs(net_p), abs(net_s), 1.0)
    confidence = round(1.0 - min(1.0, abs(net_p - net_s) / denom), 3)

    return {
        "start": start,
        "end": end,
        "tickers": len(common),
        "only_primary_tickers": only_primary,
        "only_secondary_tickers": only_secondary,
        "net_primary": net_p,
        "net_secondary": net_s,
        "return_difference_usd": net_p - net_s,
        "trades_primary": n_p,
        "trades_secondary": n_s,
        "trade_count_difference": n_p - n_s,
        "win_rate_primary": wr_p,
        "win_rate_secondary": wr_s,
        "win_rate_difference": wr_p - wr_s,
        "max_drawdown_primary": dd_p,
        "max_drawdown_secondary": dd_s,
        "drawdown_difference": dd_p - dd_s,
        "sharpe_primary": sh_p,
        "sharpe_secondary": sh_s,
        "sharpe_difference": sh_p - sh_s,
        "securities_primary": int(p_res["securities"]),
        "securities_secondary": int(s_res["securities"]),
        "security_coverage_difference": int(p_res["securities"]) - int(s_res["securities"]),
        "data_confidence": confidence,
        # Read off the provider, not inferred from the numbers. Whether a
        # dataset kept delisted names is a property of how it was built, and
        # guessing it from a return difference is how a survivorship tag becomes
        # a restatement of the result it is supposed to qualify.
        "secondary_includes_delisted": bool(getattr(secondary, "includes_delisted", False)),
    }


def survivorship_status(cross: dict | None, haircut_applied: bool = False) -> str:
    """
    Tag a result by how much survivorship bias it is exposed to.

    UNKNOWN when there is no cross-validation at all — the honest answer, and
    the one that stops an untested strategy from being labelled SAFE by default.
    """
    if cross is None:
        return "UNKNOWN"
    if (cross.get("secondary_includes_delisted") is True
            and cross.get("net_secondary", 0.0) > 0
            and cross.get("data_confidence", 0.0) >= 0.5):
        return "SURVIVORSHIP_SAFE"
    if haircut_applied:
        return "SURVIVORSHIP_ADJUSTED"
    return "SURVIVORSHIP_LIMITED"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _primary_connection(cfg: dict) -> sqlite3.Connection:
    path = cfg["data"].get("database", "data/market_data.db")
    conn = sqlite3.connect(path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    return conn


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cross-dataset validation")
    ap.add_argument("--compare", action="store_true",
                    help="compare the primary database against FINSABER")
    ap.add_argument("--start", required=False, help="window start, YYYY-MM-DD")
    ap.add_argument("--end", required=False, help="window end, YYYY-MM-DD")
    ap.add_argument("--db", default="data/finsaber.db",
                    help="FINSABER SQLite file (default data/finsaber.db)")
    ap.add_argument("--tickers", default=None,
                    help="comma-separated ticker subset")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    if not args.compare:
        ap.print_help()
        return 1

    if not args.start or not args.end:
        print("error: --compare requires --start and --end", file=sys.stderr)
        return 2

    if not os.path.exists(args.db):
        print("FINSABER not imported yet — run finsaber.py --import PATH")
        return 0

    cfg = load_config()
    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
               if args.tickers else None)

    import finsaber

    conn = _primary_connection(cfg)
    try:
        primary = dp.StockbotProvider(conn)
        secondary = finsaber.FinsaberProvider(args.db)
        report = compare(primary, secondary, args.start, args.end, tickers=tickers)
        store_comparison(conn, report)
    finally:
        conn.close()

    print(f"level_drift_tickers: {report['level_drift_tickers']}")
    for k in ("datasets", "date_range", "securities_primary", "securities_secondary",
              "securities_both", "bars_primary", "bars_secondary",
              "missing_bars_in_primary", "missing_bars_in_secondary",
              "duplicate_bars_primary", "duplicate_bars_secondary",
              "returns_compared", "return_discrepancies", "return_agreement",
              "price_discrepancies", "corporate_action_candidates",
              "volume_discrepancies"):
        print(f"{k}: {report[k]}")
    print(f"only_in_primary: {report['only_in_primary']['count']}")
    print(f"only_in_secondary: {report['only_in_secondary']['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
