"""
Loads the trained XGBoost model and scores the MOST RECENT day's feature
snapshot for every ticker in the universe. Outputs raw_scores.json:
[{ "ticker": "AAPL", "xgb_score": 82.4, "features": {...} }, ...]

This is the input to llm_report.py, which turns raw scores into the
plain-language scoresheet that gets handed to Claude.
"""
import json
import logging

import pandas as pd
import xgboost as xgb

from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("score")


def main():
    cfg = load_config()
    features = pd.read_parquet(cfg["data"]["features_file"])

    latest = features.sort_values("date").groupby("ticker").tail(1).copy()
    latest = latest.dropna(subset=FEATURE_COLS)

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
