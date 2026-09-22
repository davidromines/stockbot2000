"""
Governed generation. Phase 8, item 23.

WHAT "GOVERNED" MEANS, AND WHY IT IS NOT JUST UNFREEZING
----------------------------------------------------------
Search was frozen on 2026-09-22 because 1.03M trials had created a severe
multiple-testing burden: further search on the same data was adding less
information than independent forward observation. Item 23 asks for generation
to be re-enabled *from the factory* — which is not the same as turning the
search back on.

Ungoverned, the loop was: run overnight, collect survivors, look at what they
found. Four searches ran that way and every one located its result in the
scoreboard rather than in the market. The binding constraint was never the
amount of search.

So generation now requires passing five gates before a single genome is drawn:

  1. A REGISTERED EXPERIMENT. What is being tested, and what would count as it
     failing, written down before any result exists.
  2. SEED_MODE NONE. No hand-written rules and no descendants of them. The
     seeded-vs-seed-free comparison showed 12.8% of a seeded arm carries a seed
     structure that the search never finds on its own.
  3. A TRIAL BUDGET, declared up front and charged to the append-only ledger.
     The bar every future result must clear rises permanently by the amount
     spent, so the amount is stated before it is spent rather than discovered
     afterwards.
  4. THE FREEZE, explicitly acknowledged. A frozen search stays frozen unless
     the experiment names the freeze and says why this run is worth it.
  5. ANCESTRY RECORDING, on by default and not switchable off here.

None of these makes a search more likely to find something real. They make it
impossible to run one without a record of what was being looked for — which is
the difference between an experiment and a fishing trip, and this project has
paid for the distinction four times.

THIS MODULE DOES NOT UNFREEZE ANYTHING
----------------------------------------
`authorize()` reports whether a run WOULD be permitted and what is missing.
Flipping `search.mode` to ACTIVE is a human edit to `config.yaml`, deliberately
left outside this code: a module that can lift its own restriction is not a
governor.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import experiment_registry as reg
import multiple_testing as mt
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("factory")

REQUIRED_SEED_MODE = "NONE"


class Refused(RuntimeError):
    pass


def _search_mode(cfg: dict) -> str:
    return (cfg.get("search") or {}).get("mode", "ACTIVE")


def authorize(conn, cfg: dict, experiment_id: str | None,
              budget: int | None) -> dict:
    """
    May a generation run proceed? Returns every reason it may not.

    Reasons accumulate rather than short-circuit. Reporting only the first
    blocker invites clearing it and re-running, discovering the next, and
    treating governance as a queue of obstacles instead of a description of what
    a legitimate run requires.
    """
    blockers, notes = [], []
    lab = cfg.get("lab") or {}
    mode = _search_mode(cfg)

    # 1. A registered experiment.
    exp = None
    if not experiment_id:
        blockers.append(
            "no experiment named. Generation requires a REGISTERED experiment "
            "stating what is being tested and what would count as it failing, "
            "written before any result exists.")
    else:
        try:
            exp = reg.get(conn, experiment_id)
        except Exception as e:
            blockers.append(f"experiment {experiment_id!r} not found: {e}")
        else:
            if exp["status"] not in (reg.REGISTERED, reg.RUNNING):
                blockers.append(
                    f"experiment {experiment_id} is {exp['status']}, not "
                    f"REGISTERED or RUNNING. A DRAFT can still be edited after "
                    f"seeing a result, which is the whole thing registration "
                    f"prevents.")
            else:
                notes.append(f"experiment {experiment_id} v{exp['version']} "
                             f"({exp['status']}), spec {exp['spec_hash'][:12]}")

    # 2. Seed mode.
    seed_mode = str(lab.get("seed_mode", "NONE")).upper()
    if seed_mode != REQUIRED_SEED_MODE:
        blockers.append(
            f"lab.seed_mode is {seed_mode!r}, must be {REQUIRED_SEED_MODE!r}. "
            f"The seeded arm of the section 3 comparison carried a seed "
            f"structure in 12.8% of its candidates against 0.0% of the "
            f"seed-free arm — structures the search never rediscovers alone.")
    else:
        notes.append("seed_mode NONE — no hand-written rules, no descendants")

    # 3. A declared budget, priced against the standing ledger.
    counts = mt.count(conn)
    if not budget or budget <= 0:
        blockers.append("no trial budget declared. The bar every future result "
                        "must clear rises permanently by whatever is spent, so "
                        "the amount is stated before it is spent.")
    else:
        before = counts["total_trials"]
        after = before + budget
        notes.append(f"budget {budget:,} trials: ledger {before:,} -> {after:,}, "
                     f"noise bar {mt.noise_max_sharpe(before):.2f} -> "
                     f"{mt.noise_max_sharpe(after):.2f} SE")

    # 4. The freeze.
    if mode == "FROZEN":
        ack = ""
        if exp:
            import json
            try:
                ack = (json.loads(exp["spec"]) or {}).get("freeze_justification", "")
            except Exception:
                ack = ""
        if not ack.strip():
            blockers.append(
                "search.mode is FROZEN and the experiment does not carry a "
                "'freeze_justification'. The freeze was a deliberate decision "
                "about multiple testing, not an outage — a run during it has to "
                "say why it is worth more than the forward observation it "
                "displaces.")
        else:
            notes.append(f"freeze acknowledged: {ack[:70]}")

    # 5. Ancestry is not optional and is not configurable here.
    notes.append("ancestry recorded for every candidate (not switchable)")

    return {"permitted": not blockers, "blockers": blockers, "notes": notes,
            "mode": mode, "trials_now": counts["total_trials"],
            "budget": budget, "experiment": experiment_id}


def render(a: dict) -> str:
    L = ["", "  GOVERNED GENERATION — authorisation check",
         f"  search.mode = {a['mode']}   ledger = {a['trials_now']:,} trials",
         "  " + "-" * 74]
    for n in a["notes"]:
        L.append(f"  ok      {n}")
    for b in a["blockers"]:
        first, *rest = b.split(". ")
        L.append(f"  BLOCKED {first}.")
        for r in rest:
            if r.strip():
                L.append(f"          {r.strip()}")
    L += ["  " + "-" * 74]
    if a["permitted"]:
        L += ["  PERMITTED. Generation may proceed under this experiment.", ""]
    else:
        L += [f"  REFUSED — {len(a['blockers'])} requirement(s) unmet.", "",
              "  Nothing here can be waived by this module, and this module",
              "  cannot lift the freeze: flipping search.mode to ACTIVE is a",
              "  human edit to config.yaml. A governor that can lift its own",
              "  restriction is not a governor.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", help="a REGISTERED experiment id")
    ap.add_argument("--budget", type=int, help="trials this run may spend")
    ap.add_argument("--check", action="store_true",
                    help="report whether a run would be permitted")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    res = authorize(conn, cfg, a.experiment, a.budget)
    print(render(res))
    conn.close()
    return 0 if res["permitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
