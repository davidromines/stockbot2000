#!/usr/bin/env bash
# Continuous strategy search. Runs until stopped: touch data/STOP_LAB to halt.
#
# WHY THIS RUNS SEQUENTIALLY, NOT IN PARALLEL
# -------------------------------------------
# The VM has 4 vCPU and runtime.py holds compute to 3 threads. One search with 3
# workers saturates the box; two searches with 1-2 workers each finish slower in
# total and double the peak memory, because each holds its own ~1.3 GB panel plus
# an unfiltered exit-price frame. Back-to-back runs give the same throughput with
# none of the thrashing, and each iteration varies the seed so the population and
# the constants explored differ every time.
#
# THE STATISTICAL COST, STATED ONCE
# ---------------------------------
# Every additional run raises the number of strategies tested, and the best of N
# looks better than the truth by an amount that grows with N. That is exactly
# what the deflated Sharpe correction in promote.py exists to undo, and it is
# only valid if it knows the real total - so this loop writes a cumulative trial
# count that survives across runs. A strategy found on run 40 must clear a much
# higher bar than the same strategy found on run 1. That is not pessimism, it is
# the arithmetic of multiple testing.

set -uo pipefail
cd "$(dirname "$0")"
PY=./venv/bin/python
mkdir -p logs data
SUMMARY=data/lab_loop_summary.log

i=0
while true; do
    if [ -f data/STOP_LAB ]; then
        echo "=== $(date '+%F %T') : STOP_LAB present, halting ==="
        break
    fi
    i=$((i+1))
    SEED=$(( (RANDOM << 15 | RANDOM) % 900000 + 1000 ))
    STAMP=$(date '+%F %T')
    echo "=== $STAMP : iteration $i, seed $SEED ==="

    # Hold off while the daily capture runs; both want the CPU and the daily job
    # is the one that must not be missed - it is the only record of delistings.
    while pgrep -f "[d]aily.sh" >/dev/null; do sleep 120; done

    if ! $PY evolve.py --seeds --generations 50 --population 300 --seed "$SEED" \
            >> logs/lab_loop_evolve.log 2>&1; then
        echo "  evolve failed, continuing"; sleep 60; continue
    fi

    RID=$($PY -c "
import runtime,storage
from universe import load_config
c=storage.connect(load_config()['database']['market_data_path'])
print(c.execute('SELECT run_id FROM lab_runs ORDER BY started_at DESC LIMIT 1').fetchone()[0])" 2>/dev/null)
    [ -z "$RID" ] && { echo "  no run id"; continue; }

    $PY promote.py --shortlist "$RID" >> logs/lab_loop_ladder.log 2>&1
    $PY promote.py --validate  "$RID" >> logs/lab_loop_ladder.log 2>&1

    # One line per iteration: what it found, and the cumulative trial count that
    # any deflated-Sharpe claim has to be measured against.
    $PY - "$RID" "$i" "$SEED" >> "$SUMMARY" 2>/dev/null <<'PYEOF'
import runtime, sys, storage
from universe import load_config
rid, it, seed = sys.argv[1], sys.argv[2], sys.argv[3]
c = storage.connect(load_config()["database"]["market_data_path"])
ev = c.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
sur = c.execute("""SELECT COUNT(*) FROM promotions p JOIN strategies s ON s.id=p.strategy_id
    WHERE p.stage='validation' AND p.decision='pass' AND s.run_id=?""", (rid,)).fetchone()[0]
short = c.execute("""SELECT COUNT(*) FROM promotions p JOIN strategies s ON s.id=p.strategy_id
    WHERE p.stage='shortlist' AND p.decision='pass' AND s.run_id=?""", (rid,)).fetchone()[0]
best = c.execute("""SELECT MAX(e.excess_pnl_usd) FROM evaluations e
    JOIN strategies s ON s.id=e.strategy_id WHERE s.run_id=?""", (rid,)).fetchone()[0] or 0
import datetime as dt
print(f"{dt.datetime.now():%F %T}  iter {it:>4}  seed {seed:>7}  run {rid[:8]}  "
      f"shortlist {short:>4}  survivors {sur:>3}  best excess ${best:>9,.0f}  "
      f"CUMULATIVE TRIALS {ev:,}", flush=True)
PYEOF
    tail -1 "$SUMMARY"
    sleep 30
done
