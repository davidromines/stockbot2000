"""
Walk-forward validation: retrain repeatedly, always predicting forward.

A single train/test split answers "did this work on 2022-2026?". It cannot answer
"does this work *consistently*", and that is the question that matters — a
strategy whose entire edge came from one favourable year looks identical to a
durable one when you only cut the data once.

This rolls a window through history. Train on `train_years`, predict the next
`test_months`, step forward, repeat. Every prediction is made by a model that saw
only data preceding it, so concatenating them gives a continuous out-of-sample
series spanning nearly the whole period rather than just the tail.

Predictions are written to `oos_predictions`, which lets `backtest.py` simulate
against scores that were genuinely unavailable at the time — the single-model
backtest still uses one model's view of a four-year stretch, which is weaker.

The purge between train and test is inherited from `storage.load_labeled_frame`:
loading each range separately means SQL `LEAD` returns NULL for the last
`horizon_days` of the training range, so no training label can see test prices.

Usage:
    python walk_forward.py --run          # run all folds (resumable)
    python walk_forward.py --report       # per-fold AUC and stability
"""
import runtime  # noqa: F401  — must precede numpy/pandas/xgboost
import argparse
import gc
import logging

import pandas as pd
import xgboost as xgb
from sklearn.metrics import roc_auc_score

import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("walk_forward")


def build_folds(dates: list[str], train_years: int, test_months: int,
                horizon_days: int) -> list[dict]:
    """
    Cut the date list into rolling train/test folds.

    Folds are built from dates alone, before any data is loaded, so each side can
    be queried separately and no fold ever holds the whole history in memory.

    The last `horizon_days` of every training range are dropped. Labels look
    forward, so without that purge a training row near the boundary carries a
    label derived from prices inside its own test window.
    """
    idx = pd.DatetimeIndex(dates)
    folds = []
    start = idx[0]
    while True:
        train_end = start + pd.DateOffset(years=train_years)
        test_end = train_end + pd.DateOffset(months=test_months)
        if test_end > idx[-1]:
            break

        train_dates = [d for d in dates if start <= pd.Timestamp(d) < train_end]
        test_dates = [d for d in dates if train_end <= pd.Timestamp(d) < test_end]
        if len(train_dates) > horizon_days * 3 and test_dates:
            purged = train_dates[:-horizon_days] if horizon_days else train_dates
            if purged:
                folds.append({
                    "train_start": purged[0], "train_end": purged[-1],
                    "test_start": test_dates[0], "test_end": test_dates[-1],
                })
        start = start + pd.DateOffset(months=test_months)
    return folds


def run(config: dict, resume: bool = True) -> None:
    mcfg = config["model"]
    wf = mcfg.get("walk_forward", {})
    horizon = config["labeling"]["horizon_days"]
    threshold = config["labeling"]["up_threshold_pct"]
    types = config["universe"]["tradeable_types"]
    floors = (config["risk"].get("min_price"), config["risk"].get("min_dollar_volume"))
    cap = wf.get("max_train_rows", 2_000_000)

    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)

    dates = storage.feature_dates(conn, types=types,
                                  start_date=config["data"].get("train_start"))
    folds = build_folds(dates, wf.get("train_years", 5),
                        wf.get("test_months", 6), horizon)
    log.info(f"{len(folds)} folds over {dates[0]} -> {dates[-1]}")

    done = storage.completed_folds(conn) if resume else set()
    if done:
        log.info(f"{len(done)} folds already computed; skipping them")

    for i, f in enumerate(folds, start=1):
        key = f"{f['test_start']}:{f['test_end']}"
        if key in done:
            continue

        n = storage.count_labeled_rows(conn, FEATURE_COLS, types=types,
                                       start_date=f["train_start"], end_date=f["train_end"],
                                       min_price=floors[0], min_dollar_volume=floors[1])
        per_mille = max(1, int(1000 * cap / n)) if n > cap else None

        train = storage.load_labeled_frame(
            conn, FEATURE_COLS, horizon, threshold, types=types,
            start_date=f["train_start"], end_date=f["train_end"],
            sample_per_mille=per_mille, min_price=floors[0], min_dollar_volume=floors[1])
        test = storage.load_labeled_frame(
            conn, FEATURE_COLS, horizon, threshold, types=types,
            start_date=f["test_start"], end_date=f["test_end"],
            min_price=floors[0], min_dollar_volume=floors[1])

        if len(train) < 1000 or test.empty or train["label"].nunique() < 2:
            log.warning(f"fold {i}: insufficient data, skipping")
            continue

        model = xgb.XGBClassifier(
            n_estimators=mcfg.get("n_estimators", 200),
            max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            eval_metric="auc", random_state=mcfg["random_state"],
            n_jobs=runtime.MAX_THREADS,
        )
        model.fit(train[FEATURE_COLS], train["label"])
        probs = model.predict_proba(test[FEATURE_COLS])[:, 1]

        auc = roc_auc_score(test["label"], probs) if test["label"].nunique() > 1 else float("nan")
        storage.record_oos_predictions(conn, key, f, test, probs, auc)

        log.info(f"fold {i}/{len(folds)}  train {f['train_start']}..{f['train_end']} "
                 f"({len(train):,})  test {f['test_start']}..{f['test_end']} "
                 f"({len(test):,})  AUC {auc:.3f}")
        del train, test, model
        gc.collect()

    conn.close()


def report(config: dict) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)
    rows = storage.fold_summary(conn)
    if not rows:
        print("No folds computed yet — run --run first.")
        conn.close()
        return

    print(f"{'test window':<26}{'rows':>10}{'AUC':>8}{'top-decile hit':>16}{'base':>8}")
    print("-" * 68)
    for r in rows:
        print(f"{r['test_start']} -> {r['test_end']:<10}{r['n']:>10,}{r['auc']:>8.3f}"
              f"{r['top_hit']:>15.1%}{r['base']:>8.1%}")

    aucs = [r["auc"] for r in rows if r["auc"] == r["auc"]]
    over = storage.overall_oos(conn)
    print("-" * 68)
    print(f"folds: {len(rows)}   AUC mean {sum(aucs)/len(aucs):.3f}  "
          f"min {min(aucs):.3f}  max {max(aucs):.3f}  "
          f"above 0.5: {sum(a > 0.5 for a in aucs)}/{len(aucs)}")
    print(f"pooled out-of-sample: {over['n']:,} rows, AUC {over['auc']:.3f}, "
          f"top-decile hit {over['top_hit']:.1%} vs base {over['base']:.1%}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Run all outstanding folds.")
    parser.add_argument("--rerun", action="store_true", help="Recompute every fold.")
    parser.add_argument("--report", action="store_true", help="Per-fold AUC and stability.")
    args = parser.parse_args()

    config = load_config()
    runtime.be_nice()
    if args.run or args.rerun:
        run(config, resume=not args.rerun)
    if args.report:
        report(config)
    if not (args.run or args.rerun or args.report):
        parser.print_help()


if __name__ == "__main__":
    main()
