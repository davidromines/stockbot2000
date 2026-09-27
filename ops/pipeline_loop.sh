#!/usr/bin/env bash
cd ~/stockbot2000
for i in $(seq 1 8); do
  # never overlap the 07:00 UTC daily job: stop starting rounds after 06:00 UTC Monday
  if [ "$(date -u +%u)" = "1" ] && [ "$(date -u +%H)" -ge 6 ]; then echo "=== stop: daily job window"; break; fi
  n=$(./venv/bin/python -c "
import sqlite3;c=sqlite3.connect('file:data/market_data.db?mode=ro',uri=True,timeout=60)
print(c.execute('''SELECT count(*) FROM league_state s JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state GROUP BY strategy_key, version) m ON m.mid=s.id WHERE s.to_state='DISCOVERED' ''').fetchone()[0])")
  echo "=== $(date -u) round $i: $n discovered"
  [ "$n" -eq 0 ] && break
  ./run_bounded.sh ./venv/bin/python factory_pipeline.py --run --budget 100 2>&1 | grep -E " -> |processed|Traceback|Error" 
done
echo "=== $(date -u) loop done"
