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
# Every stage is timed and recorded against its compute-priority tier, so the
# question "are we spending the majority of compute on search while the data
# problem is unresolved" has an answer rather than an opinion. Phase 6 s28.
run() {
    local label="$1"; shift
    say "$label"
    # Find the script being run rather than assuming its position. Taking
    # argument 2 blindly recorded an EMPTY stage name for anything invoked as
    # `python -c`, and a compute log full of blanks answers no question.
    local stage="unknown"
    local a
    for a in "$@"; do
        case "$a" in
            *.py|*.sh) stage="$(basename "$a")"; break ;;
        esac
    done
    local t0=$SECONDS
    local ok=1
    if ! "$@"; then
        say "FAILED: $label (continuing — later stages are independent)"
        fail=1
        ok=0
    fi
    local elapsed=$(( SECONDS - t0 ))
    # Best-effort: accounting must never be the reason a capture fails.
    $PY compute_priority.py --record "$stage" "$elapsed" >/dev/null 2>&1 || true
}

say "Daily capture starting"

# 1. Point-in-time universe. THE survivorship-critical step: this is what stamps
#    a ticker inactive on the day it leaves the listing directory.
run "[1/10] Symbol directory — records listings and delistings" $PY universe.py --record

# 2. Prices. Incremental: tops up from the last stored bar per ticker.
run "[2/10] Price top-up" $PY backfill.py --top-up

# 3. Indicators for whatever bars arrived.
run "[3/10] Features" $PY build_features.py

# 4. Freshness is a gate, not a log line. The old pipeline reported SUCCESS
#    while a full session behind because its check compared the table to
#    itself. A stale run must fail here rather than produce scores nobody
#    knows are stale.
# Fundamentals are derived from filings, not from bars, so they were never
# part of the price top-up — and nothing else rebuilt them. They stopped on
# 2026-09-11 and sat eleven days stale while the pipeline reported success
# every morning, stalling both conviction paper funds and feeding every
# conviction screen in the daily book stale data. A 90-day window is enough
# to pick up newly filed reports and to repair a gap of a week or two;
# INSERT OR REPLACE makes re-running it a no-op on days with nothing new.
run "[3b/10] Fundamental projection" $PY fundamental_features.py --build \
    --start "$(date -u -d '90 days ago' +%F)"

run "[4/10] Freshness gate" $PY freshness.py

# 4. Advance every open paper-trading run one day. This is the only measurement
#    in the project with no survivorship bias, and it accrues only in real time.
run "[5/10] Paper trading step" $PY paper_trading.py --step

# 5. The daily book: best candidate from every system, sell signals on open
#    picks, and both recorded so the forward record builds itself.
run "[6/10] Daily book" $PY daily_picks.py --report --record
$PY daily_picks.py --report --record > data/daily_book.txt 2>/dev/null || true

# 6. Where every fund stands. Runs from the database, because cron holds no
#    broker credentials — share counts come from the recorded fills, so the
#    Claude fund's cost basis is exact rather than assumed. Pass --live with a
#    broker snapshot to add the accounts this system does not manage.
# 6. Mark the bull/bear switching funds. Replays each curve from its start
#    date, so a missed day self-heals rather than leaving a hole.
run "[7/10] Pair funds" $PY pair_funds.py --step

run "[8/10] Fund report" $PY fund_report.py --live data/live.json

# 8. Back up what cannot be regenerated. Prices and features are re-fetchable;
#    the forward record is not — a paper fund that has run 14 days cannot be
#    made to have run 14 days by running anything. Last, so a backup failure
#    cannot suppress the morning slate.
# 9. Regenerate the integrity report from the live database. Its job is to be
#    harder on the project than the project would be on itself, and a report
#    that is regenerated daily cannot quietly drift from what the system
#    actually contains.
# The league. Migration is idempotent and re-registers nothing, so running it
# daily is how a newly opened fund joins without anyone remembering to add it.
# All three are best-effort: a scoreboard that did not update tonight costs
# nothing, and blocking the price capture over it would lose that day's
# delistings permanently.
$PY migrate_league.py --run >/dev/null 2>&1 || true
$PY scoreboard.py --snapshot >/dev/null 2>&1 || true
$PY degradation.py --record >/dev/null 2>&1 || true

run "[9/10] Research integrity" $PY research_integrity.py
$PY multiple_testing.py --snapshot --note "daily" >/dev/null 2>&1 || true

# A small nightly increment to the random-strategy control. Deliberately not a
# big one-off run: the table is append-only and a distribution built from 25 a
# night over months is a better calibration than one built from 300 once. Never
# fatal — a calibration that failed to grow tonight costs nothing, and blocking
# the price capture over it would cost a day of delistings permanently.
$PY random_control.py --run 25 >/dev/null 2>&1 || true

# --- the research loop (Phase 11 item 35) -------------------------------
# Each of these reports; none of them acts. stop_conditions can say DO NOT
# SEARCH, which is a legitimate output and is why it runs before anything
# that would search.
$PY stop_conditions.py > data/stop_conditions.txt 2>/dev/null || true
$PY roster.py --plan > data/roster_plan.txt 2>/dev/null || true
$PY live_pipeline.py --build > /dev/null 2>&1 || true
$PY compute_priority.py > data/compute_spend.txt 2>/dev/null || true

run "[10/10] Backup" $PY backup.py

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
