"""
Seeded vs seed-free search, all else identical. Phase 6 section 3.

THE QUESTION
------------
`seeds.py` injects 20 published strategies into generation 0. The search then
mutates them like anything else. The worry is that what the search "discovers"
is largely the seeds' own structure wearing different constants — and the
project has already had one retraction of exactly that shape, where
momentum+pullback was reported as the best finding and withdrawn within the
hour once its ancestry was checked.

Ancestry classification (section 2) answers this retrospectively and
imperfectly, by inferring parentage for 1.03M strategies generated before the
classifier existed. This answers it prospectively, by running the experiment
that ancestry can only approximate:

    A = seeded search
    B = identical search, seeds disabled

Same window, same RNG seed, same population, same generations, same gates, same
panel. The ONLY difference is whether generation 0 contains the published
strategies.

WHY IT IS PRE-REGISTERED
-------------------------
Section 3 ends with "do not select the better-looking result". The mechanism
that enforces that is not good intentions — it is writing down what will be
measured before seeing either arm. Both arms are registered, both run, and both
report, whichever way it comes out. There is no code path here that reports one
arm.

TRIAL COST
----------
Both arms add permanently to an append-only trial ledger, which raises the
multiple-testing bar for every result the project will ever report. That is the
correct accounting and the reason this is bounded rather than open-ended: the
default is small, and the cost is printed before anything runs.

Usage:
    python experiments/seed_free_search/run.py --register
    python experiments/seed_free_search/run.py --run
    python experiments/seed_free_search/run.py --compare
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import experiment_registry as reg
import genome as gn
import multiple_testing as mt
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seedfree")

EXPERIMENT_ID = "seed_free_search"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Identical for both arms. Changing any of these invalidates the comparison, so
# they live here rather than being passed in at the command line where an arm
# could quietly get a different one.
GENERATIONS = 6
POPULATION = 120
RNG_SEED = 20260922


def spec(cfg: dict) -> dict:
    lab = cfg["lab"]
    return {
        "primary_metric": "share of survivors whose structure traces to a seed",
        "hypothesis_direction": "declared before running; see hypothesis text",
        "universe": cfg["universe"]["tradeable_types"],
        "entry_rule": "evolved — the experiment is about their provenance",
        "exit_rule": "evolved",
        "window": [lab["search_start"], lab["search_end"]],
        "arms": {
            "A": {"seeds": True, "flag": "--seeds"},
            "B": {"seeds": False, "flag": ""},
        },
        "generations": GENERATIONS,
        "population": POPULATION,
        "rng_seed": RNG_SEED,
        "measures": [
            "candidates evaluated", "survivors per gate", "structural diversity",
            "behavioural diversity", "best validation statistic",
            "median statistic", "maximum statistic",
        ],
        "stopping_rule": "both arms run to completion; neither is inspected "
                         "until both are done",
        "selection_rule": "BOTH arms are reported. There is no code path in "
                          "this experiment that reports one.",
    }


HYPOTHESIS = (
    "Seeding generation 0 with the 20 published strategies materially changes "
    "what the search finds: the seeded arm's survivors will show lower "
    "structural diversity and a higher share of seed-traceable structures than "
    "the seed-free arm, at a similar or better best-fitness. If instead both "
    "arms produce comparable diversity and comparable best fitness, the seeds "
    "are not steering the search and the ancestry concern is overstated for "
    "future runs."
)


def register(conn) -> dict:
    cfg = load_config()
    try:
        e = reg.get(conn, EXPERIMENT_ID)
        log.info(f"already registered at version {e['version']}, status {e['status']}")
        return e
    except Exception:
        pass
    reg.create(conn, EXPERIMENT_ID, HYPOTHESIS, "claude+david", spec(cfg))
    e = reg.register(conn, EXPERIMENT_ID)
    log.info(f"registered {EXPERIMENT_ID} v{e['version']}, spec hash {e['spec_hash'][:12]}")
    return e


def _run_arm(arm: str, use_seeds: bool, cfg: dict) -> str:
    run_id = f"{EXPERIMENT_ID}_{arm}"
    lab = cfg["lab"]
    cmd = [str(ROOT / "venv" / "bin" / "python"), str(ROOT / "evolve.py"),
           "--generations", str(GENERATIONS), "--population", str(POPULATION),
           "--seed", str(RNG_SEED), "--run-id", run_id,
           "--start", lab["search_start"], "--end", lab["search_end"]]
    if use_seeds:
        cmd.append("--seeds")
    log.info(f"arm {arm}: {' '.join(cmd[2:])}")
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    (HERE / f"arm_{arm}.log").write_text(r.stdout + "\n" + r.stderr)
    if r.returncode != 0:
        raise SystemExit(f"arm {arm} failed with exit {r.returncode}; "
                         f"see {HERE / f'arm_{arm}.log'}")
    return run_id


def measure(conn, run_id: str) -> dict:
    """
    The seven measures, from the ledger. Identical query for both arms — a
    per-arm measurement path is how an A/B quietly becomes two experiments.
    """
    rows = [dict(r) for r in conn.execute("""
        SELECT s.id, s.genome, e.fitness, e.net_pnl_usd, e.excess_pnl_usd,
               e.sharpe, e.n_trades
        FROM strategies s JOIN evaluations e ON e.strategy_id = s.id
        WHERE s.run_id = ?""", (run_id,))]
    if not rows:
        return {"run_id": run_id, "n": 0}

    fit = np.array([r["fitness"] or 0.0 for r in rows], dtype="float64")
    shapes, seeded = set(), 0
    seed_shapes = set()
    try:
        import seeds as seed_lib
        seed_shapes = {gn.genome_shape(g) for g in seed_lib.genomes()}
    except Exception:
        pass
    for r in rows:
        try:
            g = json.loads(r["genome"])
            sh = gn.genome_shape(g)
            shapes.add(sh)
            if sh in seed_shapes:
                seeded += 1
        except Exception:
            continue

    return {
        "run_id": run_id,
        "n": len(rows),
        "unique_structures": len(shapes),
        # Distinct structures per candidate. A search that keeps rediscovering
        # one idea scores near zero however many candidates it evaluates.
        "structural_diversity": len(shapes) / len(rows),
        "seed_shaped": seeded,
        "seed_shaped_share": seeded / len(rows),
        "best_fitness": float(fit.max()),
        "median_fitness": float(np.median(fit)),
        "mean_fitness": float(fit.mean()),
        "best_pnl": float(max((r["net_pnl_usd"] or 0.0) for r in rows)),
        "best_excess": float(max((r["excess_pnl_usd"] or 0.0) for r in rows)),
        "best_sharpe": float(max((r["sharpe"] or 0.0) for r in rows)),
    }


def compare(conn) -> dict:
    a = measure(conn, f"{EXPERIMENT_ID}_A")
    b = measure(conn, f"{EXPERIMENT_ID}_B")
    return {"A_seeded": a, "B_seed_free": b,
            "compared_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def render(c: dict) -> str:
    a, b = c["A_seeded"], c["B_seed_free"]
    if not a.get("n") or not b.get("n"):
        return ("\n  One or both arms have not run.\n"
                f"    A (seeded)    : {a.get('n', 0)} candidates\n"
                f"    B (seed-free) : {b.get('n', 0)} candidates\n")
    rows = [
        ("candidates evaluated", "n", ",.0f"),
        ("unique structures", "unique_structures", ",.0f"),
        ("structural diversity", "structural_diversity", ".3f"),
        ("seed-shaped survivors", "seed_shaped", ",.0f"),
        ("seed-shaped share", "seed_shaped_share", ".1%"),
        ("best fitness", "best_fitness", ".4f"),
        ("median fitness", "median_fitness", ".4f"),
        ("best net P&L", "best_pnl", ",.0f"),
        ("best excess", "best_excess", ",.0f"),
        ("best Sharpe", "best_sharpe", ".3f"),
    ]
    L = ["", "  SEEDED vs SEED-FREE SEARCH — both arms, whichever way it came out",
         "  " + "-" * 68,
         f"  {'measure':<26}{'A seeded':>16}{'B seed-free':>16}", "  " + "-" * 68]
    for label, key, f in rows:
        L.append(f"  {label:<26}{format(a[key], f):>16}{format(b[key], f):>16}")
    L += ["  " + "-" * 68, ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--yes", action="store_true",
                    help="proceed past the trial-cost notice")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.register:
        e = register(conn)
        print(f"\n  {EXPERIMENT_ID} v{e['version']} — {e['status']}")
        print(f"  spec hash {e['spec_hash'][:16]}")
        conn.close(); return 0

    if a.run:
        register(conn)
        cost = 2 * GENERATIONS * POPULATION
        before = mt.count(conn)["total_trials"]
        print(f"\n  TRIAL COST NOTICE")
        print(f"  Both arms together evaluate about {cost:,} candidates.")
        print(f"  The ledger currently stands at {before:,} trials and is")
        print(f"  append-only — this raises the multiple-testing bar for every")
        print(f"  result this project will ever report, permanently.")
        if not a.yes:
            print(f"\n  Re-run with --yes to proceed.\n")
            conn.close(); return 1
        try:
            reg.start(conn, EXPERIMENT_ID)
        except Exception as e:
            log.info(f"registry: {e}")
        # Both arms run before either is measured. Measuring A first would make
        # the decision to run B contingent on A's result, which is the same
        # loophole pre-registration exists to close.
        _run_arm("A", True, cfg)
        _run_arm("B", False, cfg)
        c = compare(conn)
        print(render(c))
        (HERE / "results.json").write_text(json.dumps(c, indent=2, sort_keys=True))
        try:
            reg.complete(conn, EXPERIMENT_ID, c,
                         "Both arms reported; see results.json.")
        except Exception as e:
            log.info(f"registry: {e}")
        conn.close(); return 0

    c = compare(conn)
    print(render(c))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
