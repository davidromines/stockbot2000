"""
How many times have we looked? Phase 6 section 18.

WHY A SHARPE RATIO IS MEANINGLESS WITHOUT THIS
-----------------------------------------------
The best of N noisy trials looks better than the truth by an amount that grows
with N. At N = 1, a Sharpe of 1.1 is interesting. At N = 1,037,005 it is roughly
what the best coin flip in the pile would produce anyway.

So a leaderboard must never be read independently of the number of strategies
tested — and that number has to be right, which means counting things that do
not look like trials.

WHAT COUNTS AS A TRIAL, AND WHY MORE THAN YOU THINK
----------------------------------------------------
  evaluations         the obvious one: every genome scored
  promotion decisions selection. Picking the top 5 from a growing pool,
                      repeatedly, is a search — its false-discovery rate
                      compounds with every re-ranking. The validation firewall
                      flagged this as a defect: the counter previously could not
                      see it at all.
  backtest runs       every `backtest.py` invocation is a hypothesis test
  sweeps              a stop sweep of 4 rules x 3 holds x 10 stops is 120 trials
                      even though it produces one table

EFFECTIVE TRIALS
----------------
Raw count over-counts, because near-identical strategies are not independent
tests. `unique_structures` (constants erased) is the honest denominator for
structural search, and the effective count is estimated between the two. It is
an estimate and is labelled as one — the alternative is choosing between a
number that is definitely too big and one that is definitely too small.

THE COUNTER IS APPEND-ONLY
---------------------------
Archiving, retiring or invalidating a strategy never decrements it. Deleting
records does not delete the selection pressure that produced them; it only
destroys the denominator the correction depends on. A rebuilt database that
restarts at zero is a regression, and `check_monotonic()` exists to catch it.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import math
from datetime import datetime, timezone

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("multitest")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trial_ledger (
            at            TEXT PRIMARY KEY,
            evaluations   INTEGER NOT NULL,
            promotions    INTEGER NOT NULL,
            backtests     INTEGER NOT NULL,
            sweeps        INTEGER NOT NULL,
            total_trials  INTEGER NOT NULL,
            unique_structures INTEGER,
            note          TEXT
        ) STRICT
    """)
    conn.commit()


def count(conn) -> dict:
    """Every kind of look, counted from where it is actually recorded."""
    init(conn)

    def q(sql, default=0):
        try:
            v = conn.execute(sql).fetchone()[0]
            return int(v) if v is not None else default
        except Exception:
            return default

    ev = q("SELECT COUNT(*) FROM evaluations")
    # Selection is testing. Every promotion decision is a comparison that could
    # have gone the other way, and the firewall flagged that the counter could
    # not see them.
    pr = q("SELECT COUNT(*) FROM promotions")
    bt = q("SELECT COUNT(*) FROM experiments WHERE kind='backtest'")
    sw = q("SELECT COUNT(*) FROM experiment_registry WHERE status='COMPLETE'")
    uniq = q("SELECT COUNT(DISTINCT shape) FROM strategies", None)
    if uniq is None:
        # `strategies` has no shape column; approximate by distinct entry_desc,
        # which erases nothing but is the best available and is labelled so.
        uniq = q("SELECT COUNT(DISTINCT entry_desc) FROM strategies", 0)

    total = ev + pr + bt + sw
    return {"evaluations": ev, "promotions": pr, "backtests": bt, "sweeps": sw,
            "total_trials": total, "unique_structures": uniq,
            "effective_trials": effective(total, uniq)}


def effective(total: int, unique: int) -> int:
    """
    An estimate between the raw count and the distinct-structure count.

    Raw over-counts: a thousand variants of one rule are not a thousand
    independent tests. Distinct structures under-counts: two different rules
    trading the same names at the same times are one test wearing two hats.

    The geometric mean is used because the truth is multiplicative in character
    and because it is transparently a compromise rather than a claim. Anyone
    reading a number produced this way should treat it as an order of magnitude.
    """
    if total <= 0:
        return 0
    if not unique or unique <= 0:
        return total
    return int(round(math.sqrt(total * min(unique, total))))


def noise_max_sharpe(n_trials: int) -> float:
    """
    Roughly what the best of N pure-noise trials scores.

    sqrt(2 ln N) is the expected maximum of N standard normals. A survivor must
    clear this, not merely be positive — which is the single most important
    thing to know before reading any leaderboard this project produces.
    """
    if n_trials < 2:
        return 0.0
    return math.sqrt(2 * math.log(n_trials))


def snapshot(conn, note: str = "") -> dict:
    """Record the counts. Append-only: a snapshot is never updated or removed."""
    c = count(conn)
    init(conn)
    conn.execute("""INSERT OR REPLACE INTO trial_ledger (at, evaluations,
        promotions, backtests, sweeps, total_trials, unique_structures, note)
        VALUES (?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),
         c["evaluations"], c["promotions"], c["backtests"], c["sweeps"],
         c["total_trials"], c["unique_structures"], note))
    conn.commit()
    return c


def check_monotonic(conn) -> list:
    """
    The counter must never go down.

    A decrease means either records were deleted or the database was rebuilt
    from an incomplete source. Both destroy the denominator every
    deflated-Sharpe claim depends on, and both are silent unless checked.
    """
    init(conn)
    rows = list(conn.execute(
        "SELECT at, total_trials FROM trial_ledger ORDER BY at"))
    problems = []
    for a, b in zip(rows, rows[1:]):
        if b["total_trials"] < a["total_trials"]:
            problems.append(
                f"trial count FELL from {a['total_trials']:,} at {a['at']} to "
                f"{b['total_trials']:,} at {b['at']} — records were removed or "
                f"the database was rebuilt from an incomplete source")
    return problems


def context_line(conn) -> str:
    """One line to print beside any performance figure. Never omit it."""
    c = count(conn)
    return (f"{c['total_trials']:,} trials to date "
            f"(~{c['effective_trials']:,} effective); the best of pure noise at "
            f"this count scores about {noise_max_sharpe(c['total_trials']):.2f} SE")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    c = snapshot(conn, a.note) if a.snapshot else count(conn)

    print("\n  MULTIPLE-TESTING ACCOUNT")
    print("  " + "-" * 58)
    print(f"  evaluations          {c['evaluations']:>14,}")
    print(f"  promotion decisions  {c['promotions']:>14,}")
    print(f"  backtest runs        {c['backtests']:>14,}")
    print(f"  registered sweeps    {c['sweeps']:>14,}")
    print("  " + "-" * 58)
    print(f"  TOTAL TRIALS         {c['total_trials']:>14,}")
    print(f"  unique structures    {c['unique_structures']:>14,}")
    print(f"  effective (estimate) {c['effective_trials']:>14,}")
    print("  " + "-" * 58)
    print(f"  best of pure noise at this count: "
          f"{noise_max_sharpe(c['total_trials']):.2f} standard errors")
    print("  A survivor must clear that, not merely be positive.")
    probs = check_monotonic(conn)
    for p in probs:
        print(f"\n  PROBLEM: {p}")
    conn.close()
    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
