#!/usr/bin/env bash
# Daily capture. The job that makes the database point-in-time from today forward.
#
# The survivorship problem is unfixable *backwards* — we hold 5 companies that
# stopped trading during 2006-2019 against 9,029 the Internet Archive says
# existed. It is entirely fixable *forwards*, and only by running this every day:
# step 1 records which tickers are still listed, so a company that disappears is
# stamped inactive on the day it disappears rather than silently vanishing from
# history. Miss a week and that week's delistings are lost permanently.
#
# Install (07:00 on weekdays, after the previous close is final):
#   crontab -e
#   0 7 * * 1-5 /home/stockpicker/stockbot2000/daily.sh >> /home/stockpicker/stockbot2000/logs/daily.log 2>&1
#
# Idempotent: every stage may be re-run on the same day without duplicating or
# corrupting anything, so a missed day is caught up by simply running it again.

set -uo pipefail
cd "$(dirname "$0")"
mkdir -p logs
PY="./venv/bin/python"

say() { echo "=== $(date '+%Y-%m-%d %H:%M:%S') : $*"; }
fail=0

# A failing stage must not abort the ones after it. Losing today's delisting
# record because Yahoo rate-limited the price pull would be the worst possible
# trade, and these stages are independent.
run() {
    local label="$1"; shift
    say "$label"
    if ! "$@"; then
        say "FAILED: $label (continuing — later stages are independent)"
        fail=1
    fi
}

say "Daily capture starting"

# 1. Point-in-time universe. THE survivorship-critical step: this is what stamps
#    a ticker inactive on the day it leaves the listing directory.
run "[1/4] Symbol directory — records listings and delistings" $PY universe.py --record

# 2. Prices. Incremental: tops up from the last stored bar per ticker.
run "[2/4] Price top-up" $PY backfill.py --top-up

# 3. Indicators for whatever bars arrived.
run "[3/4] Features" $PY build_features.py

# 4. Advance every open paper-trading run one day. This is the only measurement
#    in the project with no survivorship bias, and it accrues only in real time.
run "[4/4] Paper trading step" $PY paper_trading.py --step

if [ "$fail" -eq 0 ]; then
    say "Daily capture complete"
else
    say "Daily capture finished WITH FAILURES — see above"
fi
exit $fail
