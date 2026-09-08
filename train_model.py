"""
Trains an XGBoost binary classifier: given a day's feature snapshot,
predict whether the stock rises >= up_threshold_pct within horizon_days.

Run this occasionally (weekly/monthly) offline as history accumulates.
Not part of the daily scoring pipeline.
"""
import logging

import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score

from universe import load_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("train_model")

FEATURE_COLS = [
    "sma_50", "sma_200", "rsi_14", "roc_10", "adx_14",
    "macd", "macd_signal", "macd_hist",
    "bb_pct", "vol_ratio",
    "price_above_sma50", "price_above_sma200", "golden_cross",
    "atr_14", "stoch_k", "stoch_d", "obv_rising", "cci_20", "willr_14", "chaikin_osc",
]


def build_labels(history: pd.DataFrame, horizon_days: int, up_threshold_pct: float) -> pd.DataFrame:
    history = history.sort_values(["ticker", "date"]).reset_index(drop=True)
    history["future_close"] = history.groupby("ticker")["close"].shift(-horizon_days)
    history["forward_return_pct"] = (history["future_close"] / history["close"] - 1) * 100
    history["label"] = (history["forward_return_pct"] >= up_threshold_pct).astype(int)
    return history.dropna(subset=["label"])


def main():
    cfg = load_config()
    features = pd.read_parquet(cfg["data"]["features_file"])
    history = pd.read_parquet(cfg["data"]["history_file"])[["ticker", "date", "close"]]

    labeled = build_labels(history, cfg["labeling"]["horizon_days"], cfg["labeling"]["up_threshold_pct"])
    merged = features.merge(labeled[["ticker", "date", "label"]], on=["ticker", "date"], how="inner")
    merged = merged.dropna(subset=FEATURE_COLS + ["label"])

    if merged.empty:
        log.error("No labeled rows after merge — need more history before training.")
        return

    X = merged[FEATURE_COLS]
    y = merged["label"]
    log.info(f"Training on {len(X)} rows. Positive rate: {y.mean():.2%}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=cfg["model"]["train_test_split"],
        random_state=cfg["model"]["random_state"], stratify=y,
    )

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="auc",
        random_state=cfg["model"]["random_state"],
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]
    log.info("\n" + classification_report(y_test, preds))
    log.info(f"Test AUC: {roc_auc_score(y_test, probs):.3f}")

    model.save_model(cfg["model"]["path"])
    log.info(f"Model saved to {cfg['model']['path']}")


if __name__ == "__main__":
    main()
