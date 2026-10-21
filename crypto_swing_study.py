"""
Crypto swing study (owner 2026-10-21: "I want crypto built"). Registered experiment `crypto_swing_v1`. Read-only.

Robinhood's crypto buy price sits ~1.9% above its sell price at the same moment (crypto_spreads, measured hourly
since 2026-09-25), and a coin's median one-hour move is 0.2-0.5% (Coinbase hourly bars). So a minute-scale rule starts
every trade ~1.9% behind with nothing to recover it from; this asks the question that decides whether a crypto runner
is worth building: does any simple rule held for HOURS TO DAYS make money after buying at the ask and selling at the bid?

Data: Coinbase hourly bars (`crypto_prices`, interval 1h), 10 coins, 2024-09-03 to the registration date. Fills: the
signal is the close of hour i; the buy is at the open of hour i+1 times (1 + half the coin's measured spread), the sale
at the open H hours later times (1 - half the spread). One position per coin at a time. No stop (a time exit only, so
the grid stays small and nothing is tuned).

The grid (pre-declared, 18 cells): rule x threshold x hold
    breakout     close above the highest close of the previous N hours      N in {24, 72}
    momentum     24-hour return above x                                     x in {+5%, +10%}
    dip          24-hour return below -x                                    x in {-5%, -10%}
    hold H       12, 24, 48 hours

PASS for a cell (written before any result): mean net return per trade > 0, date-clustered t >= 3.0 (about a Bonferroni
5% across the 18 cells), and a positive mean in BOTH halves of the window. A passing cell is a candidate for a SHADOW
runner, never a live rule by itself.

    ./venv/bin/python crypto_swing_study.py --register
    ./venv/bin/python crypto_swing_study.py --run [--write]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

ROOT = Path(__file__).resolve().parent
EXPERIMENT = "crypto_swing_v1"
START = "2024-09-03"
END = "2026-10-21"
HOLDS = (12, 24, 48)
RULES = (("breakout", 24), ("breakout", 72), ("momentum", 0.05), ("momentum", 0.10), ("dip", 0.05), ("dip", 0.10))
T_NEED = 3.0
DEFAULT_HALF_SPREAD = 0.0096


def half_spreads(conn) -> dict:
    try:
        s = pd.read_sql("SELECT symbol, AVG(spread_pct) s FROM crypto_spreads GROUP BY symbol", conn)
        return {r.symbol: float(r.s) / 2 for r in s.itertuples()}
    except Exception:                                          # noqa: BLE001
        return {}


def bars(conn, start=START, end=END) -> pd.DataFrame:
    lo = int(pd.Timestamp(start, tz="UTC").timestamp())
    hi = int((pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).timestamp())
    return pd.read_sql("SELECT symbol, open_time, open, close FROM crypto_prices WHERE interval='1h' AND open_time >= ? "
                       "AND open_time < ? ORDER BY symbol, open_time", conn, params=(lo, hi))


def signals(close: np.ndarray, rule: str, p) -> np.ndarray:
    """Boolean per hour: the rule fires on this hour's close (uses only this and earlier closes)."""
    n = len(close)
    out = np.zeros(n, dtype=bool)
    if rule == "breakout":
        prior_max = pd.Series(close).shift(1).rolling(int(p), min_periods=int(p)).max().to_numpy()
        out = close > prior_max
    else:
        r24 = np.full(n, np.nan)
        r24[24:] = close[24:] / close[:-24] - 1
        out = (r24 > p) if rule == "momentum" else (r24 < -p)
    return np.nan_to_num(out, nan=0).astype(bool)


def trades(df: pd.DataFrame, rule: str, p, hold: int, half: dict) -> pd.DataFrame:
    rows = []
    for sym, g in df.groupby("symbol"):
        o, c, t = g["open"].to_numpy(float), g["close"].to_numpy(float), g["open_time"].to_numpy()
        sig = signals(c, rule, p)
        hs = half.get(sym, DEFAULT_HALF_SPREAD)
        i, n = 0, len(c)
        while i < n:
            if sig[i] and i + 1 + hold < n:
                buy = o[i + 1] * (1 + hs)
                sell = o[i + 1 + hold] * (1 - hs)
                rows.append({"symbol": sym, "entry_time": int(t[i + 1]), "ret": sell / buy - 1})
                i += 1 + hold                                   # one position per coin at a time
            else:
                i += 1
    return pd.DataFrame(rows)


def cell_stats(tr: pd.DataFrame, mid_time: int) -> dict:
    import forward_stats as fs
    if len(tr) < 10:
        return {"n": int(len(tr)), "mean": None, "t": None, "first": None, "second": None, "pass": False}
    day = pd.to_datetime(tr["entry_time"], unit="s").dt.strftime("%Y-%m-%d").to_numpy()
    cs = fs.cluster_stats(tr["ret"].to_numpy(), day)
    a, b = tr[tr["entry_time"] < mid_time]["ret"], tr[tr["entry_time"] >= mid_time]["ret"]
    out = {"n": int(len(tr)), "mean": float(tr["ret"].mean()), "t": cs["t"], "days": cs["clusters"],
           "win": float((tr["ret"] > 0).mean()), "first": float(a.mean()) if len(a) else None,
           "second": float(b.mean()) if len(b) else None}
    out["pass"] = bool(out["mean"] > 0 and (out["t"] or 0) >= T_NEED and (out["first"] or 0) > 0 and (out["second"] or 0) > 0)
    return out


def run(conn) -> list:
    df = bars(conn)
    half = half_spreads(conn)
    lo = int(pd.Timestamp(START, tz="UTC").timestamp())
    hi = int((pd.Timestamp(END, tz="UTC")).timestamp())
    mid = (lo + hi) // 2
    out = []
    for rule, p in RULES:
        for hold in HOLDS:
            tr = trades(df, rule, p, hold, half)
            out.append({"rule": rule, "param": p, "hold": hold, **cell_stats(tr, mid)})
    return out


def spec() -> dict:
    return {"primary_metric": "mean net return per trade, buying at the ask and selling at the bid (measured spread)",
            "universe": "the 10 coins with Coinbase hourly bars in crypto_prices",
            "entry_rule": [f"{r}:{p}" for r, p in RULES], "exit_rule": {"time_exit_hours": list(HOLDS), "stop": None},
            "holding_period": f"{HOLDS} hours", "cost_assumptions": "half the coin's mean measured Robinhood spread each way",
            "evaluation_period": [START, END], "data_version": "crypto_prices 1h (Coinbase) at registration",
            "stopping_rule": "one evaluation of the 18 cells", "sample_size": "every signal, one position per coin",
            "holdout_policy": "none: a feasibility study; a passing cell goes to SHADOW, not live",
            "pass_rule": f"mean > 0, date-clustered t >= {T_NEED}, positive in both halves"}


def register(conn) -> None:
    import experiment_registry as er
    try:
        er.get(conn, EXPERIMENT)
        return
    except er.RegistryError:
        pass
    er.create(conn, EXPERIMENT, "A simple crypto rule held 12-48 hours (breakout, momentum or dip) makes money after "
              "buying at Robinhood's ask and selling at its bid, by more than noise across 18 cells and in both halves of "
              "2024-09..2026-10. Fails if no cell passes.", "Claude (owner 'I want crypto built', 2026-10-21)", spec())
    er.register(conn, EXPERIMENT)


def render(res: list) -> str:
    L = [f"# Crypto swing study — {date.today().isoformat()} (`{EXPERIMENT}`)", "",
         f"10 coins, Coinbase hourly bars {START} to {END}; buy at the next hour's open at Robinhood's ask, sell H hours "
         "later at its bid. Net return per trade; date-clustered t.", "",
         "| rule | hold (h) | trades | mean net | t | win | first half | second half | pass |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    f = lambda x, s="{:+.2%}": "—" if x is None else s.format(x)       # noqa: E731
    for r in res:
        p = f"{r['param']:.0%}" if r["rule"] != "breakout" else f"{int(r['param'])}h high"
        L.append(f"| {r['rule']} {p} | {r['hold']} | {r['n']} | {f(r['mean'])} | {f(r['t'], '{:+.1f}')} | "
                 f"{f(r.get('win'), '{:.0%}')} | {f(r['first'])} | {f(r['second'])} | {'PASS' if r['pass'] else 'no'} |")
    passed = [r for r in res if r["pass"]]
    L += ["", f"**{len(passed)} of {len(res)} cells pass.** "
          + ("A passing cell is a candidate for a SHADOW crypto runner." if passed else
             "No simple rule held 12-48 hours makes money at Robinhood's buy and sell prices on this window.")]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for x in ("register", "run", "write"):
        ap.add_argument(f"--{x}", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    if a.register:
        register(conn)
        print(f"{EXPERIMENT} registered")
    if a.run:
        import experiment_registry as er
        e = er.get(conn, EXPERIMENT)
        conn.row_factory = None
        res = run(conn)
        text = render(res)
        print(text)
        if a.write:
            (ROOT / "reports" / f"crypto_swing_{date.today().isoformat()}.md").write_text(text)
        conn.row_factory = sqlite3.Row
        if e["status"] == er.REGISTERED:
            er.start(conn, EXPERIMENT)
            passed = [f"{r['rule']}:{r['param']}:{r['hold']}h" for r in res if r["pass"]]
            er.complete(conn, EXPERIMENT, {"passed": passed, "cells": res},
                        "PASS: " + ", ".join(passed) if passed else "FAIL: no cell passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
