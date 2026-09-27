"""
Bear-market protection for the five slots (owner, 2026-09-27: "1. Go").

The slots hold long positions only, so in a falling market all five lose together.
This adds one portfolio-level rule, the same kind as the kill switch:

    RISK_OFF  SPY closed below its 200-day average (the project's PREDEFINED bear
              regime, regimes.py / robustness.regime_labels — fixed before any
              result, never tuned here)
    effect    no NEW long entries into a slot while RISK_OFF. Held positions keep
              their own stops and exits; an empty slot waits in cash.

Modes (config `regime_filter.mode`):
    OFF      nothing happens
    SHADOW   every run records what the rule WOULD have blocked; nothing is blocked
    ON       entries are blocked while RISK_OFF

It starts in SHADOW, as every change to how real money is placed does here.

The evidence is measured, not assumed (`--evidence`): across every tradeable common
stock, 2006 -> today, the 20-session return of an entry at the next open, split by
the regime on the signal day. The filter is worth having only if RISK_OFF entries
did worse — a lower mean or a fatter left tail — than RISK_ON entries. The rule is
stated before the numbers: helpful = RISK_OFF mean below RISK_ON mean AND RISK_OFF
5th percentile below RISK_ON 5th percentile.

    ./venv/bin/python regime_filter.py --state
    ./venv/bin/python regime_filter.py --evidence
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import logging
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("regime_filter")
DEFAULTS = {"mode": "SHADOW"}
MODES = ("OFF", "SHADOW", "ON")
EVIDENCE = Path("data/regime_filter_evidence.json")
HORIZON = 20


def settings(cfg: dict | None) -> dict:
    s = {**DEFAULTS, **((cfg or {}).get("regime_filter") or {})}
    if s["mode"] not in MODES:
        s["mode"] = "SHADOW"                                 # an unknown mode fails safe, never to ON
    return s


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS regime_filter_log (
        at TEXT NOT NULL, session TEXT, state TEXT NOT NULL, mode TEXT NOT NULL,
        spy_close REAL, spy_sma200 REAL, blocked INTEGER NOT NULL, would_block INTEGER NOT NULL,
        slots TEXT, PRIMARY KEY (at))""")
    conn.commit()


def state(conn, as_of: str | None = None) -> dict:
    """The regime on the newest SPY session on or before `as_of`: RISK_ON / RISK_OFF / UNKNOWN."""
    import robustness
    end = as_of or conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
    start = (dt.date.fromisoformat(end[:10]) - dt.timedelta(days=450)).isoformat()
    lab = robustness.regime_labels(conn, start, end)
    lab = lab[lab["date"] <= end]
    px = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' AND date >= ? AND date <= ? "
                           "ORDER BY date", conn, params=(start, end))
    if lab.empty or px.empty or lab.iloc[-1].get("bull") is None:
        return {"state": "UNKNOWN", "session": end, "spy_close": None, "spy_sma200": None}
    sma = px["close"].rolling(200).mean().iloc[-1]
    if pd.isna(sma):
        # "close > NaN" is False: without 200 sessions the label reads bear. Unknown, not bear.
        return {"state": "UNKNOWN", "session": end, "spy_close": float(px["close"].iloc[-1]), "spy_sma200": None}
    bull = lab.iloc[-1]["bull"]
    return {"state": "RISK_ON" if bool(bull) else "RISK_OFF", "session": str(lab.iloc[-1]["date"]),
            "spy_close": float(px["close"].iloc[-1]), "spy_sma200": None if pd.isna(sma) else float(sma)}


def check(conn, cfg: dict, slots_waiting: list | None = None, record: bool = True) -> dict:
    """What the slot trader may do this run. {block: bool, state, mode, reason}. UNKNOWN never
    blocks (a missing SPY bar is a data problem the freshness gate owns, not a bear market)."""
    s = settings(cfg)
    st = state(conn)
    risk_off = st["state"] == "RISK_OFF"
    block = s["mode"] == "ON" and risk_off
    would = s["mode"] == "SHADOW" and risk_off
    reason = (f"market regime RISK_OFF (SPY {st['spy_close']:.2f} below its 200-day average "
              f"{st['spy_sma200']:.2f}): no new long entries" if risk_off and st["spy_sma200"] else None)
    if record and s["mode"] != "OFF":
        init(conn)
        conn.execute("INSERT OR REPLACE INTO regime_filter_log VALUES (?,?,?,?,?,?,?,?,?)",
                     (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), st["session"], st["state"],
                      s["mode"], st["spy_close"], st["spy_sma200"], int(block), int(would),
                      json.dumps(slots_waiting or [])))
        conn.commit()
    return {"block": block, "would_block": would, "state": st["state"], "mode": s["mode"], "reason": reason, **st}


# --- evidence ---------------------------------------------------------------------------

def evidence(conn, cfg: dict, start_year: int = 2006) -> dict:
    """Universe-wide 20-session returns of next-open entries, split by the signal day's regime.
    Year by year to bound memory; the pooled figures are built from per-year sums."""
    import robustness
    import storage
    last = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
    lab = robustness.regime_labels(conn, f"{start_year - 1}-01-01", last)
    bull = dict(zip(lab["date"].astype(str), lab["bull"]))
    acc = {"RISK_ON": [], "RISK_OFF": []}
    by_year = {}
    for y in range(start_year, int(last[:4]) + 1):
        lo, hi = f"{y}-01-01", f"{y}-12-31"
        pad = (dt.date.fromisoformat(min(hi, last)) + dt.timedelta(days=45)).isoformat()
        df = storage.load_training_frame(conn, ["rsi_14"], types=cfg["universe"]["tradeable_types"],
                                         start_date=lo, end_date=pad, min_price=cfg["risk"].get("min_price"),
                                         min_dollar_volume=cfg["risk"].get("min_dollar_volume"), include_open=True)
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.sort_values(["ticker", "date"])
        g = df.groupby("ticker", observed=True)["open"]
        df["ret"] = g.shift(-(HORIZON + 1)) / g.shift(-1) - 1
        df = df[(df["date"] >= lo) & (df["date"] <= hi) & df["ret"].notna() & np.isfinite(df["ret"])]
        df["ret"] = df["ret"].clip(-0.95, 3.0)
        df["regime"] = df["date"].map(lambda d: None if bull.get(d) is None else
                                      ("RISK_ON" if bull.get(d) else "RISK_OFF"))
        yr = {}
        for reg, grp in df.dropna(subset=["regime"]).groupby("regime"):
            r = grp["ret"].to_numpy()
            # a sample per year keeps the pooled percentiles honest without holding every row
            acc[reg].append(np.random.default_rng(y).choice(r, size=min(len(r), 50000), replace=False))
            yr[reg] = {"n": int(len(r)), "mean": float(r.mean()), "p05": float(np.quantile(r, .05))}
        by_year[y] = yr
        log.info(f"{y}: " + ", ".join(f"{k} n={v['n']:,} mean={v['mean']:+.2%}" for k, v in yr.items()))
        del df
    pooled = {}
    for reg, parts in acc.items():
        if parts:
            r = np.concatenate(parts)
            pooled[reg] = {"n_sampled": int(len(r)), "mean": float(r.mean()), "median": float(np.median(r)),
                           "p05": float(np.quantile(r, .05)), "sd": float(r.std())}
    on, off = pooled.get("RISK_ON"), pooled.get("RISK_OFF")
    helpful = bool(on and off and off["mean"] < on["mean"] and off["p05"] < on["p05"])
    out = {"rule": "helpful = RISK_OFF mean < RISK_ON mean AND RISK_OFF p05 < RISK_ON p05 (stated before running)",
           "horizon_sessions": HORIZON, "pooled": pooled, "by_year": by_year, "helpful": helpful,
           "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    EVIDENCE.write_text(json.dumps(out, indent=1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", action="store_true")
    ap.add_argument("--evidence", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    if a.state:
        print(json.dumps({**state(conn), "mode": settings(cfg)["mode"]}, indent=1))
    if a.evidence:
        e = evidence(conn, cfg)
        print(json.dumps({k: e[k] for k in ("rule", "pooled", "helpful")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
