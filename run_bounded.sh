#!/usr/bin/env bash
# Run a batch job in its own systemd scope, under a memory ceiling.
#
#   ./run_bounded.sh ./venv/bin/python stop_sweep.py --run
#   MEM_MAX=3G ./run_bounded.sh ./venv/bin/python signal_decay.py
#
# WHY. A job started from a Claude session — even under setsid/nohup — stays in
# the Claude desktop app's systemd scope. When the kernel OOM-kills it, systemd
# marks that scope failed and stops everything in it, the desktop included. On
# 2026-09-23 that happened three times, each from one ~9.5 GB Python job.
#
# In its own scope with MemoryMax, an oversized job is killed alone and the
# desktop, the browser and the daily pipeline never notice. Exit code 137 from
# here means the ceiling was hit — the job needs to load less, not more memory.
set -uo pipefail
cd "$(dirname "$0")"

if [ $# -eq 0 ]; then
    echo "usage: $0 COMMAND [ARGS...]" >&2; exit 2
fi

gb=$(awk '/^compute:/{c=1;next} c&&/^[^ #]/{c=0} c&&/max_memory_gb:/{print $2; exit}' config.yaml)
MEM="${MEM_MAX:-${gb:-6}G}"
NICE=$(awk '/^compute:/{c=1;next} c&&/^[^ #]/{c=0} c&&/nice_level:/{print $2; exit}' config.yaml)
script="${2:-$1}"; case "$script" in -*) script="$1";; esac
name="stockbot-$(basename -- "$script" .py | tr -c 'a-zA-Z0-9_\n-' '-')-$$"

exec systemd-run --user --scope --quiet --collect \
    --unit="$name" \
    -p MemoryMax="$MEM" -p MemorySwapMax=512M \
    nice -n "${NICE:-10}" "$@"
