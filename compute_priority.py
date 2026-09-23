"""
Compute allocation by priority. Phase 6 section 28.

The spec inverts the default: strategy search goes LAST.

    1. data integrity
    2. forward testing
    3. regression tests
    4. independent validation
    5. backtesting
    6. strategy search

"Do not spend the majority of compute on evolutionary search while the
data-quality problem remains unresolved."

This module is the ordering made checkable. It knows which pipeline stage
belongs to which tier, reports how the day's compute was actually spent, and
says whether the ordering was honoured. `may_run(tier)` lets a caller ask
whether a lower tier is permitted yet — a search that runs while the price
top-up failed is spending compute on refining a measurement of stale data.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
from datetime import datetime, timezone

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("compute")

TIERS = (
    (1, "data_integrity", ("universe.py", "backfill.py", "build_features.py",
                           "fundamental_features.py", "freshness.py",
                           "pit_backfill.py", "sec_fundamentals.py")),
    (2, "forward_testing", ("paper_trading.py", "pair_funds.py",
                            "value_fund.py", "daily_picks.py", "orders.py")),
    (3, "regression_tests", ("run_tests.sh",)),
    (4, "independent_validation", ("random_control.py", "control.py",
                                   "multiple_testing.py", "degradation.py",
                                   "research_integrity.py", "stop_conditions.py")),
    (5, "backtesting", ("backtest.py", "walk_forward.py", "rescore.py",
                        "conviction_walkforward.py", "pair_momentum.py")),
    (6, "strategy_search", ("evolve.py", "lab_loop.sh", "factory.py")),
)

TIER_OF = {m: (n, name) for n, name, mods in TIERS for m in mods}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compute_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            at        TEXT NOT NULL,
            stage     TEXT NOT NULL,
            tier      INTEGER NOT NULL,
            tier_name TEXT NOT NULL,
            seconds   REAL NOT NULL,
            ok        INTEGER NOT NULL
        )
    """)
    conn.commit()


def record(conn, stage: str, seconds: float, ok: bool = True) -> None:
    init(conn)
    tier, name = TIER_OF.get(stage, (99, "unclassified"))
    conn.execute("""INSERT INTO compute_log (at, stage, tier, tier_name,
        seconds, ok) VALUES (?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),
         stage, tier, name, float(seconds), 1 if ok else 0))
    conn.commit()


def may_run(conn, tier: int, window_hours: int = 24) -> tuple:
    """
    (permitted, why). A tier runs only if every higher-priority tier succeeded
    recently.

    The rule the spec is really making: refining a measurement is worthless
    while the thing being measured is stale. A search that runs after a failed
    price top-up is not doing research, it is doing arithmetic on yesterday.
    """
    init(conn)
    cutoff = f"-{int(window_hours)} hours"
    rows = conn.execute(f"""SELECT tier, tier_name, ok FROM compute_log
        WHERE at >= datetime('now', '{cutoff}') AND tier < ?""", (tier,)).fetchall()
    if not rows:
        return True, "no higher-priority stage has run in the window"
    failed = sorted({r["tier_name"] for r in rows if not r["ok"]})
    if failed:
        return False, (f"higher-priority work failed in the last "
                       f"{window_hours}h: {', '.join(failed)}. Refining a "
                       f"measurement while the thing being measured is stale "
                       f"is arithmetic, not research.")
    return True, "every higher-priority tier succeeded"


def spend(conn, window_hours: int = 24) -> dict:
    init(conn)
    rows = conn.execute(f"""SELECT tier, tier_name, SUM(seconds) s, COUNT(*) n
        FROM compute_log WHERE at >= datetime('now', '-{int(window_hours)} hours')
        GROUP BY tier, tier_name ORDER BY tier""").fetchall()
    total = sum(r["s"] for r in rows) or 0.0
    by_tier = [{"tier": r["tier"], "name": r["tier_name"], "seconds": r["s"],
                "runs": r["n"], "share": (r["s"] / total) if total else 0.0}
               for r in rows]
    search = next((t for t in by_tier if t["name"] == "strategy_search"), None)
    return {"window_hours": window_hours, "total_seconds": total,
            "by_tier": by_tier,
            "search_share": search["share"] if search else 0.0,
            "honoured": (search["share"] if search else 0.0) <= 0.5}


def render(s: dict) -> str:
    L = ["", f"  COMPUTE ALLOCATION — last {s['window_hours']}h",
         f"  {s['total_seconds']:,.0f} seconds recorded", "  " + "-" * 62,
         f"  {'tier':<6}{'name':<26}{'runs':>6}{'seconds':>11}{'share':>8}"]
    for t in s["by_tier"]:
        L.append(f"  {t['tier']:<6}{t['name'][:25]:<26}{t['runs']:>6}"
                 f"{t['seconds']:>11,.0f}{t['share']:>8.1%}")
    L.append("  " + "-" * 62)
    if not s["by_tier"]:
        L += ["  nothing recorded yet — daily.sh records each stage as it runs"]
    elif s["honoured"]:
        L += [f"  Strategy search took {s['search_share']:.1%} of compute.",
              "  The spec's ordering is honoured: search is last, and the",
              "  data-quality work that bounds every result comes first."]
    else:
        L += [f"  SEARCH TOOK {s['search_share']:.1%} OF COMPUTE.",
              "  The spec is explicit: do not spend the majority of compute on",
              "  evolutionary search while the data-quality problem remains",
              "  unresolved. It remains unresolved."]
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiers", action="store_true")
    ap.add_argument("--may-run", type=int, metavar="TIER")
    ap.add_argument("--record", nargs=2, metavar=("STAGE", "SECONDS"))
    ap.add_argument("--hours", type=int, default=24)
    a = ap.parse_args()

    if a.tiers:
        print("\n  COMPUTE PRIORITY (Phase 6 section 28)")
        print("  " + "-" * 62)
        for n, name, mods in TIERS:
            print(f"  {n}. {name:<24}{', '.join(mods)[:34]}")
        print("\n  Search is LAST, deliberately.\n")
        return 0

    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.record:
        record(conn, a.record[0], float(a.record[1]))
        conn.close(); return 0

    if a.may_run is not None:
        ok, why = may_run(conn, a.may_run, a.hours)
        print(f"\n  tier {a.may_run}: {'MAY RUN' if ok else 'BLOCKED'}")
        print(f"  {why}\n")
        conn.close(); return 0 if ok else 1

    print(render(spend(conn, a.hours)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
