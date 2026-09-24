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
#
# The trader runs in SIMULATION. Its hours cover the US session in both EDT
# and EST (the VM clock is UTC and does not observe DST); outside the regular
# session slot_trader exits at once, so the extra polls cost nothing.
#
#   ./services.sh --install   add the trader line to the crontab (idempotent)
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
TAG="slot_trader.py --auto"
case "${1:---status}" in
  --install)
    for L in "$LINE" "$LINE_SHADOW" "$LINE_LIVE"; do
      if crontab -l 2>/dev/null | grep -qF "$L"; then echo "already installed: ${L:0:60}..."; else
        (crontab -l 2>/dev/null; echo "$L") | crontab - && echo "installed: $L"; fi
    done ;;
  --remove)
    crontab -l 2>/dev/null | grep -vF "$TAG" | crontab - && echo "removed" ;;
  *)
    crontab -l 2>/dev/null | grep -E "stockbot2000" ;;
esac
