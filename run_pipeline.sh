#!/usr/bin/env bash
# Daily pipeline: pull data -> compute features -> score -> LLM interpretation.
# Model training (train_model.py) is intentionally NOT run here — retrain
# separately on a slower cadence (weekly/monthly) as history accumulates.
#
# Suggested cron (7:00am local, before market open):
#   0 7 * * 1-5 /home/stockpicker/stockbot2000/run_pipeline.sh >> logs/pipeline.log 2>&1

set -euo pipefail
cd "$(dirname "$0")"

source venv/bin/activate 2>/dev/null || echo "No venv found, using system python."

echo "=== $(date) : Starting pipeline ==="

echo "[1/5] Pulling market data..."
python data_pull.py

echo "[2/5] Computing features..."
python features.py

echo "[3/5] Scoring with XGBoost..."
python score.py

echo "[4/5] Generating LLM scoresheet..."
python llm_report.py

echo "[5/5] Checking open positions against stop-loss levels..."
python check_exits.py

echo "=== $(date) : Pipeline complete. Scoresheet at data/scoresheet.json ==="
