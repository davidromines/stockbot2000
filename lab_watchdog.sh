#!/usr/bin/env bash
# Keeps the continuous strategy search alive. Runs from cron every 15 minutes.
#
# WHY THIS EXISTS
# ---------------
# lab_loop.sh runs forever by design, and on 2026-09-15 it stopped anyway: it had
# been launched by hand from an interactive shell, and when that shell went away
# so did the loop. Nobody noticed for two days. A loop that only runs while
# someone is watching is not a continuous search, it is a manual one with extra
# steps.
#
# The watchdog is deliberately dumber than the thing it guards. It checks one
# fact — is the loop running — and starts it if not. It does not parse logs,
# does not decide whether the loop is "healthy", and does not restart anything
# that is already up. Watchdogs that reason about health are how you get two
# copies of a search writing to the same database.
#
# STOP_LAB is honoured here too. `touch data/STOP_LAB` halts the loop AND stops
# the watchdog from restarting it, so there is one switch, not two.

set -uo pipefail
cd "$(dirname "$0")"
PY=./venv/bin/python

if [ -f data/STOP_LAB ]; then
    exit 0
fi

# Liveness by PID FILE, never by process name. `pgrep -f lab_loop` matches any
# command line that mentions this file — including this watchdog's own — so a
# name check reports the loop alive when nothing runs, and it is never
# restarted. That failure was real: the first version of this script did exactly
# that and silently did nothing.
#
# The pid is also confirmed to BE the loop, so a recycled pid belonging to some
# unrelated process cannot masquerade as a healthy search.
running=0
if [ -f data/lab_loop.pid ]; then
    pid=$(cat data/lab_loop.pid 2>/dev/null || echo "")
    if [ -n "$pid" ] && [ -d "/proc/$pid" ] \
       && tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "lab_loop.sh"; then
        running=1
    fi
fi
if [ "$running" -eq 1 ]; then
    exit 0
fi

STAMP=$(date -u '+%F %T')
echo "=== $STAMP UTC : lab loop not running, starting it ===" >> logs/lab_watchdog.log

# setsid so it survives this cron job exiting, and </dev/null so it never
# inherits a terminal it can lose.
setsid nohup bash ./lab_loop.sh >> logs/lab_loop.log 2>&1 < /dev/null &
sleep 5

if [ -f data/lab_loop.pid ] && [ -d "/proc/$(cat data/lab_loop.pid)" ]; then
    echo "  started ok, pid $(cat data/lab_loop.pid)" >> logs/lab_watchdog.log
else
    echo "  FAILED TO START" >> logs/lab_watchdog.log
    $PY notify.py --alert "Strategy search is DOWN and the watchdog could not restart it. Check logs/lab_loop.log." >/dev/null 2>&1 || true
fi
