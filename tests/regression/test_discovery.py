"""
Regression tests for discovery.py (Phase 13 H9): priority, budgets, failure
records, recycling.

Plain script, no pytest. Run: PYTHONPATH=. venv/bin/python tests/regression/test_discovery.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import discovery
import league
import research_queue as rq
import strategy_factory as sf
import strategy_objects as so

CFG = {"factory": {"family_explored_after": 8, "max_backtests_per_run": 12,
                   "max_recycles_per_strategy": 2}}

_failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        _failures.append(name)


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def _obj(key, family, params=None, source="factory_template"):
    """A minimal but complete strategy object for register()."""
    g = sf.G(sf.gt(sf.col("roc_10"), sf.k(0.5)))
    return {"strategy_key": key, "name": key, "family": family, "league": "momentum",
            "genome": g, "parameters": params or {"q": 0.8},
            "hypothesis": "test", "economic_rationale": "test",
            "data_requirements": ["features"], "universe": "tradeable common stock",
            "source": source, "source_ref": family, "features": ["roc_10"],
            "intraday": False}


def _register(conn, key, family, params=None, source="factory_template"):
    r = so.register(conn, _obj(key, family, params, source))
    return r["strategy_key"], r["version"]


def _reject(conn, key, version, stage, reason="bad"):
    """Move a strategy to REJECTED and log a failure at `stage`."""
    so.decide(conn, key, version, "REJECT", reason, to_state=league.REJECTED)
    discovery.record_failure(conn, key, version, stage, reason)


# --- 1. priority: untested beats explored-without-evidence ------------------
def test_priority_untested_beats_explored():
    c = conn()
    fam = "xs_momentum"
    assert sf.F[fam]["rationale"] and sf.F[fam]["data_available"]
    fresh = discovery.priority(fam, {fam: {"tested": 0, "good": 0}}, CFG, "template")
    stale = discovery.priority(fam, {fam: {"tested": 8, "good": 0}}, CFG, "template")
    check("priority untested > explored-without-evidence",
          isinstance(fresh, float) and fresh > stale, f"{fresh} vs {stale}")
    c.close()


# --- 2. priority: recycle is penalised vs template --------------------------
def test_priority_recycle_lower():
    c = conn()
    fam = "xs_momentum"
    rec = {fam: {"tested": 0, "good": 0}}
    t = discovery.priority(fam, rec, CFG, "template")
    r = discovery.priority(fam, rec, CFG, "recycle")
    check("priority recycle < template", r < t, f"{r} vs {t}")
    c.close()


# --- 3. priority: unknown family is blocked ---------------------------------
def test_priority_unknown_family():
    c = conn()
    p = discovery.priority("no_such_family_xyz", {}, CFG, "template")
    check("priority unknown family is None", p is None, repr(p))
    c.close()


# --- 3b. priority: data-unavailable family is blocked -----------------------
def test_priority_data_unavailable():
    c = conn()
    blocked = [f for f in sf.F if not sf.F[f]["data_available"]]
    if not blocked:
        check("priority data-unavailable family is None", True,
              "no data-unavailable family exists — skipped")
    else:
        fam = blocked[0]
        p = discovery.priority(fam, {fam: {"tested": 0, "good": 0}}, CFG, "template")
        check("priority data-unavailable family is None", p is None, repr(p))
    c.close()


# --- 4. take: per-family budget ---------------------------------------------
def test_take_per_family_budget():
    c = conn()
    fam = "xs_momentum"
    for i in range(5):
        key, ver = _register(c, f"fx_{fam}_t{i}", fam, {"q": 0.8, "i": i})
        rq.enqueue(c, "template", fam, family=fam, strategy_key=key, version=ver)
    chosen = discovery.take(c, CFG, n=3)
    check("take respects per-family budget",
          len(chosen) <= discovery.PER_FAMILY_PER_RUN,
          f"got {len(chosen)}")
    c.close()


# --- 5. take: skips non-DISCOVERED and marks the item done ------------------
def test_take_skips_non_discovered():
    c = conn()
    fam = "xs_momentum"
    key, ver = _register(c, f"fx_{fam}_moved", fam, {"q": 0.8})
    rq.enqueue(c, "template", fam, family=fam, strategy_key=key, version=ver)
    so.decide(c, key, ver, "CONTINUE", "moved on", to_state=league.SPECIFIED)
    chosen = discovery.take(c, CFG, n=3)
    row = c.execute("SELECT status FROM research_queue WHERE strategy_key=?",
                    (key,)).fetchone()
    check("take skips non-DISCOVERED and marks done",
          len(chosen) == 0 and row["status"] == "done",
          f"chosen={len(chosen)} status={row['status']}")
    c.close()


# --- 6. record_failure writes the row ---------------------------------------
def test_record_failure():
    c = conn()
    fam = "xs_momentum"
    key, ver = _register(c, f"fx_{fam}_fail", fam, {"q": 0.8})
    discovery.record_failure(c, key, ver, "backtest", "no edge", window={"start": "2020-01-01"})
    row = c.execute("SELECT stage, reason FROM failure_log WHERE strategy_key=? AND version=?",
                    (key, ver)).fetchone()
    check("record_failure writes stage and reason",
          row is not None and row["stage"] == "backtest" and row["reason"] == "no edge",
          repr(dict(row)) if row else "no row")
    c.close()


# --- 7. recycle: rejected fx_ strategy mints v2 with source recycle ---------
def test_recycle_creates_version():
    c = conn()
    fam = "xs_momentum"
    key, ver = _register(c, f"fx_{fam}_recyc", fam, {"q": 0.8})
    _reject(c, key, ver, "backtest")
    made = discovery.recycle(c, CFG)
    m = so.meta(c, key, 2)
    check("recycle mints v2 with source recycle",
          len(made) == 1 and m is not None and m.get("source") == "recycle",
          f"made={made} meta={m.get('source') if m else None}")
    c.close()


# --- 8. recycle: data-stage failure is not recycled -------------------------
def test_recycle_skips_data_failure():
    c = conn()
    fam = "xs_momentum"
    key, ver = _register(c, f"fx_{fam}_datafail", fam, {"q": 0.8})
    _reject(c, key, ver, "data", "missing fundamentals")
    made = discovery.recycle(c, CFG)
    check("recycle skips data-stage failure",
          len(made) == 0 and len(league.versions(c, key)) == 1,
          f"made={made} versions={len(league.versions(c, key))}")
    c.close()


# --- 9. family_record counts the rejected strategy --------------------------
def test_family_record_counts_rejected():
    c = conn()
    fam = "xs_momentum"
    key, ver = _register(c, f"fx_{fam}_counted", fam, {"q": 0.8})
    _reject(c, key, ver, "backtest")
    rec = discovery.family_record(c)
    check("family_record counts rejected",
          rec.get(fam, {}).get("rejected", 0) >= 1,
          f"rejected={rec.get(fam, {}).get('rejected')}")
    c.close()


def _make_slot_trades(c):
    c.execute("CREATE TABLE IF NOT EXISTS slot_trades "
              "(id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INTEGER, strategy_key TEXT, "
              "version INTEGER, symbol TEXT, action TEXT, quantity REAL, price REAL, atr REAL, "
              "stop_plan TEXT, reason TEXT, signal_id TEXT)")


def _make_orders(c):
    c.execute("CREATE TABLE IF NOT EXISTS orders "
              "(client_order_id TEXT, signal_id TEXT, mode TEXT, side TEXT, "
              "avg_fill_price REAL, quote_price REAL)")


# --- 10. N6 stop-exit rate: family flagged when >60% stops and >= min trips ---
def test_weak_spots_stop_exit_rate():
    c = conn()
    discovery.init(c)
    _make_slot_trades(c)
    key, _ = _register(c, "fx_xs_momentum_stoptest", "xs_momentum")
    for i, reason in enumerate(["stop_loss", "stop_loss", "stop_loss", "strategy_exit"]):
        c.execute("INSERT INTO slot_trades (mode, action, strategy_key, reason, signal_id) "
                  "VALUES ('LIVE', 'CLOSE', ?, ?, ?)", (key, reason, f"sig{i}"))
    c.commit()
    w = discovery.weak_spots(c)
    check("N6 stop-exit rate flags family",
          "xs_momentum" in w and "stop-exit" in w.get("xs_momentum", ""),
          f"weak={w}")
    c.close()


# --- 11. N6 stop-exit rate: below threshold does not flag ---------------------
def test_weak_spots_stop_exit_below_threshold():
    c = conn()
    discovery.init(c)
    _make_slot_trades(c)
    key, _ = _register(c, "fx_xs_momentum_lowstop", "xs_momentum")
    for i, reason in enumerate(["stop_loss", "strategy_exit", "strategy_exit", "strategy_exit"]):
        c.execute("INSERT INTO slot_trades (mode, action, strategy_key, reason, signal_id) "
                  "VALUES ('LIVE', 'CLOSE', ?, ?, ?)", (key, reason, f"sig{i}"))
    c.commit()
    w = discovery.weak_spots(c)
    check("N6 stop-exit below threshold does not flag",
          "xs_momentum" not in w,
          f"weak={w}")
    c.close()


# --- 12. N6 slippage: family flagged when slippage > threshold ----------------
def test_weak_spots_slippage():
    c = conn()
    discovery.init(c)
    _make_slot_trades(c)
    _make_orders(c)
    key, _ = _register(c, "fx_xs_momentum_sliptest", "xs_momentum")
    # 4 fills, each with ~50 bps slippage (above 30 bps threshold)
    for i in range(4):
        sig = f"slipsig{i}"
        c.execute("INSERT INTO slot_trades (mode, action, strategy_key, signal_id) "
                  "VALUES ('LIVE', 'OPEN', ?, ?)", (key, sig))
        c.execute("INSERT INTO orders (signal_id, mode, side, avg_fill_price, quote_price) "
                  "VALUES (?, 'LIVE', 'buy', ?, ?)", (sig, 100.35, 100.0))
    c.commit()
    w = discovery.weak_spots(c)
    check("N6 slippage flags family",
          "xs_momentum" in w and "slippage" in w.get("xs_momentum", ""),
          f"weak={w}")
    c.close()


def main():
    test_priority_untested_beats_explored()
    test_priority_recycle_lower()
    test_priority_unknown_family()
    test_priority_data_unavailable()
    test_take_per_family_budget()
    test_take_skips_non_discovered()
    test_record_failure()
    test_recycle_creates_version()
    test_recycle_skips_data_failure()
    test_family_record_counts_rejected()
    test_weak_spots_stop_exit_rate()
    test_weak_spots_stop_exit_below_threshold()
    test_weak_spots_slippage()
    if _failures:
        print(f"\n  {len(_failures)} FAILED: {', '.join(_failures)}")
        return 1
    print("\n  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
