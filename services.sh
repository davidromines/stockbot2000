#!/usr/bin/env bash
# Always-on services (Addendum A §19, §27; build step I11).
#
# Research and trading are separate processes on separate schedules, so a slow
# backtest never delays a stop and trading never waits for research (B9):
#
#   07:00 UTC weekdays   daily.sh      data, features, paper funds, accounting,
#                                      the Strategy Factory, slot reassessment
#   every 5 min, 13:00-20:59 UTC weekdays
#                        slot_trader.py --auto  entry pass once per session,
#                                      then the stop monitor; intraday SHADOW scan
#   every 15 min         lab_watchdog.sh (existing)
#   every minute         the Control Center (monitor.py --serve, port 8787,
#                                      localhost only): started if not running,
#                                      so it survives reboots and crashes
#
# The trader runs in SIMULATION. Its hours cover the US session in both EDT
# and EST (the VM clock is UTC and does not observe DST); outside the regular
# session slot_trader exits at once, so the extra polls cost nothing.
#
#   ./services.sh --install   add the trader and Control Center lines to the crontab (idempotent)
#   ./services.sh --status    show the project's cron lines
#   ./services.sh --remove    remove the trader line
set -uo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"
LINE="*/5 13-20 * * 1-5 cd $DIR && ./venv/bin/python slot_trader.py --auto --mode SIMULATION >> $DIR/logs/slot_trader.log 2>&1"
# SHADOW beside it: the same decisions and risk checks, nothing placed. Its
# record is acceptance.py item 26 — LIVE should not be armed without it.
LINE_SHADOW="2-59/5 13-20 * * 1-5 cd $DIR && ./venv/bin/python slot_trader.py --auto --mode SHADOW >> $DIR/logs/slot_trader_shadow.log 2>&1"
# LIVE: the real Robinhood Agentic account. Harmless until armed — it refuses
# unless config/risk.yaml says execution_mode: LIVE and names the account, and
# it halts (and alerts) if the Robinhood sign-in has expired.
LINE_LIVE="4-59/5 13-20 * * 1-5 cd $DIR && ./venv/bin/python slot_trader.py --auto --mode LIVE >> $DIR/logs/slot_trader_live.log 2>&1"
# Control Center (Addendum D, N1). flock makes the per-minute line a no-op while
# the server runs; if it dies, the next minute restarts it. Read-only page.
LINE_CC="* * * * * cd $DIR && flock -n /tmp/stockbot2000_control_center.lock ./venv/bin/python monitor.py --serve --port 8787 >> $DIR/logs/control_center.log 2>&1"
# Stage K1: Robinhood crypto bid/ask every hour, every day (read-only quotes),
# so backtests charge the measured spread rather than one snapshot.
LINE_SPREAD="17 * * * * cd $DIR && ./venv/bin/python crypto_costs.py --log >> $DIR/logs/crypto_spreads.log 2>&1"
# Stage K6: crypto slots, every hour, every day (crypto trades 24/7; the stop
# also rests at the broker). Exits at once unless allow_crypto is true or a
# crypto slot position is open.
LINE_CRYPTO="41 * * * * cd $DIR && ./venv/bin/python crypto_slot_trader.py --auto --mode LIVE >> $DIR/logs/crypto_slot_trader.log 2>&1"
# Addendum D §16 (N10): the end-of-day report to the owner's alert channels, after the close.
# 2026-10-21 (owner "ok go" on the image report): the text report still runs and writes its file and log; the phone
# gets the one-page image instead (daily_snapshot.py, evidence lines in its caption).
LINE_EOD="10 21 * * 1-5 cd $DIR && ./venv/bin/python eod_report.py --mode LIVE >> $DIR/logs/eod_report.log 2>&1"
LINE_SNAPSHOT="12 21 * * 1-5 cd $DIR && ./venv/bin/python daily_snapshot.py --mode LIVE --send >> $DIR/logs/daily_snapshot.log 2>&1"
# Owner-only Telegram commands (telegram_bot.py): a 55 s long-poll pass every minute,
# flock so only one runs. Read-only status plus a confirmed /kill and /resume.
LINE_TG="* * * * * cd $DIR && flock -n /tmp/stockbot2000_telegram.lock ./venv/bin/python telegram_bot.py --poll --seconds 55 >> $DIR/logs/telegram_bot.log 2>&1"
# The strategy backlog (Knowledge Factory reproductions, templates, recycles) tested overnight:
# the daily job's budget of 12 would take months to clear ~900 queued ideas. 22:30 UTC every
# night, hard-stopped after 7 hours (before the 07:00 daily job), one at a time (flock), and
# skipped when another pipeline run is already going (two would need ~9 GB).
# Weekly research digest to Telegram (digest.py): Sundays 17:00 UTC = 10 AM Pacific.
LINE_DIGEST="0 17 * * 0 cd $DIR && ./venv/bin/python digest.py --send >> $DIR/logs/digest.log 2>&1"
LINE_NIGHT="30 22 * * * cd $DIR && ! pgrep -f '[f]actory_pipeline.py --run' >/dev/null && flock -n /tmp/stockbot2000_night.lock timeout 7h ./venv/bin/python factory_pipeline.py --run --budget 70 >> $DIR/logs/factory_night.log 2>&1"
# Addendum G: the Intraday Momentum Runner service (intraday_runner.py). Started at 13:20 and 14:20 UTC on weekdays so it
# covers the New York session in both EDT and EST; flock keeps one instance, and the process ends itself at 16:05 New York
# time. It does nothing unless config.yaml intraday.stage is SHADOW or LIVE (LIVE also needs risk.yaml allow_intraday: true).
LINE_INTRADAY="20 13,14 * * 1-5 cd $DIR && flock -n /tmp/stockbot2000_intraday.lock ./venv/bin/python intraday_runner.py --serve >> $DIR/logs/intraday_runner.log 2>&1"
TAG="slot_trader.py --auto"
TAG_CC="monitor.py --serve"
case "${1:---status}" in
  --install)
    for L in "$LINE" "$LINE_SHADOW" "$LINE_LIVE" "$LINE_CC" "$LINE_SPREAD" "$LINE_CRYPTO" "$LINE_EOD" "$LINE_SNAPSHOT" "$LINE_TG" "$LINE_NIGHT" "$LINE_DIGEST" "$LINE_INTRADAY"; do
      if crontab -l 2>/dev/null | grep -qF "$L"; then echo "already installed: ${L:0:60}..."; else
        (crontab -l 2>/dev/null; echo "$L") | crontab - && echo "installed: $L"; fi
    done ;;
  --remove)
    crontab -l 2>/dev/null | grep -vF "$TAG" | grep -vF "$TAG_CC" | crontab - && echo "removed" ;;
  *)
    crontab -l 2>/dev/null | grep -E "stockbot2000" ;;
esac
