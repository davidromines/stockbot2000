"""
Loads the trained XGBoost model and scores the MOST RECENT day's feature
snapshot for every ticker in the universe. Outputs raw_scores.json:
[{ "ticker": "AAPL", "xgb_score": 82.4, "features": {...} }, ...]

This is the input to llm_report.py, which turns raw scores into the
plain-language scoresheet that gets handed to Claude.
"""
import runtime  # noqa: F401  — must precede numpy/pandas/xgboost
import json
import logging

import pandas as pd
import xgboost as xgb

import storage

from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("score")


def main():
    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    latest = storage.load_latest_features(
        conn, FEATURE_COLS,
        types=cfg["universe"]["tradeable_types"],
        max_staleness_days=cfg["scoresheet"].get("max_staleness_days", 5),
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
    )
    conn.close()

    if latest.empty:
        log.error("No scoreable tickers — is the database stale? Run backfill.py "
                  "then build_features.py.")
        return
    log.info(f"Scoring {len(latest):,} tickers as of {latest['date'].max()}")

    model = xgb.XGBClassifier()
    model.load_model(cfg["model"]["path"])

    probs = model.predict_proba(latest[FEATURE_COLS])[:, 1]
    latest["xgb_score"] = (probs * 100).round(1)

    results = []
    for _, row in latest.iterrows():
        results.append({
            "ticker": row["ticker"],
            "date": str(row["date"]),
            "xgb_score": float(row["xgb_score"]),
            "features": {col: (None if pd.isna(row[col]) else round(float(row[col]), 3)) for col in FEATURE_COLS},
        })

    results.sort(key=lambda r: r["xgb_score"], reverse=True)

    out_path = "data/raw_scores.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"Scored {len(results)} tickers. Saved to {out_path}. Top score: {results[0]['xgb_score'] if results else 'n/a'}")


if __name__ == "__main__":
    main()
