"""Generate CHANGELOG.md from the git history.

The project commits every change separately, so the git log is the change
record. A hand-maintained changelog would drift from it; this derives the
changelog instead. Merge commits from the ADO workflow duplicate the task
commit they merge, so they are excluded.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# git's own --no-merges misses nothing here, but the ADO workflow produces
# commits whose subject begins "Merge " that git does not classify as merges
# (e.g. fast-forwarded or squashed merges). Excluding by subject as well is the
# conservative reading: a duplicated entry is worse than a missing one.
MERGE_PREFIX = "Merge "

LOG_FORMAT = "%ad%x09%h%x09%s"


def parse(log_text: str) -> dict[str, list[tuple[str, str]]]:
    """Group ``git log`` output by date.

    Returns a mapping of ``YYYY-MM-DD`` to a list of ``(shorthash, subject)``
    in the order git emitted them (newest first). Dates are ordered newest
    first, matching git's default ordering.
    """
    groups: dict[str, list[tuple[str, str]]] = {}
    for line in log_text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            # A malformed line means the format string and the parser have
            # drifted apart; skipping silently would hide commits, so fail.
            raise ValueError(f"unexpected git log line: {line!r}")
        date, shorthash, subject = parts
        if subject.startswith(MERGE_PREFIX):
            continue
        groups.setdefault(date, []).append((shorthash, subject))
    return groups


def render(groups: dict[str, list[tuple[str, str]]]) -> str:
    """Render grouped commits as markdown, newest date first."""
    total = sum(len(commits) for commits in groups.values())
    lines = [
        "# Changelog",
        "",
        "Generated from git by `changelog.py`. Do not edit by hand.",
        "",
        f"{total} commits.",
        "",
    ]
    for date in sorted(groups, reverse=True):
        commits = groups[date]
        lines.append(f"## {date} ({len(commits)} commits)")
        lines.append("")
        for shorthash, subject in commits:
            lines.append(f"- {subject} (`{shorthash}`)")
        lines.append("")
    return "\n".join(lines)


def read_log(repo_dir: Path) -> str:
    """Run git log in ``repo_dir`` and return its raw output."""
    result = subprocess.run(
        [
            "git",
            "log",
            "--no-merges",
            "--date=short",
            f"--format={LOG_FORMAT}",
        ],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="CHANGELOG.md",
        help="path to write the changelog to (default: CHANGELOG.md)",
    )
    args = parser.parse_args(argv)

    # Resolve relative to the script, not the caller's cwd, so the changelog
    # always describes this repository.
    repo_dir = Path(__file__).resolve().parent
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = repo_dir / out_path

    try:
        log_text = read_log(repo_dir)
    except subprocess.CalledProcessError as exc:
        print(f"git log failed: {exc.stderr}", file=sys.stderr)
        return 1

    out_path.write_text(render(parse(log_text)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
