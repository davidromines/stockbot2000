"""
Where a strategy came from. Phase 6 section 2.

WHY THIS EXISTS
---------------
On 2026-09-22 the search produced 455 validation survivors across 435 distinct
structures, 85% of which contained "momentum + pullback". That was reported as
independent convergence and retracted within the hour: `seeds.py` injects a
hand-written `momentum_pullback` rule on every iteration, and 231 of the 455
carried its literal constant 40.

Nothing in the system could have caught that, because nothing recorded where a
strategy came from. A rule and its four hundred descendants were indistinguishable
from four hundred and one independent findings.

WHAT "SEED-DESCENDED" MEANS HERE
---------------------------------
Three tests, in increasing strength, because a strategy can inherit a seed's
idea without inheriting its text:

  LITERAL     carries a constant that appears in a seed and nowhere in the
              natural range of that column. The constant 40 is the worked
              example: an interquartile range of zero across hundreds of
              supposedly independent survivors is descent, not convergence.
  STRUCTURAL  shares a seed's rule SHAPE (constants erased). A mutation that
              only moved a threshold is the same idea.
  LINEAGE     an ancestor was a seed. This is the ground truth where parentage
              was recorded; the other two are what must be used for the million
              strategies generated before it was.

**A seed-derived strategy is never an independent discovery.** That is the whole
point, and it is a classification rather than a judgement: seeded strategies may
be perfectly good, they simply cannot be cited as evidence that the search found
something on its own.

WHY IT RUNS OVER HISTORY TOO
-----------------------------
The 1.03M existing strategies have no parentage recorded. Deleting them is not
an option — the trial counter is append-only and they are its denominator — so
they are classified retrospectively by the literal and structural tests. Imperfect
and stated as such, which is better than an unlabelled pile.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import logging
import re
from datetime import datetime, timezone

import genome as gn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ancestry")

INDEPENDENT = "INDEPENDENT"
SEED_LITERAL = "SEED_LITERAL"
SEED_STRUCTURAL = "SEED_STRUCTURAL"
SEED_LINEAGE = "SEED_LINEAGE"
SEED_EXACT = "SEED_EXACT"
UNKNOWN = "UNKNOWN"

# Ordered strongest-first: a strategy that is an exact seed is reported as such
# rather than as merely literal-matching.
ORDER = (SEED_EXACT, SEED_LINEAGE, SEED_STRUCTURAL, SEED_LITERAL, INDEPENDENT)


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_ancestry (
            strategy_id   TEXT PRIMARY KEY,
            seed_origin   TEXT NOT NULL,
            seed_name     TEXT,
            evidence      TEXT NOT NULL,
            generation    INTEGER,
            parent_ids    TEXT,
            classified_at TEXT NOT NULL
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anc_origin "
                 "ON strategy_ancestry(seed_origin)")
    conn.commit()


def seed_fingerprints() -> dict:
    """
    What the seeds actually contain: their shapes, and their literal constants.

    Constants are collected per column. A bare number is meaningless — 40 is
    unremarkable for `rsi_14` and impossible for `price_above_sma200` — so the
    match is always (column, value), never the value alone.
    """
    import seeds
    shapes, consts, names = {}, {}, {}
    for entry in getattr(seeds, "SEEDS", []):
        g = entry.get("genome") or {}
        entry_tree = g.get("entry")
        if not entry_tree:
            continue
        name = entry.get("name", "?")
        try:
            sh = gn.shape(entry_tree)
        except Exception:
            sh = json.dumps(entry_tree, sort_keys=True)
        shapes[sh] = name
        names[name] = entry_tree
        for col, val in _column_constants(entry_tree):
            consts.setdefault((col, val), set()).add(name)
    return {"shapes": shapes, "constants": consts, "trees": names}


# A shape simpler than this is one the search would reach without help, so a
# structural match against a seed proves nothing. Three nodes is one comparison
# (operator + column + constant); distinctiveness starts above that.
MIN_STRUCTURAL_NODES = 7


def _complexity(node) -> int:
    """Node count of a rule tree. Cheap proxy for how distinctive a shape is."""
    if not isinstance(node, dict):
        return 0
    n = 1
    for a in node.get("args") or []:
        n += _complexity(a)
    for k in ("left", "right"):
        if isinstance(node.get(k), dict):
            n += _complexity(node[k])
    return n


def _column_constants(node, col=None):
    """Every (column, constant) pair a rule compares. Recursive, order-insensitive."""
    out = []
    if not isinstance(node, dict):
        return out
    args = node.get("args") or []
    cols = [a.get("col") for a in args if isinstance(a, dict) and "col" in a]
    vals = [a.get("const") for a in args if isinstance(a, dict) and "const" in a]
    if cols and vals:
        for c in cols:
            for v in vals:
                out.append((c, float(v)))
    for a in args:
        out.extend(_column_constants(a))
    for k in ("left", "right"):
        if isinstance(node.get(k), dict):
            out.extend(_column_constants(node[k]))
    return out


def discriminating_constants(conn, min_distinct: int = 3) -> set:
    """
    Columns whose thresholds are a real CHOICE rather than the only option.

    A constant is evidence of descent only when the seed's author picked it out
    of many possibilities. `rsi_14 < 40` is a choice: the column runs 0-100 and
    40 is one of thousands of thresholds. `price_above_sma200 > 0.5` is not: the
    column holds exactly 0 and 1, so 0.5 is the only way to express "is above",
    and every independent author writes the same thing.

    Without this distinction the classifier flagged 217 survivors as
    seed-descended for using the only sensible threshold on a boolean, which
    would make the label useless — if everything is contaminated, the word stops
    discriminating.

    Returns the set of columns whose constants COUNT as evidence.
    """
    out = set()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(features)")]
    for c in cols:
        if c in ("ticker", "date"):
            continue
        try:
            # Sampled, not scanned. DISTINCT over 33M rows takes minutes per
            # column and the question only needs "two values or many" — a
            # 50,000-row sample answers that with certainty for a binary column
            # and never mistakes a continuous one for binary.
            n = conn.execute(
                f"SELECT COUNT(DISTINCT {c}) FROM "
                f"(SELECT {c} FROM features WHERE {c} IS NOT NULL LIMIT 50000)"
            ).fetchone()[0]
        except Exception:
            continue
        if n >= min_distinct:
            out.add(c)
    return out


def classify(genome: dict, fp: dict, parent_origins: list | None = None,
             discriminating: set | None = None) -> dict:
    """
    Classify one strategy. Returns the origin and the evidence for it.

    Evidence is returned rather than just a label because a classification
    nobody can check is a classification nobody should trust.
    """
    entry = (genome or {}).get("entry")
    if not entry:
        return {"origin": UNKNOWN, "seed_name": None,
                "evidence": "no entry rule"}

    # Lineage beats inference where it exists.
    if parent_origins:
        seeded = [p for p in parent_origins if p and p != INDEPENDENT]
        if seeded:
            return {"origin": SEED_LINEAGE, "seed_name": None,
                    "evidence": f"ancestor origins: {sorted(set(seeded))}"}

    try:
        sh = gn.shape(entry)
    except Exception:
        sh = None

    if sh and sh in fp["shapes"]:
        name = fp["shapes"][sh]
        exact = json.dumps(entry, sort_keys=True) == json.dumps(
            fp["trees"].get(name, {}), sort_keys=True)
        if exact:
            return {"origin": SEED_EXACT, "seed_name": name,
                    "evidence": "identical to the seed"}
        # A structural match only counts when the SHAPE is distinctive. The seed
        # `rsi_oversold` is `rsi_14 < CONST`, and that shape is shared by every
        # oversold rule anyone would ever write — flagging it made a genuinely
        # learned threshold of 33.7 look inherited. A one-comparison shape is a
        # shape the search would reach unaided, so it is not evidence; a
        # three-term conjunction is.
        if _complexity(entry) >= MIN_STRUCTURAL_NODES:
            return {"origin": SEED_STRUCTURAL, "seed_name": name,
                    "evidence": f"same distinctive rule shape as seed '{name}' "
                                f"({_complexity(entry)} nodes)"}
        # Otherwise fall through: the literal-constant test below is the
        # stronger and more specific claim for a trivial shape.

    hits = []
    for col, val in _column_constants(entry):
        # A constant on a near-binary column is not a choice anyone made; see
        # discriminating_constants. Skipping them is what keeps the label
        # meaningful.
        if discriminating is not None and col not in discriminating:
            continue
        for (scol, sval), owners in fp["constants"].items():
            if col == scol and abs(val - sval) < 1e-9:
                hits.append(f"{col}={val:g} from {sorted(owners)}")
    if hits:
        return {"origin": SEED_LITERAL, "seed_name": None,
                "evidence": "literal seed constants: " + "; ".join(sorted(set(hits))[:3])}

    return {"origin": INDEPENDENT, "seed_name": None,
            "evidence": "no shared shape or literal constant with any seed"}


def record(conn, strategy_id: str, result: dict, generation=None,
           parent_ids=None) -> None:
    init(conn)
    conn.execute("""INSERT OR REPLACE INTO strategy_ancestry
        (strategy_id, seed_origin, seed_name, evidence, generation, parent_ids,
         classified_at) VALUES (?,?,?,?,?,?,?)""",
        (strategy_id, result["origin"], result.get("seed_name"),
         result["evidence"], generation,
         json.dumps(parent_ids) if parent_ids else None,
         datetime.now(timezone.utc).isoformat()))


def is_independent(conn, strategy_id: str) -> bool:
    """
    True only when classified INDEPENDENT. An unclassified strategy is NOT
    independent — absence of evidence is not evidence of independence, and this
    is exactly the assumption that produced the retraction.
    """
    init(conn)
    r = conn.execute("SELECT seed_origin FROM strategy_ancestry WHERE strategy_id=?",
                     (strategy_id,)).fetchone()
    return bool(r) and r["seed_origin"] == INDEPENDENT


def summary(conn) -> dict:
    init(conn)
    return {r["seed_origin"]: r["n"] for r in conn.execute(
        "SELECT seed_origin, COUNT(*) n FROM strategy_ancestry GROUP BY seed_origin")}
