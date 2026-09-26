"""Regression: Stage L3 published-signal families register and link correctly."""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import strategy_factory  # noqa: E402
import factory_families_l as L  # noqa: E402
import strategy_library  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name + ("  " + detail if detail else ""))
        FAILED.append(name)


def _find_lag(node):
    """Return the lag op dict anywhere in the entry tree, or None."""
    if isinstance(node, dict):
        if node.get("op") == "lag":
            return node
        for v in node.values():
            found = _find_lag(v)
            if found is not None:
                return found
    elif isinstance(node, (list, tuple)):
        for v in node:
            found = _find_lag(v)
            if found is not None:
                return found
    return None


def _find_pct(node):
    if isinstance(node, dict):
        if node.get("op") == "pct_change":
            return node
        for v in node.values():
            found = _find_pct(v)
            if found is not None:
                return found
    elif isinstance(node, (list, tuple)):
        for v in node:
            found = _find_pct(v)
            if found is not None:
                return found
    return None


def main():
    for name in L.NEW_FAMILIES:
        check("registered: " + name, name in strategy_factory.F)

    for name, window in (("momentum_12_1", 231), ("momentum_9_1", 168)):
        spec = strategy_factory.F[name]
        genome = spec["build"](strategy_factory.grid_points(spec, 1)[0])   # a family builds genomes
        entry = genome["entry"]
        lag_op = _find_lag(entry)
        pct_op = _find_pct(entry)
        check(name + " lag n=21", lag_op is not None and lag_op.get("n") == 21,
              repr(lag_op))
        check(name + " pct n=%d" % window,
              pct_op is not None and pct_op.get("n") == window, repr(pct_op))
        hold = genome["risk"]["max_hold_days"]
        check(name + " hold 21", hold == 21, repr(hold))

    for name in ("fcf_to_price", "earnings_surprise"):
        spec = strategy_factory.F[name]
        avail = spec.get("data_available") if isinstance(spec, dict) else getattr(spec, "data_available", None)
        missing = spec.get("missing") if isinstance(spec, dict) else getattr(spec, "missing", None)
        check(name + " unavailable", avail is False, repr(avail))
        check(name + " missing reason", bool(missing), repr(missing))

    for name in ("momentum_12_1", "momentum_9_1"):
        spec = strategy_factory.F[name]
        avail = spec.get("data_available") if isinstance(spec, dict) else getattr(spec, "data_available", None)
        check(name + " available", avail is True, repr(avail))

    check("PUBLISHED covers NEW_FAMILIES",
          all(n in L.PUBLISHED for n in L.NEW_FAMILIES))

    conn = sqlite3.connect(":memory:")
    strategy_library.init(conn)
    conn.execute(
        "INSERT INTO strategy_library (entry_id, name, family, original_hypothesis, known_biases, limitations, "
        "validation_status, created_at, implementation) VALUES (?,?,?,?,?,?,?,?,?)",
        ("published:jkp:ret_12_1", "Momentum", "momentum", "h", "b", "l", "HYPOTHESIS", "2026-09-26", None))
    conn.commit()
    n = L.link_library(conn)
    check("link_library updated >=1", n >= 1, repr(n))
    row = conn.execute(
        "SELECT implementation FROM strategy_library WHERE entry_id=?",
        ("published:jkp:ret_12_1",)).fetchone()
    check("implementation stamped",
          row is not None and row[0] == "factory family momentum_12_1", repr(row))
    check("missing entry skipped",
          conn.execute("SELECT COUNT(*) FROM strategy_library WHERE entry_id=?",
                       ("published:jkp:ret_9_1",)).fetchone()[0] == 0)

    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "factory_families_l.py")).read()
    check("no evolve import", "import evolve" not in src)
    check("no seeds import", "import seeds" not in src)

    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        sys.exit(1)
    print("ALL PASS")


main()
