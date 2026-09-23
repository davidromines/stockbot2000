"""
AI Development Orchestration. Claude architects and reviews; DeepSeek implements.

THE LOOP
--------
    claude          task specification, written here or by hand
      ↓
    implement       DeepSeek writes code on a feature branch
      ↓
    test            run_tests.sh is the gate, not an opinion
      ↓
    review          a human or Claude reads the diff and decides
      ↓
    approve/reject  reject returns the task to IN_PROGRESS with feedback
      ↓
    merge

WHAT THIS DELIBERATELY DOES NOT DO
-----------------------------------
**It does not auto-merge.** A passing test suite means the known failures did
not recur; it does not mean the change is correct. Every defect in this
project's history passed every test that existed at the time, because the tests
that would have caught them had not been written yet. Approval stays manual.

**It does not let the model choose its own context.** `build_context` assembles
project state, the files the task names, and the task. A model that can pull
whatever it likes will pull too much, and context is the cost being optimised.

**It does not touch main.** Work happens on `ado/TASK-nnn`. A bad implementation
is discarded by deleting a branch.

WHY GIT IS THE SOURCE OF TRUTH
-------------------------------
Because the alternative is trusting that the file on disk is what was reviewed.
The branch is the unit of work, the diff is what gets reviewed, and the commit
is the record of what was accepted.

Usage:
    python orchestrator.py status
    python orchestrator.py new --objective "..." --component storage
    python orchestrator.py next-task
    python orchestrator.py implement TASK-001
    python orchestrator.py test
    python orchestrator.py review TASK-001
    python orchestrator.py approve TASK-001
    python orchestrator.py merge TASK-001
    python orchestrator.py reject TASK-001 --feedback "..."
    python orchestrator.py usage
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

import ado_task as T
import storage
from llm import get_provider
from llm import provider as prov
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ado")

SYSTEM_PROMPT = """You are the implementation engineer for Stockbot2000, a \
quantitative trading research system. You write Python.

YOU HAVE NO TOOLS. You cannot run commands, read the filesystem, or call \
functions. There is no shell and no further turn. Everything you are given is \
in this message, and your reply is the deliverable. Attempting a tool call \
produces nothing and wastes the request — the first attempt at this task did \
exactly that and had to be discarded.

You will be given the project state, the files relevant to one task, and the \
task specification. Implement exactly that task and reply with the file.

Rules that are not negotiable:

1. Output ONLY files, each as a fenced block preceded by a line of the form
   FILE: path/to/file.py
   Do not explain, summarise, or comment outside the blocks.
2. Output the COMPLETE file contents, not a diff or a fragment. Files are
   written verbatim to disk.
3. Do not modify files the task did not name.
4. `import runtime` must be the first import in any module that imports numpy,
   pandas or xgboost. This is load-bearing: those libraries read their thread
   limits once at import time.
5. Read configuration from config.yaml. Do not hardcode paths or thresholds.
6. Never place a credential in a file. Secrets live in 0600 files under the
   home directory.
7. Comments explain WHY, not what. Explain the reasoning behind a non-obvious
   choice; do not narrate the code.
8. This project's entire history is measurement bugs that ran fine and computed
   the wrong thing. If a requirement is ambiguous in a way that affects
   correctness, implement the conservative reading and note it in a comment.

Your entire reply must look like this, with nothing before or after:

FILE: path/to/module.py
```python
<the complete file>
```
"""


def sh(cmd: list, check: bool = False) -> tuple:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {p.stderr[:300]}")
    return p.returncode, p.stdout, p.stderr


def _branch(task: T.Task) -> str:
    return task.branch or f"ado/{task.task_id.lower()}"


# --- commands ---------------------------------------------------------------

def cmd_status(args, cfg) -> int:
    tasks = T.all_tasks()
    print(f"\n  ADO STATUS")
    print("  " + "-" * 62)
    for st in T.STATES:
        got = [t for t in tasks if t.state == st]
        print(f"  {st:<14}{len(got):>3}")
        for t in got:
            print(f"      {t.task_id:<12}{t.component:<14}{t.objective[:40]}")
    rc, out, _ = sh(["git", "branch", "--list", "ado/*"])
    branches = [b.strip().lstrip("* ") for b in out.splitlines() if b.strip()]
    print(f"  {'branches':<14}{len(branches):>3}  {', '.join(branches) or '-'}")
    conn = storage.connect(cfg["database"]["market_data_path"])
    u = prov.usage_summary(conn)
    print("  " + "-" * 62)
    print(f"  delegated calls {u['calls']}, "
          f"{u['prompt_tokens']:,} in / {u['completion_tokens']:,} out, "
          f"est ${u['cost_usd']:.4f}")
    conn.close()
    return 0


def cmd_new(args, cfg) -> int:
    t = T.Task(task_id=args.task_id or T.next_id(), objective=args.objective,
               component=args.component, priority=args.priority)
    t.branch = _branch(t)
    p = t.save()
    print(f"  created {p}")
    print("  Edit it to add requirements, constraints and ACCEPTANCE CRITERIA.")
    print("  A task without checkable acceptance criteria cannot be gated, and")
    print("  an ungated task is one you have to read line by line.")
    return 0


def cmd_next(args, cfg) -> int:
    todo = [t for t in T.all_tasks() if t.state == "TODO"]
    if not todo:
        print("  nothing in TODO")
        return 0
    order = {"high": 0, "normal": 1, "low": 2}
    todo.sort(key=lambda t: (order.get(t.priority, 1), t.task_id))
    t = todo[0]
    blocked = [d for d in t.dependencies
               if d and T.load(d).state != "COMPLETE"]
    print(f"\n  NEXT: {t.task_id}  [{t.priority}]  {t.component}")
    print(f"  {t.objective}")
    if blocked:
        print(f"  BLOCKED by {', '.join(blocked)}")
    else:
        print(f"  run: python orchestrator.py implement {t.task_id}")
    return 0


def cmd_implement(args, cfg) -> int:
    task = T.load(args.task_id)
    if task.state not in ("TODO", "IN_PROGRESS"):
        print(f"  {task.task_id} is {task.state}; nothing to implement")
        return 1
    if not task.acceptance:
        print(f"  {task.task_id} has NO acceptance criteria. Refusing.")
        print("  The gate cannot evaluate work with no stated definition of done.")
        return 1

    branch = _branch(task)
    rc, out, _ = sh(["git", "rev-parse", "--verify", branch])
    if rc != 0:
        sh(["git", "checkout", "-b", branch], check=True)
    else:
        sh(["git", "checkout", branch], check=True)
    task.branch = branch
    if task.state == "TODO":
        task.move_to("IN_PROGRESS")
    else:
        task.save()

    context = T.build_context(task)
    feedback = Path(f"tasks/feedback/{task.task_id}.md")
    if feedback.exists():
        context += ("\n\n---\n\n# REVIEW FEEDBACK — address every point\n\n"
                    + feedback.read_text())

    log.info(f"sending {len(context):,} chars to the implementation model")
    p = get_provider(cfg)
    resp = p.complete(SYSTEM_PROMPT, context,
                      max_tokens=int(cfg.get("ado", {}).get("max_tokens", 8000)))

    conn = storage.connect(cfg["database"]["market_data_path"])
    rates = (cfg.get("ado", {}) or {}).get("rates", {})
    prov.record(conn, resp, "implement", task.task_id, rates)
    conn.close()

    # The closing fence must be the LAST one before the next FILE: marker or
    # the end of the response. A non-greedy match to the first closing fence
    # silently truncates any file that CONTAINS a fenced block — which every
    # markdown document with a code sample does. ARCHITECTURE.md was cut off at
    # exactly the line where its pipeline diagram began, twice, and it read as
    # the model failing to finish rather than the parser discarding the rest.
    files = re.findall(
        r"^FILE:\s*(\S+)\s*\n```(?:\w+)?\n(.*?)\n```[ \t]*(?=\n*(?:^FILE:|\Z))",
        resp.text, re.M | re.S)
    if not files:
        # Near-miss: a fenced block whose first line is a path comment. Accepted
        # because rejecting a formatting slip costs a full request to fix.
        files = [(m.group(1), m.group(2)) for m in re.finditer(
            r"```(?:python)?\n#\s*(?:FILE:\s*)?([\w./\-]+\.py)\s*\n(.*?)\n```",
            resp.text, re.S)]
        if files:
            log.warning("accepted near-miss format: path in a leading comment")
    if not files:
        # Distinguish a TRUNCATED response from a malformed one. A FILE header
        # with an opening fence and no closing fence means the model ran out of
        # output budget mid-file — TASK-015 stopped mid-line at 28.5 KB. Calling
        # that "no FILE blocks" sent the diagnosis toward the format, when the
        # fix is to ask for a shorter file or split the task.
        opened = len(re.findall(r"^FILE:\s*\S+\s*\n```", resp.text, re.M))
        fences = resp.text.count("```")
        if opened and fences % 2 == 1:
            print(f"  response TRUNCATED at the output limit: {len(resp.text):,} "
                  f"chars, a file was opened and never closed. Ask for a "
                  f"shorter file or split the task. Raw response saved.")
        else:
            print("  model returned no FILE blocks. Raw response saved.")
        Path(f"tasks/feedback/{task.task_id}.raw.md").parent.mkdir(parents=True, exist_ok=True)
        Path(f"tasks/feedback/{task.task_id}.raw.md").write_text(resp.text)
        return 1

    written = []
    for path, body in files:
        # A task names the files it may touch. Anything else is the model
        # deciding scope for itself, which is how unrelated code changes appear
        # in a diff nobody asked for.
        if task.files and path not in task.files:
            print(f"  REFUSED {path}: not named in the task's Relevant files")
            continue
        fp = Path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(body + "\n", encoding="utf-8")
        written.append(path)

    print(f"\n  {task.task_id} implemented on {branch}")
    print(f"  files written: {', '.join(written) or 'none'}")
    print(f"  tokens: {resp.prompt_tokens:,} in / {resp.completion_tokens:,} out"
          f"  est ${resp.cost_usd(rates):.4f}  {resp.latency_s}s  [{resp.model}]")
    print(f"  next: python orchestrator.py test")
    return 0 if written else 1


def cmd_test(args, cfg) -> int:
    rc, out, err = sh(["./run_tests.sh"])
    print(re.sub(r"\x1b\[[0-9;]*m", "", out))
    if err.strip():
        print(err[:600])
    return rc


def cmd_review(args, cfg) -> int:
    task = T.load(args.task_id)
    branch = _branch(task)
    print(f"\n  REVIEW {task.task_id} on {branch}")
    print("  " + "-" * 62)
    rc, out, _ = sh(["git", "diff", "main...HEAD", "--stat"])
    print(out or "  (no committed diff yet)")
    rc, out, _ = sh(["git", "status", "--short"])
    print("  uncommitted:\n" + (out or "  (clean)"))
    print("\n  Acceptance criteria to check:")
    for i, a in enumerate(task.acceptance, 1):
        print(f"    {i}. {a}")
    trc = cmd_test(args, cfg)
    print(f"  gate: {'PASS' if trc == 0 else 'FAIL'}")
    print("\n  A passing gate means the KNOWN failures did not recur. It does")
    print("  not mean the change is correct — every bug in this project's")
    print("  history passed every test that existed when it shipped.")
    print(f"  then: approve {task.task_id}   or   reject {task.task_id} --feedback '...'")
    if task.state == "IN_PROGRESS":
        task.move_to("REVIEW")
    return 0


def cmd_merge(args, cfg) -> int:
    """
    Merge an approved task. Refuses anything not COMPLETE.

    Added because the first real run merged a branch while its task was still
    IN_PROGRESS — the process was followed by hand, and by hand it was skipped.
    A step that depends on remembering is not a step.
    """
    task = T.load(args.task_id)
    if task.state != "COMPLETE":
        print(f"  {task.task_id} is {task.state}, not COMPLETE. Refusing to merge.")
        print("  run: review then approve")
        return 1
    if cmd_test(args, cfg) != 0:
        print("  gate FAILED — refusing to merge")
        return 1
    branch = _branch(task)
    sh(["git", "checkout", "main"], check=True)
    rc, out, err = sh(["git", "merge", "--no-ff", branch,
                       "-m", f"Merge ADO {task.task_id}: {task.objective[:60]}"])
    print(out or err)
    return rc


def cmd_approve(args, cfg) -> int:
    task = T.load(args.task_id)
    if task.state != "REVIEW":
        print(f"  {task.task_id} is {task.state}, not REVIEW")
        return 1
    if cmd_test(args, cfg) != 0:
        print("  gate FAILED — refusing to approve")
        return 1
    task.move_to("COMPLETE")
    print(f"  {task.task_id} -> COMPLETE on branch {_branch(task)}")
    print(f"  merge when ready:  git checkout main && git merge --no-ff {_branch(task)}")
    return 0


def cmd_reject(args, cfg) -> int:
    task = T.load(args.task_id)
    fb = Path("tasks/feedback"); fb.mkdir(parents=True, exist_ok=True)
    (fb / f"{task.task_id}.md").write_text(args.feedback or "See review notes.")
    if task.state == "REVIEW":
        task.move_to("IN_PROGRESS")
    print(f"  {task.task_id} -> IN_PROGRESS with feedback recorded")
    print(f"  re-run: python orchestrator.py implement {task.task_id}")
    return 0


def cmd_usage(args, cfg) -> int:
    conn = storage.connect(cfg["database"]["market_data_path"])
    prov.init(conn)
    u = prov.usage_summary(conn)
    print(f"\n  DELEGATED WORK")
    print("  " + "-" * 54)
    print(f"  calls              {u['calls']:>10,}")
    print(f"  prompt tokens      {u['prompt_tokens']:>10,}")
    print(f"  completion tokens  {u['completion_tokens']:>10,}")
    print(f"  estimated cost     {'$' + format(u['cost_usd'], '.4f'):>10}")
    print("\n  By task:")
    for r in conn.execute("""SELECT task_id, COUNT(*) n, SUM(prompt_tokens) pin,
            SUM(completion_tokens) pout, SUM(cost_usd) c FROM llm_calls
            WHERE ok=1 GROUP BY task_id ORDER BY c DESC LIMIT 15"""):
        print(f"    {r['task_id'] or '-':<14}{r['n']:>3} calls "
              f"{r['pin']:>9,} in {r['pout']:>8,} out  ${r['c']:.4f}")
    conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("next-task")
    sub.add_parser("test")
    sub.add_parser("usage")
    n = sub.add_parser("new")
    n.add_argument("--objective", required=True)
    n.add_argument("--component", default="general")
    n.add_argument("--priority", default="normal", choices=("high", "normal", "low"))
    n.add_argument("--task-id")
    for name in ("implement", "review", "approve", "merge"):
        s = sub.add_parser(name); s.add_argument("task_id")
    r = sub.add_parser("reject"); r.add_argument("task_id"); r.add_argument("--feedback")
    a = ap.parse_args()
    T.ensure_dirs()
    cfg = load_config()
    fn = {"status": cmd_status, "new": cmd_new, "next-task": cmd_next,
          "implement": cmd_implement, "test": cmd_test, "review": cmd_review,
          "approve": cmd_approve, "reject": cmd_reject, "usage": cmd_usage,
          "merge": cmd_merge}[a.cmd]
    return fn(a, cfg)


if __name__ == "__main__":
    sys.exit(main())
