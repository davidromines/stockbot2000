"""Regression tests for signal_activity."""
import runtime  # noqa: F401

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

import signal_activity as sa

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def _frame():
    """3 tickers x 100 business days; 'flag' is 1 only on chosen rows."""
    dates = pd.bdate_range("2024-01-01", periods=100).strftime("%Y-%m-%d").tolist()
    rows = []
    for ticker in ("AAA", "BBB", "CCC"):
        for d in dates:
            rows.append({"ticker": ticker, "date": d, "close": 10.0, "flag": 0.0})
    df = pd.DataFrame(rows)
    return df, dates


def _set(df, ticker, date, value=1.0):
    df.loc[(df["ticker"] == ticker) & (df["date"] == date), "flag"] = value


FLAG_ENTRY = {"entry": {"op": "gt", "args": [{"col": "flag"}, {"const": 0.5}]}}


def main():
    df, dates = _frame()
    recent = dates[-60:]

    # 5 distinct recent dates, one ticker each.
    for d in recent[:5]:
        _set(df, "AAA", d)
    check("five distinct recent dates -> 5", sa.active_sessions(df, FLAG_ENTRY) == 5,
          sa.active_sessions(df, FLAG_ENTRY))

    # Two tickers firing on the same date count once.
    df2, dates2 = _frame()
    _set(df2, "AAA", dates2[-1])
    _set(df2, "BBB", dates2[-1])
    check("two tickers same date counts once", sa.active_sessions(df2, FLAG_ENTRY) == 1,
          sa.active_sessions(df2, FLAG_ENTRY))

    # Firings older than the window are excluded.
    df3, dates3 = _frame()
    for d in dates3[:10]:
        _set(df3, "AAA", d)
    check("old firings excluded", sa.active_sessions(df3, FLAG_ENTRY) == 0,
          sa.active_sessions(df3, FLAG_ENTRY))

    # Never fires.
    df4, _ = _frame()
    check("never fires -> 0", sa.active_sessions(df4, FLAG_ENTRY) == 0)
    check("never fires -> last_signal None", sa.last_signal(df4, FLAG_ENTRY) is None)

    # last_signal is the latest firing date.
    df5, dates5 = _frame()
    _set(df5, "AAA", dates5[-3])
    _set(df5, "BBB", dates5[-1])
    check("last_signal latest date", sa.last_signal(df5, FLAG_ENTRY) == dates5[-1],
          sa.last_signal(df5, FLAG_ENTRY))

    # measurable().
    check("measurable plain genome", sa.measurable(FLAG_ENTRY) is True)
    for k in ("pair", "value", "rotation", "crypto"):
        check(f"measurable False for {k}", sa.measurable({"entry": {}, k: {}}) is False)
    check("measurable False for None", sa.measurable(None) is False)

    # activity() with a rotation genome: not measurable, no counts.
    import slots
    orig = slots.genome_for
    slots.genome_for = lambda conn, key, version: {"rotation": {"x": 1}}
    try:
        out = sa.activity(None, None, "rot", 1, df=df)
    finally:
        slots.genome_for = orig
    check("activity rotation measurable False", out["measurable"] is False)
    check("activity rotation active_sessions None", out["active_sessions"] is None)

    # A rule referencing a missing column: measurable, 0, with error text.
    bad = {"entry": {"op": "gt", "args": [{"col": "nope"}, {"const": 0.5}]}}
    slots.genome_for = lambda conn, key, version: bad
    try:
        out2 = sa.activity(None, None, "bad", 1, df=df)
    finally:
        slots.genome_for = orig
    check("missing column -> active_sessions 0", out2["active_sessions"] == 0)
    check("missing column -> error key", "error" in out2 and bool(out2["error"]))

    if FAILED:
        print(f"\n{len(FAILED)} FAILED")
        sys.exit(1)
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
