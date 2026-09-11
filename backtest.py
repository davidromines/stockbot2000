"""
Backtests the full strategy (score >= threshold -> enter, ATR/fixed stop-loss
-> exit, or horizon timeout -> exit) over historical data, using the trained
model to score each historical day out-of-sample-ish (note caveat below).

This is a SIMPLE walk-forward simulation, not a production-grade backtester:
- Position sizing fixed at risk.position_size_usd per entry.
- Enforces risk.max_open_positions concurrently.
- One entry per ticker at a time (no pyramiding).
Out-of-sample enforcement: train_model.py writes models/split.json recording
the held-out date range. This script simulates ONLY from test_start onward and
refuses to run without that file. Backtesting across the training period is what
produced the earlier 97.9% win rate, which was leakage, not performance.

Still not production-grade: no costs, no slippage, no liquidity floor. Those are
phase 07. Results are an optimistic ceiling even when the dates are honest.

Usage: python backtest.py --threshold 70
"""
import runtime  # noqa: F401  — must precede numpy/pandas/xgboost
import argparse
import json
import logging
import os

import pandas as pd
import xgboost as xgb

import costs as costs_mod
import storage

from train_model import FEATURE_COLS
from stop_loss import calculate_stop_loss
from universe import load_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("backtest")


def load_split(cfg: dict) -> dict:
    """
    Read the held-out date range written by train_model.py.

    Hard failure rather than a warning if it is missing. A backtest that quietly
    replays the training period returns a number that looks like performance and
    is not — which is exactly the failure this file used to have.
    """
    path = cfg["model"].get("split_metadata_path", "models/split.json")
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} not found. Run train_model.py first — without it this "
            f"backtest would score the training period and report leakage as profit."
        )
    with open(path) as f:
        return json.load(f)


def apply_survivorship_haircut(trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Deduct the measured survivorship overstatement from every trade.

    Our universe contains only companies still listed today, so its returns are
    inflated by everything that failed. `bias_benchmark.py` measured that against
    CRSP at 9.68% of excess compounding per year.

    Charged per trade in proportion to how long the position was actually held,
    rather than as a flat deduction: a two-day trade should not carry the same
    correction as a two-month one.

    This is a correction, not a fix. The delisted companies are still missing, and
    the figure is an upper bound because it also contains CRSP's microcap and OTC
    coverage that a directory-built universe never had. Treat adjusted numbers as
    less wrong, not as right.
    """
    scfg = cfg.get("survivorship", {})
    if not scfg.get("enabled", False):
        trades["pnl_pct_adj"] = trades["pnl_pct"]
        return trades

    annual = float(scfg.get("excess_return_pct_per_year", 0.0)) / 100.0
    held = (pd.to_datetime(trades["exit_date"]) - pd.to_datetime(trades["entry_date"])).dt.days
    held = held.clip(lower=1)
    drag_pct = ((1 + annual) ** (held / 365.0) - 1) * 100.0

    trades["survivorship_drag_pct"] = drag_pct
    trades["pnl_pct_adj"] = trades["pnl_pct"] - drag_pct
    return trades


def run_backtest(threshold: float, cfg: dict) -> dict:
    split = load_split(cfg)

    conn = storage.connect(cfg["database"]["market_data_path"])
    features = storage.load_training_frame(
        conn, FEATURE_COLS,
        types=cfg["universe"]["tradeable_types"],
        start_date=split["test_start"], end_date=split["test_end"],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True,
    )

    log.info(f"Out-of-sample only: {split['test_start']} -> {split['test_end']} "
             f"({len(features):,} rows, {features['ticker'].nunique():,} tickers)")
    if features.empty:
        raise SystemExit("No feature rows in the held-out period — retrain first.")

    features = features.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Exits price off the UNFILTERED table. Floors gate entries only — a position
    # already open must still be priced on days the name dips below them.
    price_lookup = storage.price_series(
        conn, sorted(features["ticker"].astype(str).unique()),
        split["test_start"], split["test_end"])
    log.info(f"Exit price lookup: {len(price_lookup):,} unfiltered bars")
    conn.close()

    model = xgb.XGBClassifier()
    model.load_model(cfg["model"]["path"])

    features["score"] = model.predict_proba(features[FEATURE_COLS])[:, 1] * 100

    horizon = cfg["labeling"]["horizon_days"]
    max_positions = cfg["risk"]["max_open_positions"]
    position_size = cfg["risk"]["position_size_usd"]

    # top_n fills the open slots with the best available each day. A fixed cutoff
    # selected nothing at all: see config.yaml and the note in CLAUDE.md.
    cost_model = costs_mod.CostModel(cfg)
    log.info(cost_model.describe())
    mode = cfg["risk"].get("selection_mode", "top_n")
    min_score = threshold if mode == "threshold" else cfg["risk"].get("min_score")
    log.info(f"Selection: {mode}"
             + (f", floor {min_score}" if min_score is not None else ", no score floor"))

    trades = []
    open_positions = {}  # ticker -> dict(entry_date, entry_price, stop_price, days_held)

    for date, day_df in features.groupby("date"):
        # 1. check exits first
        for ticker in list(open_positions.keys()):
            pos = open_positions[ticker]
            pos["days_held"] += 1          # the clock runs whether or not we can price it
            price = price_lookup.get((str(ticker), str(date)[:10]))
            if price is None:
                if pos["days_held"] >= horizon * 4:
                    del open_positions[ticker]   # no prices at all: abandon, do not hold forever
                continue
            exit_reason = None
            if price <= pos["stop_price"]:
                exit_reason = "stop_loss"
            elif pos["days_held"] >= horizon:
                exit_reason = "horizon_timeout"

            if exit_reason:
                pnl_pct = (price / pos["entry_price"] - 1) * 100
                shares = position_size / pos["entry_price"] if pos["entry_price"] else 0.0
                gross = position_size * (pnl_pct / 100)
                cost = cost_model.round_trip(position_size, pos["dollar_volume"], shares)
                trades.append({
                    "ticker": ticker, "entry_date": pos["entry_date"], "exit_date": date,
                    "entry_price": pos["entry_price"], "exit_price": price,
                    "shares": shares,
                    "gross_pnl_usd": gross, "costs_usd": cost,
                    "net_pnl_usd": gross - cost,
                    "pnl_usd": gross, "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason,
                })
                del open_positions[ticker]

        # 2. check new entries (only if room available)
        if len(open_positions) < max_positions:
            candidates = day_df[~day_df["ticker"].isin(open_positions)]
            if min_score is not None:
                candidates = candidates[candidates["score"] >= min_score]
            candidates = candidates.sort_values("score", ascending=False)
            slots_open = max_positions - len(open_positions)
            for _, row in candidates.head(slots_open).iterrows():
                stop_price = calculate_stop_loss(row["close"], row.get("atr_14"), cfg)
                open_positions[row["ticker"]] = {
                    "entry_date": date, "entry_price": row["close"],
                    "stop_price": stop_price, "days_held": 0,
                    # Liquidity on the entry bar drives the spread estimate.
                    "dollar_volume": float(row.get("dollar_volume_20") or 0.0),
                }

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df = apply_survivorship_haircut(trades_df, cfg)
    if trades_df.empty:
        log.warning("No trades generated at this threshold.")
        return {"threshold": threshold, "num_trades": 0}

    # --- P&L first. Everything else is diagnostics. ---------------------
    survivorship = trades_df["survivorship_drag_pct"] * position_size / 100 \
        if "survivorship_drag_pct" in trades_df else 0.0
    trades_df["net_pnl_usd"] = trades_df["net_pnl_usd"] - survivorship
    trades_df["costs_usd"] = trades_df["costs_usd"] + survivorship

    surv_usd = float(survivorship.sum()) if hasattr(survivorship, "sum") else 0.0
    gross = float(trades_df["gross_pnl_usd"].sum())
    cost = float(trades_df["costs_usd"].sum())
    trading_cost = cost - surv_usd
    net = float(trades_df["net_pnl_usd"].sum())
    capital = position_size * max_positions

    curve = trades_df.sort_values("exit_date")["net_pnl_usd"].cumsum() + capital
    dd = storage.max_drawdown_pct(curve)

    summary = {
        "NET P&L (USD)": round(net, 2),
        "NET P&L (% of capital)": round(net / capital * 100, 1) if capital else None,
        "verdict": "PROFITABLE" if net > 0 else "LOSS",
        "": "",
        "gross_pnl_usd": round(gross, 2),
        "trading_costs_usd": round(trading_cost, 2),
        "survivorship_haircut_usd": round(surv_usd, 2),
        "net_before_survivorship_usd": round(gross - trading_cost, 2),
        "trading_cost_share_of_gross_pct": round(trading_cost / gross * 100, 1) if gross > 0 else None,
        "capital_at_risk_usd": capital,
        "num_trades": len(trades_df),
        "win_rate_pct": round((trades_df["net_pnl_usd"] > 0).mean() * 100, 1),
        "avg_net_pnl_usd_per_trade": round(net / len(trades_df), 4),
        "max_drawdown_pct": round(dd, 1),
        "avg_days_held": round((pd.to_datetime(trades_df["exit_date"])
                                - pd.to_datetime(trades_df["entry_date"])).dt.days.mean(), 1),
        "stopped_out_pct": round((trades_df["exit_reason"] == "stop_loss").mean() * 100, 1),
        "period": f"{split['test_start']} -> {split['test_end']} (out-of-sample)",
        "selection": mode if mode != "threshold" else f"threshold {threshold}",
    }
    summary["_trades"] = trades_df
    summary["_capital"] = capital
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=70.0)
    parser.add_argument("--name", help="Record this run in the experiment ledger under this name.")
    args = parser.parse_args()

    cfg = load_config()
    result = run_backtest(args.threshold, cfg)

    trades = result.pop("_trades", None)
    capital = result.pop("_capital", None)

    print("\n=== Backtest Summary ===")
    for k, v in result.items():
        print(f"{k}: {v}" if k else "")

    if trades is not None and args.name:
        conn = storage.connect(cfg["database"]["market_data_path"])
        storage.init_db(conn)
        storage.record_experiment(conn, {
            "id": f"bt:{args.name}",
            "name": args.name,
            "kind": "backtest",
            "config": json.dumps({"risk": cfg["risk"], "labeling": cfg["labeling"],
                                  "costs": cfg["costs"], "model": cfg["model"].get("path")}),
            "period_start": result["period"].split(" ")[0],
            "period_end": result["period"].split(" ")[2],
            "n_trades": result["num_trades"],
            "capital_usd": capital,
            "net_pnl_usd": result["NET P&L (USD)"],
            "net_pnl_pct": result["NET P&L (% of capital)"],
            "gross_pnl_usd": result["gross_pnl_usd"],
            "costs_usd": result["trading_costs_usd"] + result["survivorship_haircut_usd"],
            "win_rate_pct": result["win_rate_pct"],
            "max_drawdown_pct": result["max_drawdown_pct"],
            "avg_days_held": result["avg_days_held"],
            "notes": "survivorship haircut included in costs_usd",
        }, trades)
        conn.close()
        print(f"\nRecorded as experiment 'bt:{args.name}' — compare with experiments.py")
