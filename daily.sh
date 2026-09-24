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

# Market cap for liquid names the filings miss (GEN, NWSA were refused as
# "unknown" on the first LIVE session). Sourced and dated, never assumed; a
# name still unknown after this is still rejected by the risk engine.
run "[3c/10] Market-cap fallback" $PY market_caps.py --backfill

# Rates series for the Phase 6 §21 rate regimes (FRED, ^IRX fallback).
run "[3d/10] Rates series" $PY regimes.py --load-rates

# Crypto tops up into its own table and refreshes listing status, so a pair
# that delists leaves a dated final observation rather than just stopping.
# Best-effort: a crypto outage must not fail the equity capture.
$PY crypto_data.py --load --interval 1h --max-bars 600 >/dev/null 2>&1 || true
$PY crypto_data.py --status >/dev/null 2>&1 || true
# The crypto paper fund steps and marks after its data tops up, then the slate
# is built from the fund's fresh state (Phase 12 items 40 and 42). Stepping
# first matters: the slate's kill switch treats a fund not stepped today as an
# unreconciled book and halts.
$PY crypto_fund.py --step --mark >/dev/null 2>&1 || true
$PY crypto_orders.py --build >/dev/null 2>&1 || true

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
# roster.py / live_pipeline.py (the Phase 10 promotion path) were retired
# 2026-09-24 by the owner: ranking.py + slots.py are the one promotion system.
$PY compute_priority.py > data/compute_spend.txt 2>/dev/null || true
# The Value Fund (Phase 9 item 30). Marked every morning so its forward record
# accrues; reviewed only when a quarterly review is due — --if-due is what
# stops a long-horizon fund from rebalancing daily.
$PY value_fund.py --review --if-due --apply --mark >/dev/null 2>&1 || true

# Authoritative P&L (Phase 13 H2). Runs after every fund has stepped. Exit 1
# means an ACCOUNTING_PROBLEM: a difference with no identified cause.
run "[9b/10] Accounting" $PY accounting.py --restate --snapshot data/accounting.json

# --- the Strategy Factory (Phase 13 H3-H14) ------------------------------
# Templates, not search: the frozen evolutionary search is untouched (B16).
# Backtests admit a strategy to PAPER; only forward evidence qualifies it.
#
# The pipeline stage peaks ~4.3 GB and ran 20 min at budget 12 (2026-09-24).
# From a Claude session it must run in its own memory-capped scope, or an OOM
# takes the desktop with it. Under cron there is no user bus for systemd-run
# (Linger=no) — and a cron job is not in the desktop's scope — so it runs
# plain there rather than failing.
bounded() {
    if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -S "/run/user/$(id -u)/bus" ]; then
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
    fi
    if [ -S "${XDG_RUNTIME_DIR:-/nonexistent}/bus" ]; then
        ./run_bounded.sh "$@"
    else
        "$@"
    fi
}
run "[9c/10] Research library sync" $PY library_bridge.py --sync
run "[9d/10] Factory templates" $PY strategy_factory.py --generate
run "[9e/10] Discovery plan" $PY discovery.py --plan
run "[9f/10] Factory pipeline" bounded $PY factory_pipeline.py --run --budget 12
# Owner, 2026-09-24: backtests include the synthetic dead companies. Every
# ranked strategy is re-run with them (as_is) and with every death a total loss
# (zero); ranking.py scores on as_is. Resumable: only new strategies or a new
# synthetic build are computed.
run "[9f2/10] Survivorship backtests" bounded $PY survivorship_backtest.py --run
run "[9g/10] League standings" $PY leagues.py --standings --record
run "[9h/10] Factory report" $PY factory_report.py
# Addendum A §26 / I10: the formal five-slot reassessment, once per trading
# day, after every strategy's evidence is updated. SIMULATION: it records
# assignments and releases; the intraday trader (services.sh) acts on them.
run "[9i/10] Slot reassessment" $PY slots.py --apply --mode SIMULATION --leaderboard
# The pre-LIVE acceptance checklist, daily. Informational: it exits 1 until
# every item passes (including a SHADOW track record), which is not a failure
# of the capture, so it is not run through run().
$PY acceptance.py --no-suite > data/acceptance.txt 2>&1 || true

$PY build_dashboard.py >/dev/null 2>&1 || true

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
