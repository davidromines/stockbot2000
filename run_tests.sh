#!/usr/bin/env bash
# The quality gate. Every test, one command, one exit code.
#
# WHY THIS EXISTS
# ---------------
# Until now the tests were run by hand, which means they were run when someone
# remembered — and the point of a gate is that it cannot be forgotten. ADO makes
# this load-bearing: DeepSeek's output is merged on the strength of this script
# returning 0, so "I ran the ones I thought were relevant" is not good enough.
#
# Tests are plain scripts that exit non-zero on failure rather than a pytest
# suite, matching what the project already had. The tradeoff is deliberate: no
# new dependency, no collection magic, and a failing test prints exactly what it
# checked. The cost is no fixtures and no parametrisation, which these tests do
# not need.
#
# Usage:
#   ./run_tests.sh              everything
#   ./run_tests.sh regression   one directory
set -uo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD:${PYTHONPATH:-}"
PY=./venv/bin/python

FILTER="${1:-}"
pass=0; fail=0; failed=()

printf '\n  TEST SUITE  %s\n' "$(date -u '+%F %T UTC')"
printf '  %s\n' "------------------------------------------------------------"

for t in $(find tests -name 'test_*.py' | sort); do
    [ -n "$FILTER" ] && [[ "$t" != *"$FILTER"* ]] && continue
    name=$(printf '%s' "$t" | sed 's|^tests/||; s|\.py$||')
    out=$("$PY" "$t" 2>&1); rc=$?
    if [ $rc -eq 0 ]; then
        n=$(printf '%s' "$out" | grep -c 'PASS' || true)
        printf '  \033[32mPASS\033[0m  %-34s %3s checks\n' "$name" "$n"
        pass=$((pass+1))
    else
        printf '  \033[31mFAIL\033[0m  %-34s exit %d\n' "$name" "$rc"
        printf '%s\n' "$out" | grep -E 'FAIL|Error|Traceback|assert' | head -6 | sed 's/^/          /'
        fail=$((fail+1)); failed+=("$name")
    fi
done

printf '  %s\n' "------------------------------------------------------------"
if [ $fail -eq 0 ]; then
    printf '  ALL PASS  (%d files)\n\n' "$pass"
    exit 0
fi
printf '  %d passed, \033[31m%d FAILED\033[0m: %s\n\n' "$pass" "$fail" "${failed[*]}"
exit 1
