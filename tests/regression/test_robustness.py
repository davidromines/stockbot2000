"""Regression tests for robustness.py (Phase 13 H10 collapse tests).

Plain script, no pytest. Run: PYTHONPATH=. venv/bin/python tests/regression/test_robustness.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import numpy as np
import pandas as pd

import robustness

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def init():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume REAL)")
    return conn


def test_perturb_scales_const():
    node = {"op": "gt", "args": [{"col": "x"}, {"const": 50}]}
    out = robustness._perturb(node, 1.1)
    got = out["args"][1]["const"]
    check("perturb scales const by f", abs(got - 55.0) < 1e-9, f"got {got!r}")
    # The input must be untouched: _perturb deep-copies before walking.
    check("perturb does not mutate input", node["args"][1]["const"] == 50,
          f"input const now {node['args'][1]['const']!r}")


def test_perturb_leaves_markers():
    node = {"op": "and", "args": [{"const": 0.5}, {"const": 0}]}
    out = robustness._perturb(node, 1.1)
    check("perturb leaves 0.5 (boolean marker)", out["args"][0]["const"] == 0.5,
          f"got {out['args'][0]['const']!r}")
    check("perturb leaves 0", out["args"][1]["const"] == 0,
          f"got {out['args'][1]['const']!r}")


def test_perturb_reaches_nested_args():
    node = {"op": "and", "args": [
        {"op": "gt", "args": [{"col": "a"}, {"const": 10}]},
        {"op": "lt", "args": [{"col": "b"}, {"const": 20}]},
    ]}
    out = robustness._perturb(node, 1.1)
    a = out["args"][0]["args"][1]["const"]
    b = out["args"][1]["args"][1]["const"]
    check("perturb reaches nested args", abs(a - 11.0) < 1e-9 and abs(b - 22.0) < 1e-9,
          f"got {a!r}, {b!r}")


def test_regime_labels_empty():
    conn = init()
    reg = robustness.regime_labels(conn, "2020-01-01", "2020-12-31")
    check("regime_labels empty frame", reg.empty, f"len {len(reg)}")
    check("regime_labels empty columns",
          list(reg.columns) == ["date", "bull", "high_vol", "crisis"],
          f"columns {list(reg.columns)}")


def test_regime_labels_synthetic():
    conn = init()
    # 400 sessions rising steadily, then one final date at 70% of the peak.
    # 400 rows is enough for the 200-day SMA (min_periods=150) and the
    # 252-day high (min_periods=150) to be defined on the final date.
    dates = pd.bdate_range("2020-01-01", periods=400)
    closes = np.linspace(100.0, 200.0, 400)
    rows = [(d.strftime("%Y-%m-%d"), c) for d, c in zip(dates, closes)]
    rows.append(("2021-08-02", 0.7 * 200.0))
    conn.executemany("INSERT INTO prices (ticker, date, close) VALUES ('SPY', ?, ?)", rows)
    conn.commit()

    reg = robustness.regime_labels(conn, "2020-01-01", "2021-12-31")
    check("regime_labels synthetic non-empty", not reg.empty, f"len {len(reg)}")
    if reg.empty:
        return
    reg = reg.set_index("date")
    check("regime_labels crisis on final date",
          bool(reg.loc["2021-08-02", "crisis"]) is True,
          f"crisis={reg.loc['2021-08-02', 'crisis']!r}")
    # An earlier rising date: close above the 200-day SMA.
    check("regime_labels bull on rising date",
          bool(reg.loc["2021-01-04", "bull"]) is True,
          f"bull={reg.loc['2021-01-04', 'bull']!r}")


def test_analyse_insufficient_sample():
    conn = init()
    out = robustness.analyse(conn, {}, None, None, 1000.0, 1, {"pnl_series": []}, {})
    check("analyse empty pnl -> INSUFFICIENT_SAMPLE",
          out.get("verdict") == "INSUFFICIENT_SAMPLE", f"verdict {out.get('verdict')!r}")


def test_rules_keys():
    for key in ("bootstrap_min_share", "param_min_share", "universe_min_share",
                "regime_min_trades", "max_failures"):
        check(f"RULES has {key}", key in robustness.RULES, f"keys {sorted(robustness.RULES)}")


def main():
    test_perturb_scales_const()
    test_perturb_leaves_markers()
    test_perturb_reaches_nested_args()
    test_regime_labels_empty()
    test_regime_labels_synthetic()
    test_analyse_insufficient_sample()
    test_rules_keys()
    if FAILED:
        print(f"\n{len(FAILED)} FAILED")
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
