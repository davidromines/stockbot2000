#!/usr/bin/env bash
# ship.sh TASK-nnn — review -> approve -> commit task state -> merge, gate at each step.
set -uo pipefail
cd /home/stockpicker/stockbot2000
T=$1; mkdir -p logs; L=logs/ado_ship_$T.log
run() { MEM_MAX=5G ./run_bounded.sh ./venv/bin/python orchestrator.py "$@" >> "$L" 2>&1; }
: > "$L"
run review "$T" || { echo "review failed"; exit 1; }
grep -q "gate: PASS" "$L" || { echo "GATE FAILED"; grep -E "FAIL " "$L" | head; exit 1; }
run approve "$T" || { echo "approve failed"; tail -3 "$L"; exit 1; }
git add tasks/ && git commit -q -m "$T: move to COMPLETE

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
run merge "$T" || { echo "merge failed"; tail -5 "$L"; exit 1; }
echo "$T shipped: $(git log --oneline -1)"; grep -E "ALL PASS|FAIL" "$L" | tail -1
