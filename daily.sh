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
run "[1/8] Symbol directory — records listings and delistings" $PY universe.py --record

# 2. Prices. Incremental: tops up from the last stored bar per ticker.
run "[2/8] Price top-up" $PY backfill.py --top-up

# 3. Indicators for whatever bars arrived.
run "[3/8] Features" $PY build_features.py

# 4. Advance every open paper-trading run one day. This is the only measurement
#    in the project with no survivorship bias, and it accrues only in real time.
run "[4/8] Paper trading step" $PY paper_trading.py --step

# 5. The daily book: best candidate from every system, sell signals on open
#    picks, and both recorded so the forward record builds itself.
run "[5/8] Daily book" $PY daily_picks.py --report --record
$PY daily_picks.py --report --record > data/daily_book.txt 2>/dev/null || true

# 6. Where every fund stands. Runs from the database, because cron holds no
#    broker credentials — share counts come from the recorded fills, so the
#    Claude fund's cost basis is exact rather than assumed. Pass --live with a
#    broker snapshot to add the accounts this system does not manage.
# 6. Mark the bull/bear switching funds. Replays each curve from its start
#    date, so a missed day self-heals rather than leaving a hole.
run "[6/8] Pair funds" $PY pair_funds.py --step

run "[7/8] Fund report" $PY fund_report.py --live data/live.json

# 8. Back up what cannot be regenerated. Prices and features are re-fetchable;
#    the forward record is not — a paper fund that has run 14 days cannot be
#    made to have run 14 days by running anything. Last, so a backup failure
#    cannot suppress the morning slate.
run "[8/8] Backup" $PY backup.py

# 6. Tell someone. A report nobody reads is worth the same as no report, and
#    a FAILURE nobody hears about is how this project lost eight days of price
#    data and three hours of a stalled search without noticing.
$PY orders.py --build > data/orders_today.txt 2>/dev/null || true
if [ "$fail" -eq 0 ]; then
    say "Daily capture complete"
    $PY notify.py --slate >/dev/null 2>&1 || true
    # Orders first, then standings: the slate is the actionable message and
    # should not be the second thing read on a phone.
    $PY fund_report.py --live data/live.json --notify >/dev/null 2>&1 || true
else
    say "Daily capture finished WITH FAILURES — see above"
    $PY notify.py --alert "Daily capture FAILED. Check logs/daily.log — the symbol directory step is the one that must not be missed, because a skipped day loses that day's delistings permanently." >/dev/null 2>&1 || true
fi
exit $fail
