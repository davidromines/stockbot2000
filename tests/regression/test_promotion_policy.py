"""
Regression test for promotion_policy.py — Phase 10, item 31.

The property under test is not "does promotion work". It is that promotion
CANNOT happen: the module decides, records, and stops. Every test below is
written so that it would fail if a future edit gave this module a path to the
broker, or let a compelling strategy substitute for a missing safety control.

Two things are deliberately awkward to test and are tested anyway:

  * readiness() reads config/risk.yaml and config.yaml from the real working
    directory. We do not stub those out, because the whole point of the
    readiness gate is that it reports what the repository actually contains.
    Tests assert on structure and on the verified/present distinction, never
    on a specific count of satisfied prerequisites — a count would break the
    moment a config value is legitimately added, and would teach whoever
    fixes it to weaken the assertion.

  * eligibility() is exercised through the real league tables. An unknown
    strategy must still produce a recorded REFUSED decision, because the
    interesting audit question is what we nearly promoted.

Run: PYTHONPATH=. venv/bin/python tests/regression/test_promotion_policy.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import inspect
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import promotion_policy as pp  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def fresh_conn() -> sqlite3.Connection:
    """In-memory database with the tables promotion_policy touches."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # The league tables eligibility.assess() reads. Created empty on purpose:
    # an empty league is a legitimate state and must not crash the gate.
    conn.executescript("""
        CREATE TABLE league_strategies (
            strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
            name TEXT NOT NULL, family TEXT, author TEXT,
            created_at TEXT NOT NULL, parent_key TEXT, ancestry TEXT,
            hypothesis TEXT, universe TEXT, entry_rule TEXT, exit_rule TEXT,
            position_sizing TEXT, holding_period TEXT, required_data TEXT,
            parameters TEXT, definition_hash TEXT NOT NULL,
            source_kind TEXT, source_ref TEXT, supersedes INTEGER,
            PRIMARY KEY (strategy_key, version));
        CREATE TABLE league_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy_key TEXT NOT NULL,
            version INTEGER NOT NULL, at TEXT NOT NULL, from_state TEXT,
            to_state TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT);
        CREATE TABLE degradation (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
            strategy_key TEXT NOT NULL, version INTEGER, linked_strategy TEXT,
            link_method TEXT NOT NULL, backtest_return REAL,
            validation_return REAL, paper_return REAL, live_return REAL,
            paper_vs_backtest REAL, n_marks INTEGER,
            provisional INTEGER NOT NULL, note TEXT);
        CREATE TABLE freshness_log (
            checked_at TEXT PRIMARY KEY, expected_latest_date TEXT,
            actual_latest_date TEXT, lag_days INTEGER, lag_sessions INTEGER,
            missing_symbols INTEGER NOT NULL DEFAULT 0, ok INTEGER NOT NULL,
            reason TEXT NOT NULL);
        CREATE TABLE picks (
            pick_date TEXT NOT NULL, ticker TEXT NOT NULL, source TEXT NOT NULL,
            rank INTEGER, price REAL NOT NULL, stop_price REAL, hold_days INTEGER,
            rationale TEXT, status TEXT NOT NULL DEFAULT 'open', exit_date TEXT,
            exit_price REAL, exit_reason TEXT, entry_date TEXT, shares REAL,
            PRIMARY KEY (pick_date, ticker, source));
    """)
    conn.commit()
    return conn


def cfg() -> dict:
    """
    A minimal config. Deliberately NOT the real config.yaml: readiness() must
    be testable without the repository's live settings, and a test that reads
    the real config would change meaning every time a threshold is tuned.
    """
    return {
        "database": {"market_data_path": ":memory:"},
        "execution": {"mode": "SIMULATION"},
        "league": {"min_rank_marks": 20, "min_forward_trades": 30,
                   "max_correlation": 0.7},
        "risk": {"min_dollar_volume": 1_000_000},
    }


def main() -> int:
    print("\n  promotion_policy regression\n  " + "-" * 68)

    # ---- 1. PREREQUISITES is exactly the fifteen the spec names -----------
    names = [n for n, _ in pp.PREREQUISITES]
    check("PREREQUISITES has exactly 15 entries", len(pp.PREREQUISITES) == 15,
          f"got {len(pp.PREREQUISITES)}")
    check("PREREQUISITE names are unique", len(set(names)) == len(names),
          f"duplicates: {sorted({n for n in names if names.count(n) > 1})}")
    check("every PREREQUISITE has a non-empty description",
          all(isinstance(d, str) and d.strip() for _, d in pp.PREREQUISITES))
    # The spec's fifteen, by name. A rename here is a silent loss of a control.
    expected = {
        "minimum_paper_period", "minimum_trades", "risk_limits",
        "max_position_size", "max_portfolio_exposure", "correlation_limits",
        "liquidity_limits", "kill_switches", "operational_health",
        "broker_reconciliation", "degradation_rules", "emergency_demotion",
        "human_override", "audit_logging", "live_mode_disabled",
    }
    check("PREREQUISITE names match the spec's fifteen",
          set(names) == expected,
          f"missing={sorted(expected - set(names))} "
          f"extra={sorted(set(names) - expected)}")

    # ---- 2. evaluate() records a row, permitted or not --------------------
    conn = fresh_conn()
    pp.init(conn)
    r = pp.evaluate(conn, cfg(), "does_not_exist_v1")
    n = conn.execute("SELECT COUNT(*) FROM promotion_decisions").fetchone()[0]
    check("evaluate() records exactly one decision row", n == 1, f"got {n}")
    check("evaluate() returns a decision string",
          r["decision"] in ("PERMITTED", "REFUSED"), r.get("decision"))
    check("evaluate() returns permitted as a bool",
          isinstance(r["permitted"], bool))
    check("permitted agrees with decision",
          r["permitted"] == (r["decision"] == "PERMITTED"))

    # ---- 3. an unknown strategy is still recorded, and refused ------------
    row = conn.execute("SELECT * FROM promotion_decisions").fetchone()
    check("unknown strategy is recorded, not skipped", row is not None)
    check("unknown strategy is REFUSED", row["decision"] == "REFUSED",
          row["decision"])
    check("unknown strategy records a blocker",
          len(json.loads(row["blockers"])) >= 1)
    check("unknown strategy records eligible_ok = 0", row["eligible_ok"] == 0)
    check("unknown strategy records a null version", row["version"] is None,
          str(row["version"]))
    check("decision row carries an actor", row["actor"] == "system",
          str(row["actor"]))
    check("decision row carries a UTC timestamp",
          isinstance(row["at"], str) and "T" in row["at"], str(row["at"]))

    # ---- 4. history() returns decisions and is idempotent -----------------
    pp.evaluate(conn, cfg(), "second_strategy_v1")
    h1 = pp.history(conn)
    check("history() returns both decisions", len(h1) == 2, f"got {len(h1)}")
    check("history() is newest-first",
          h1[0]["id"] > h1[1]["id"], f"{h1[0]['id']} vs {h1[1]['id']}")
    check("history() returns dicts", isinstance(h1[0], dict))
    h2 = pp.history(conn)
    check("history() is idempotent (no rows added by reading)",
          len(h2) == len(h1), f"{len(h1)} then {len(h2)}")
    check("history() filters by strategy_key",
          len(pp.history(conn, "second_strategy_v1")) == 1)
    check("history() on an unknown key returns empty",
          pp.history(conn, "never_seen") == [])
    # init() must be safe to call repeatedly — every entry point calls it.
    pp.init(conn); pp.init(conn)
    check("init() is idempotent",
          conn.execute("SELECT COUNT(*) FROM promotion_decisions").fetchone()[0] == 2)

    # ---- 5. readiness and eligibility are independent ---------------------
    # A strategy that is perfectly eligible must still be refused when the
    # system is not ready. This is the property the module exists for.
    real_eligible = pp.eligible
    real_readiness = pp.readiness
    try:
        pp.eligible = lambda c, k, s: {
            "ok": True, "reasons": [], "metrics": {"sharpe": 9.9},
            "score": 9.9, "state": "PAPER"}
        pp.readiness = lambda c, k: {
            "ready": False, "unmet": ["kill_switches"], "unexercised": [],
            "checks": {}, "n_total": 15, "n_verified": 0}
        r = pp.evaluate(conn, cfg(), "flawless_v1")
        check("eligible strategy is REFUSED when the system is not ready",
              r["decision"] == "REFUSED", r["decision"])
        check("the refusal names the system gap, not the strategy",
              any("system not ready" in b for b in r["blockers"]),
              str(r["blockers"]))
        check("readiness_ok is recorded as 0",
              conn.execute("SELECT readiness_ok FROM promotion_decisions "
                           "ORDER BY id DESC LIMIT 1").fetchone()[0] == 0)

        # And the converse: a ready system does not rescue an ineligible one.
        pp.readiness = lambda c, k: {
            "ready": True, "unmet": [], "unexercised": [],
            "checks": {}, "n_total": 15, "n_verified": 15}
        pp.eligible = lambda c, k, s: {
            "ok": False, "reasons": ["too few forward trades"],
            "metrics": None, "score": None, "state": "PAPER"}
        r = pp.evaluate(conn, cfg(), "unproven_v1")
        check("ineligible strategy is REFUSED on a ready system",
              r["decision"] == "REFUSED", r["decision"])
        check("the refusal names the strategy reason",
              any("too few forward trades" in b for b in r["blockers"]),
              str(r["blockers"]))
        check("eligible_ok is recorded as 0",
              conn.execute("SELECT eligible_ok FROM promotion_decisions "
                           "ORDER BY id DESC LIMIT 1").fetchone()[0] == 0)

        # Both gates open is the only PERMITTED path.
        pp.eligible = lambda c, k, s: {
            "ok": True, "reasons": [], "metrics": {}, "score": 1.0,
            "state": "PAPER"}
        r = pp.evaluate(conn, cfg(), "both_gates_v1")
        check("PERMITTED requires both gates open",
              r["decision"] == "PERMITTED", r["decision"])
        check("PERMITTED carries no blockers", r["blockers"] == [],
              str(r["blockers"]))
    finally:
        pp.eligible = real_eligible
        pp.readiness = real_readiness

    # ---- 6. readiness() shape, on the real repository ---------------------
    conn2 = fresh_conn()
    pp.init(conn2)
    rd = pp.readiness(conn2, cfg())
    check("readiness() returns a dict", isinstance(rd, dict))
    check("readiness() reports every prerequisite",
          set(rd["checks"]) == set(names),
          f"missing={sorted(set(names) - set(rd['checks']))}")
    check("readiness() n_total equals the prerequisite count",
          rd["n_total"] == 15, str(rd["n_total"]))
    check("readiness() returns ready as a bool", isinstance(rd["ready"], bool))
    check("readiness() returns unmet as a list", isinstance(rd["unmet"], list))
    check("readiness() returns unexercised as a list",
          isinstance(rd["unexercised"], list))

    shape_ok = True
    bad = ""
    for name, c in rd["checks"].items():
        if not isinstance(c, dict):
            shape_ok, bad = False, f"{name} is {type(c).__name__}"; break
        for key in ("satisfied", "detail", "evidence"):
            if key not in c:
                shape_ok, bad = False, f"{name} missing {key}"; break
        if not shape_ok:
            break
        if not isinstance(c["satisfied"], bool):
            shape_ok, bad = False, f"{name}.satisfied is not bool"; break
        if not isinstance(c["detail"], str):
            shape_ok, bad = False, f"{name}.detail is not str"; break
        if c["evidence"] not in ("verified", "present", "untested"):
            shape_ok, bad = False, f"{name}.evidence = {c['evidence']!r}"; break
    check("every check is a dict with satisfied/detail/evidence", shape_ok, bad)

    # ready must agree with unmet, or the gate is decorative.
    check("ready is exactly 'no unmet prerequisites'",
          rd["ready"] == (len(rd["unmet"]) == 0),
          f"ready={rd['ready']} unmet={rd['unmet']}")
    check("unmet lists exactly the unsatisfied checks",
          set(rd["unmet"]) == {k for k, v in rd["checks"].items()
                               if not v["satisfied"]},
          str(rd["unmet"]))
    check("unexercised lists only satisfied-but-unverified checks",
          set(rd["unexercised"]) == {k for k, v in rd["checks"].items()
                                     if v["satisfied"]
                                     and v["evidence"] != "verified"},
          str(rd["unexercised"]))

    # ---- 7. n_verified cannot exceed n_total ------------------------------
    check("n_verified <= n_total", rd["n_verified"] <= rd["n_total"],
          f"{rd['n_verified']} > {rd['n_total']}")
    check("n_verified counts only verified checks",
          rd["n_verified"] == sum(1 for v in rd["checks"].values()
                                  if v["evidence"] == "verified"),
          str(rd["n_verified"]))
    # The bug this guards: 15 of 15 satisfied on a system that has never
    # traded, because files existed. Verified must be the stricter number.
    check("n_verified is not inflated to n_total by mere presence",
          rd["n_verified"] <= rd["n_total"] - len(rd["unexercised"]),
          f"verified={rd['n_verified']} unexercised={len(rd['unexercised'])}")

    # ---- 8. live_mode_disabled is the one inverted prerequisite -----------
    live_cfg = cfg()
    live_cfg["execution"] = {"mode": "LIVE"}
    rd_live = pp.readiness(fresh_conn(), live_cfg)
    check("readiness() reports a GAP when execution.mode is LIVE",
          not rd_live["checks"]["live_mode_disabled"]["satisfied"],
          rd_live["checks"]["live_mode_disabled"]["detail"])
    check("LIVE mode makes the system not ready", not rd_live["ready"])
    check("LIVE mode appears in unmet", "live_mode_disabled" in rd_live["unmet"])

    # ---- 9. render_readiness() is a pure renderer -------------------------
    text = pp.render_readiness(rd)
    check("render_readiness() returns a string", isinstance(text, str))
    check("render_readiness() names every prerequisite",
          all(n in text for n in names))
    check("render_readiness() does not mutate its input",
          rd["n_total"] == 15 and isinstance(rd["checks"], dict))

    # ---- 10. the module cannot reach the broker ---------------------------
    src = (ROOT / "promotion_policy.py").read_text()
    tree = __import__("ast").parse(src)
    imported = set()
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, __import__("ast").ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"broker", "execution", "orders", "robin_stocks", "alpaca",
                 "ib_insync", "requests", "urllib", "http", "socket"}
    check("promotion_policy imports no broker or transmit module",
          not (imported & forbidden),
          f"imports {sorted(imported & forbidden)}")
    check("promotion_policy imports runtime first",
          src.lstrip().startswith('"""') and
          re.search(r'^import runtime', src, re.M) is not None)
    # runtime must precede numpy/pandas/xgboost wherever they appear.
    for lib in ("numpy", "pandas", "xgboost"):
        m_lib = re.search(rf"^\s*import {lib}\b", src, re.M)
        m_rt = re.search(r"^\s*import runtime\b", src, re.M)
        if m_lib:
            check(f"runtime precedes {lib}",
                  m_rt is not None and m_rt.start() < m_lib.start())

    # No call that could transmit. Checked on the AST so a mention in a
    # docstring or a comment cannot produce a false pass or a false failure.
    calls = set()
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").Call):
            f = node.func
            if isinstance(f, __import__("ast").Attribute):
                calls.add(f.attr)
            elif isinstance(f, __import__("ast").Name):
                calls.add(f.id)
    transmit = {"submit_order", "place_order", "transmit", "buy", "sell",
                "cancel_order", "replace_order", "post", "request", "urlopen"}
    check("promotion_policy calls nothing that transmits",
          not (calls & transmit), f"calls {sorted(calls & transmit)}")

    # ---- 11. no SQL against broker or order tables ------------------------
    sql_strings = []
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").Constant) and \
                isinstance(node.value, str):
            sql_strings.append(node.value)
    sql_text = " ".join(sql_strings).lower()
    for table in ("orders", "fills", "broker_order_id", "client_order_id"):
        check(f"promotion_policy issues no SQL against {table}",
              not re.search(rf"\b(from|into|update|join)\s+{table}\b", sql_text),
              f"found {table} in a SQL string")
    # It must write to its own table, or the audit trail is a claim.
    check("promotion_policy writes to promotion_decisions",
          "promotion_decisions" in sql_text)

    # ---- 12. the decision is a recommendation, not an instruction ---------
    check("evaluate() returns no order-shaped field",
          not ({"order", "orders", "client_order_id", "quantity", "notional"}
               & set(r.keys())),
          str(sorted(r.keys())))
    check("evaluate() returns no broker handle",
          not any(isinstance(v, object) and type(v).__module__ in
                  ("robin_stocks", "alpaca", "ib_insync")
                  for v in r.values()))
    # The docstring is the contract a reader trusts. If it stops saying this,
    # the code and the documentation have diverged.
    doc = inspect.getdoc(pp) or ""
    check("module docstring states it does not promote",
          "does not promote" in doc.lower() or "will not do" in doc.lower())
    check("module docstring states a human places orders",
          "human" in doc.lower())

    conn.close(); conn2.close()

    print("  " + "-" * 68)
    print(f"  {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
