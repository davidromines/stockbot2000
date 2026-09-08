"""
Backtests the full strategy (score >= threshold -> enter, ATR/fixed stop-loss
-> exit, or horizon timeout -> exit) over historical data, using the trained
model to score each historical day out-of-sample-ish (note caveat below).

This is a SIMPLE walk-forward simulation, not a production-grade backtester:
- Position sizing fixed at risk.position_size_usd per entry.
- Enforces risk.max_open_positions concurrently.
- One entry per ticker at a time (no pyramiding).
- Caveat: train_model.py trains on the full history including these dates
  (no strict train/test time split yet). Treat results as a sanity check of
  the strategy LOGIC, not a true out-of-sample performance estimate, until
  the "make it good" pass adds a proper walk-forward train/test split.

Usage: python backtest.py --threshold 70
"""
import argparse
import logging

import pandas as pd
import xgboost as xgb

from train_model import FEATURE_COLS
from stop_loss import calculate_stop_loss
from universe import load_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("backtest")


def run_backtest(threshold: float, cfg: dict) -> dict:
    features = pd.read_parquet(cfg["data"]["features_file"]).sort_values(["ticker", "date"])
    history = pd.read_parquet(cfg["data"]["history_file"])[["ticker", "date", "close"]]

    model = xgb.XGBClassifier()
    model.load_model(cfg["model"]["path"])

    features = features.dropna(subset=FEATURE_COLS).reset_index(drop=True)
    features["score"] = model.predict_proba(features[FEATURE_COLS])[:, 1] * 100

    price_lookup = history.set_index(["ticker", "date"])["close"].to_dict()
    horizon = cfg["labeling"]["horizon_days"]
    max_positions = cfg["risk"]["max_open_positions"]
    position_size = cfg["risk"]["position_size_usd"]

    trades = []
    open_positions = {}  # ticker -> dict(entry_date, entry_price, stop_price, days_held)

    for date, day_df in features.groupby("date"):
        # 1. check exits first
        for ticker in list(open_positions.keys()):
            pos = open_positions[ticker]
            price = price_lookup.get((ticker, date))
            if price is None:
                continue
            pos["days_held"] += 1
            exit_reason = None
            if price <= pos["stop_price"]:
                exit_reason = "stop_loss"
            elif pos["days_held"] >= horizon:
                exit_reason = "horizon_timeout"

            if exit_reason:
                pnl_pct = (price / pos["entry_price"] - 1) * 100
                trades.append({
                    "ticker": ticker, "entry_date": pos["entry_date"], "exit_date": date,
                    "entry_price": pos["entry_price"], "exit_price": price,
                    "pnl_usd": position_size * (pnl_pct / 100), "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason,
                })
                del open_positions[ticker]

        # 2. check new entries (only if room available)
        if len(open_positions) < max_positions:
            candidates = day_df[(day_df["score"] >= threshold) & (~day_df["ticker"].isin(open_positions))]
            candidates = candidates.sort_values("score", ascending=False)
            slots_open = max_positions - len(open_positions)
            for _, row in candidates.head(slots_open).iterrows():
                stop_price = calculate_stop_loss(row["close"], row.get("atr_14"), cfg)
                open_positions[row["ticker"]] = {
                    "entry_date": date, "entry_price": row["close"],
                    "stop_price": stop_price, "days_held": 0,
                }

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        log.warning("No trades generated at this threshold.")
        return {"threshold": threshold, "num_trades": 0}

    win_rate = (trades_df["pnl_pct"] > 0).mean()
    summary = {
        "threshold": threshold,
        "num_trades": len(trades_df),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_pnl_pct": round(trades_df["pnl_pct"].mean(), 2),
        "total_pnl_usd": round(trades_df["pnl_usd"].sum(), 2),
        "avg_days_held": round((pd.to_datetime(trades_df["exit_date"]) - pd.to_datetime(trades_df["entry_date"])).dt.days.mean(), 1),
        "stopped_out_pct": round((trades_df["exit_reason"] == "stop_loss").mean() * 100, 1),
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=70.0)
    args = parser.parse_args()

    cfg = load_config()
    result = run_backtest(args.threshold, cfg)
    print("\n=== Backtest Summary ===")
    for k, v in result.items():
        print(f"{k}: {v}")
