"""
Trains an XGBoost binary classifier: given a day's feature snapshot,
predict whether the stock rises >= up_threshold_pct within horizon_days.

Run this occasionally (weekly/monthly) offline as history accumulates.
Not part of the daily scoring pipeline.
"""
import runtime  # noqa: F401  — must precede numpy/pandas/xgboost
import json
import gc
import logging

import pandas as pd
import xgboost as xgb

import storage
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


def plan_split(dates: list[str], test_fraction: float, horizon_days: int) -> dict | None:
    """
    Choose the train/test boundary from the date list alone, before loading rows.

    Splitting on dates rather than after loading is what keeps this within memory:
    each side is then queried separately and the combined frame never exists. The
    previous version loaded everything, sorted it and grouped it in pandas, which
    peaked at 10.4 GB on 15M rows and was killed by the OOM reaper.

    The last `horizon_days` dates before the cutoff are excluded from training.
    Labels look forward, so a row dated within the horizon of the boundary carries
    a label derived from test-period prices even though the row itself does not.
    SQL `LEAD` would drop those rows anyway, but doing it explicitly here makes the
    purge visible and intentional rather than a side effect.
    """
    if len(dates) < horizon_days * 3:
        return None
    cutoff = int(len(dates) * (1 - test_fraction))
    train_dates = dates[: max(cutoff - horizon_days, 0)]
    test_dates = dates[cutoff:]
    if not train_dates or not test_dates:
        return None
    return {
        "train_start": str(train_dates[0])[:10],
        "train_end": str(train_dates[-1])[:10],
        "test_start": str(test_dates[0])[:10],
        "test_end": str(test_dates[-1])[:10],
        "purged_days": horizon_days,
        "horizon_days": horizon_days,
        "test_fraction": test_fraction,
    }


def main():
    runtime.be_nice()
    cfg = load_config()
    horizon = cfg["labeling"]["horizon_days"]
    threshold = cfg["labeling"]["up_threshold_pct"]
    types = cfg["universe"]["tradeable_types"]
    start = cfg["data"].get("train_start")

    conn = storage.connect(cfg["database"]["market_data_path"])

    dates = storage.feature_dates(conn, types=types, start_date=start)
    split = plan_split(dates, cfg["model"].get("test_fraction", 0.2), horizon)
    if not split:
        log.error("Not enough history to build a purged chronological split.")
        return
    log.info(f"{len(dates):,} trading days available from {dates[0]}")
    log.info(f"Split: train {split['train_start']} -> {split['train_end']} | "
             f"test {split['test_start']} -> {split['test_end']} | "
             f"purge {horizon}d")

    avail = storage.available_memory_gb()
    log.info(f"{avail:.1f} GB memory available")

    cap = cfg["model"].get("max_train_rows")

    def load(a, b, what, apply_cap=False):
        n = storage.count_labeled_rows(conn, FEATURE_COLS, types=types,
                                       start_date=a, end_date=b)
        per_mille = None
        if apply_cap and cap and n > cap:
            per_mille = max(1, int(1000 * cap / n))
            log.info(f"  {what}: {n:,} rows exceeds max_train_rows={cap:,}; "
                     f"sampling {per_mille/10:.1f}% in SQL")
        df = storage.load_labeled_frame(conn, FEATURE_COLS, horizon, threshold,
                                        types=types, start_date=a, end_date=b,
                                        sample_per_mille=per_mille)
        log.info(f"  {what}: {len(df):,} rows, {storage.frame_memory_gb(df):.2f} GB, "
                 f"positive {df['label'].mean():.2%}")
        return df

    test = load(split["test_start"], split["test_end"], "test ")
    train = load(split["train_start"], split["train_end"], "train", apply_cap=True)
    conn.close()

    if train.empty or test.empty:
        log.error("Empty train or test set — check the database.")
        return

    X_test, y_test = test[FEATURE_COLS], test["label"]
    X_train, y_train = train[FEATURE_COLS], train["label"]
    del test, train
    gc.collect()

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

    split_path = cfg["model"].get("split_metadata_path", "models/split.json")
    split["n_train"], split["n_test"] = int(len(X_train)), int(len(X_test))
    with open(split_path, "w") as f:
        json.dump(split, f, indent=2)
    log.info(f"Split metadata saved to {split_path}")

if __name__ == "__main__":
    main()
