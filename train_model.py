"""
Trains an XGBoost binary classifier: given a day's feature snapshot,
predict whether the stock rises >= up_threshold_pct within horizon_days.

Run this occasionally (weekly/monthly) offline as history accumulates.
Not part of the daily scoring pipeline.
"""
import runtime  # noqa: F401  — must precede numpy/pandas/xgboost
import json
import logging

import pandas as pd
import xgboost as xgb
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


def chronological_split(df: pd.DataFrame, test_fraction: float, horizon_days: int):
    """
    Split by date, not at random, and purge the boundary.

    Two separate leaks are being closed here.

    The obvious one: a shuffled split over time-ordered rows puts tomorrow in the
    training set and yesterday in the test set. The model then "predicts" days it
    has already seen.

    The subtle one: labels look forward `horizon_days`. A training row dated D
    carries a label derived from the close at D+horizon. If D sits within
    `horizon` days of the cutoff, that label encodes prices from the test period
    even though the row itself does not. So the last `horizon` trading days
    before the cutoff are dropped entirely — the standard purge. Without it the
    split looks clean and still leaks.
    """
    dates = sorted(df["date"].unique())
    if len(dates) < horizon_days * 3:
        return df.iloc[0:0], df.iloc[0:0], {}

    cutoff = int(len(dates) * (1 - test_fraction))
    train_dates = dates[: max(cutoff - horizon_days, 0)]
    test_dates = dates[cutoff:]
    if not train_dates or not test_dates:
        return df.iloc[0:0], df.iloc[0:0], {}

    train = df[df["date"].isin(train_dates)]
    test = df[df["date"].isin(test_dates)]
    meta = {
        "train_start": str(train_dates[0])[:10],
        "train_end": str(train_dates[-1])[:10],
        "test_start": str(test_dates[0])[:10],
        "test_end": str(test_dates[-1])[:10],
        "purged_days": horizon_days,
        "horizon_days": horizon_days,
        "test_fraction": test_fraction,
    }
    return train, test, meta


def main():
    runtime.be_nice()
    cfg = load_config()
    features = pd.read_parquet(cfg["data"]["features_file"])
    history = pd.read_parquet(cfg["data"]["history_file"])[["ticker", "date", "close"]]

    labeled = build_labels(history, cfg["labeling"]["horizon_days"], cfg["labeling"]["up_threshold_pct"])
    merged = features.merge(labeled[["ticker", "date", "label"]], on=["ticker", "date"], how="inner")
    merged = merged.dropna(subset=FEATURE_COLS + ["label"])

    if merged.empty:
        log.error("No labeled rows after merge — need more history before training.")
        return

    train, test, split = chronological_split(
        merged,
        test_fraction=cfg["model"].get("test_fraction", 0.2),
        horizon_days=cfg["labeling"]["horizon_days"],
    )
    if train.empty or test.empty:
        log.error("Not enough history to build a purged chronological split.")
        return

    X_train, y_train = train[FEATURE_COLS], train["label"]
    X_test, y_test = test[FEATURE_COLS], test["label"]

    log.info(f"Train {len(X_train):,} rows  {split['train_start']} -> {split['train_end']}  "
             f"(positive {y_train.mean():.2%})")
    log.info(f"Test  {len(X_test):,} rows  {split['test_start']} -> {split['test_end']}  "
             f"(positive {y_test.mean():.2%})")
    log.info(f"Purged {split['purged_days']} trading days between them "
             f"(label horizon = {split['horizon_days']})")

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="auc",
        random_state=cfg["model"]["random_state"],
        n_jobs=runtime.MAX_THREADS,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    probs = model.predict_proba(X_test)[:, 1]
    log.info("\n" + classification_report(y_test, preds))
    log.info(f"Test AUC: {roc_auc_score(y_test, probs):.3f}")

    model.save_model(cfg["model"]["path"])
    log.info(f"Model saved to {cfg['model']['path']}")

    # backtest.py reads this to restrict itself to out-of-sample dates. Without
    # it a backtest silently replays the training period and reports fiction.
    split_path = cfg["model"].get("split_metadata_path", "models/split.json")
    split["n_train"], split["n_test"] = int(len(X_train)), int(len(X_test))
    with open(split_path, "w") as f:
        json.dump(split, f, indent=2)
    log.info(f"Split metadata saved to {split_path}")


if __name__ == "__main__":
    main()
