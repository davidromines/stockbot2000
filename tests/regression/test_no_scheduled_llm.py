"""
Owner, 2026-09-28: DeepSeek is for development tasks only. No scheduled job (daily.sh,
the cron lines services.sh installs, lab_loop.sh) may call a DeepSeek path: llm_report,
knowledge_extract --run, orchestrator, or knowledge_factory --cycle with --extract > 0.
knowledge_factory's cycle must default to no extraction.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import inspect
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import knowledge_factory as kf

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


for script in ("daily.sh", "services.sh", "lab_loop.sh"):
    path = os.path.join(ROOT, script)
    if not os.path.exists(path):
        continue
    code = "\n".join(l for l in open(path).read().splitlines() if not l.lstrip().startswith("#"))
    for bad in ("llm_report.py", "knowledge_extract.py", "orchestrator.py", "ado_ship.sh"):
        check(f"{script} does not run {bad}", bad not in code)
    for m in re.finditer(r"knowledge_factory\.py[^\n]*", code):
        n = re.search(r"--extract\s+(\d+)", m.group(0))
        check(f"{script}: knowledge cycle passes --extract 0", n is not None and int(n.group(1)) == 0,
              m.group(0))

check("cycle() defaults to no extraction",
      inspect.signature(kf.cycle).parameters["extract"].default == 0)

sys.exit(1 if FAILED else 0)
