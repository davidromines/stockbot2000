"""
REGRESSION: a frozen search must stay frozen.

Phase 6 section 1 freezes continuous discovery deliberately. The failure this
guards against is subtle and would be hard to notice: a watchdog that restarts a
deliberately frozen search makes the loop appear to die repeatedly while
something keeps reviving it, and the multiple-testing burden the freeze exists
to stop keeps growing.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_search_freeze.py
"""
import runtime  # noqa: F401
from pathlib import Path

from universe import load_config

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


cfg = load_config()
search = cfg.get("search") or {}

check("config declares a search mode", "mode" in search, str(search))
check("mode is one of FROZEN / ACTIVE",
      search.get("mode") in ("FROZEN", "ACTIVE"), str(search.get("mode")))
check("the freeze records WHY, not just that it is frozen",
      bool(search.get("frozen_reason")),
      "a freeze without a stated reason gets quietly undone by the next person")

loop = Path("lab_loop.sh").read_text()
check("lab_loop.sh reads the mode", "FROZEN" in loop and "search" in loop)
check("lab_loop.sh EXITS on a frozen mode rather than spinning",
      "FROZEN" in loop and "break" in loop,
      "a sleep loop would hold the CPU the freeze exists to release")

dog = Path("lab_watchdog.sh").read_text()
check("the watchdog checks the mode BEFORE restarting", "FROZEN" in dog)
i_mode = dog.find("FROZEN")
i_start = dog.find("setsid nohup bash ./lab_loop.sh")
check("the mode check precedes the restart in the file",
      0 < i_mode < i_start,
      f"mode at {i_mode}, restart at {i_start} — the check must come first")

check("STOP_LAB still halts both", "STOP_LAB" in loop and "STOP_LAB" in dog)

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
