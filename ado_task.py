"""
The task: a specification precise enough to implement without the conversation.

WHY TASKS ARE FILES IN DIRECTORIES
-----------------------------------
State is the directory a task lives in — `tasks/TODO/`, `IN_PROGRESS/`,
`REVIEW/`, `COMPLETE/`. Moving a file is the transition. That is deliberately
cruder than a status column: it means `ls tasks/REVIEW` answers "what needs my
attention" with no code running, it survives the database being rebuilt, and
git tracks the whole history for free.

A task is Markdown with a YAML-ish header. Both a person and a model read it
without tooling, which matters because the whole point is handing it to a
different model.

WHAT MAKES A TASK GOOD ENOUGH TO DELEGATE
------------------------------------------
Acceptance criteria that a test can check. "Implement the schema" is not a task;
"create these five tables, with these columns, such that `run_tests.sh` passes"
is. The gate decides whether the work is done, so if the criteria are not
checkable the gate cannot function and review falls back to reading code, which
is the expensive thing ADO exists to avoid.

CONTEXT IS DELIBERATELY SMALL
------------------------------
`build_context()` sends the project state, the named files, and the task. Not
the repository, not the conversation, not every document. Sending more is not
free — it is the cost the whole arrangement is meant to reduce, and a model that
receives 200 files will use the wrong one.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("task")

TASKS = Path("tasks")
STATES = ("TODO", "IN_PROGRESS", "REVIEW", "COMPLETE")

# Lifecycle from the ADO specification. A failed test returns to IN_PROGRESS;
# a rejected review does the same. Nothing skips REVIEW.
TRANSITIONS = {
    "TODO": {"IN_PROGRESS"},
    "IN_PROGRESS": {"REVIEW", "TODO"},
    "REVIEW": {"COMPLETE", "IN_PROGRESS"},
    "COMPLETE": set(),
}


class TaskError(RuntimeError):
    pass


@dataclass
class Task:
    task_id: str
    objective: str
    component: str = "general"
    priority: str = "normal"
    background: str = ""
    dependencies: list = field(default_factory=list)
    files: list = field(default_factory=list)
    requirements: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    acceptance: list = field(default_factory=list)
    testing: list = field(default_factory=list)
    deliverables: list = field(default_factory=list)
    state: str = "TODO"
    branch: str = ""
    created: str = field(default_factory=lambda:
                         datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # -- serialisation -------------------------------------------------------

    def to_markdown(self) -> str:
        def block(title, items):
            if not items:
                return ""
            return f"\n## {title}\n" + "".join(f"{i}. {x}\n" for i, x in
                                               enumerate(items, 1))
        L = [f"# {self.task_id}", "",
             f"- component: {self.component}",
             f"- priority: {self.priority}",
             f"- state: {self.state}",
             f"- branch: {self.branch}",
             f"- created: {self.created}",
             f"- dependencies: {', '.join(self.dependencies) or 'none'}",
             "", "## Objective", self.objective]
        if self.background:
            L += ["", "## Background", self.background]
        if self.files:
            L += ["", "## Relevant files"] + [f"- `{f}`" for f in self.files]
        out = "\n".join(L)
        out += block("Requirements", self.requirements)
        out += block("Constraints", self.constraints)
        out += block("Acceptance criteria", self.acceptance)
        out += block("Testing requirements", self.testing)
        out += block("Deliverables", self.deliverables)
        return out

    @classmethod
    def from_markdown(cls, text: str, state: str = "TODO") -> "Task":
        def meta(k, default=""):
            m = re.search(rf"^- {k}:\s*(.*)$", text, re.M)
            return m.group(1).strip() if m else default

        def section(title):
            m = re.search(rf"^## {title}\n(.*?)(?=\n## |\Z)", text, re.M | re.S)
            if not m:
                return []
            body = m.group(1).strip()
            items = re.findall(r"^\s*(?:\d+\.|-)\s*(.+)$", body, re.M)
            return [i.strip().strip("`") for i in items] if items else []

        obj = re.search(r"^## Objective\n(.*?)(?=\n## |\Z)", text, re.M | re.S)
        bg = re.search(r"^## Background\n(.*?)(?=\n## |\Z)", text, re.M | re.S)
        tid = re.search(r"^# (\S+)", text, re.M)
        deps = meta("dependencies", "none")
        return cls(
            task_id=tid.group(1) if tid else "TASK-UNKNOWN",
            objective=obj.group(1).strip() if obj else "",
            background=bg.group(1).strip() if bg else "",
            component=meta("component", "general"), priority=meta("priority", "normal"),
            state=state, branch=meta("branch"), created=meta("created"),
            dependencies=[] if deps in ("none", "") else [d.strip() for d in deps.split(",")],
            files=section("Relevant files"), requirements=section("Requirements"),
            constraints=section("Constraints"), acceptance=section("Acceptance criteria"),
            testing=section("Testing requirements"), deliverables=section("Deliverables"))

    # -- filesystem as the state machine ------------------------------------

    def path(self) -> Path:
        return TASKS / self.state / f"{self.task_id}.md"

    def save(self) -> Path:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_markdown(), encoding="utf-8")
        return p

    def move_to(self, new_state: str) -> Path:
        if new_state not in STATES:
            raise TaskError(f"unknown state {new_state!r}")
        if new_state not in TRANSITIONS[self.state]:
            # An illegal transition is a bug in the orchestrator, not a state to
            # tolerate. Allowing TODO -> COMPLETE would let work skip review.
            raise TaskError(f"illegal transition {self.state} -> {new_state}")
        old = self.path()
        self.state = new_state
        new = self.save()
        if old.exists() and old != new:
            old.unlink()
        return new


def load(task_id: str) -> Task:
    for st in STATES:
        p = TASKS / st / f"{task_id}.md"
        if p.exists():
            return Task.from_markdown(p.read_text(), state=st)
    raise TaskError(f"{task_id} not found in {'/'.join(STATES)}")


def all_tasks() -> list:
    out = []
    for st in STATES:
        for p in sorted((TASKS / st).glob("*.md")) if (TASKS / st).exists() else []:
            out.append(Task.from_markdown(p.read_text(), state=st))
    return out


def next_id() -> str:
    n = 0
    for t in all_tasks():
        m = re.match(r"TASK-(\d+)", t.task_id)
        if m:
            n = max(n, int(m.group(1)))
    return f"TASK-{n + 1:03d}"


def build_context(task: Task, max_file_bytes: int = 60_000) -> str:
    """
    The smallest useful context: project state, named files, the task.

    Not the repository and not the conversation. Every token sent is the cost
    this arrangement exists to reduce, and a model handed the whole project will
    confidently edit the wrong file.
    """
    parts = []
    state = Path("PROJECT_STATUS.md")
    if state.exists():
        parts.append("# PROJECT STATE\n\n" + state.read_text()[:8000])

    conv = Path("CLAUDE.md")
    if conv.exists():
        # Conventions only — the architecture section is large and rarely what a
        # single task needs.
        txt = conv.read_text()
        m = re.search(r"^### How to communicate.*?(?=^## )", txt, re.M | re.S)
        if m:
            parts.append("# PROJECT CONVENTIONS\n\n" + m.group(0)[:4000])

    for f in task.files:
        p = Path(f)
        if not p.exists():
            parts.append(f"# FILE (does not exist yet): {f}")
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        truncated = len(body) > max_file_bytes
        parts.append(f"# FILE: {f}"
                     + (f"  [truncated to {max_file_bytes} bytes]" if truncated else "")
                     + "\n```python\n" + body[:max_file_bytes] + "\n```")

    parts.append("# TASK\n\n" + task.to_markdown())
    return "\n\n---\n\n".join(parts)
