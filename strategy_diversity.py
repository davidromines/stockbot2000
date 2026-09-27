"""
Choose the five slots as a set of DIFFERENT bets (owner, 2026-09-27: "go 2").

The central rule of the project direction: the live roster is the top five ELIGIBLE
strategies after correlation constraints — never the five highest scores, which fill
every slot with copies of one trade. eligibility.py holds that rule but reads forward
equity curves, which are weeks long and measure nothing yet. This module measures
correlation from BACKTESTS instead, so it works now:

  1. every top-ranked candidate (and every current holder) is simulated on the same
     recent window — 2023 -> today — with the one simulator, costs and fills;
  2. each strategy's trades become a weekly series: the mean net return of the trades
     it ENTERED that week;
  3. every pair is correlated over the weeks both traded (at least MIN_WEEKS).

slots.plan skips a candidate whose correlation with anything already held or chosen
exceeds `slots.max_correlation` (0.7). A pair with no measurement (a fund with no
genome — pair / value / crypto — or too few shared weeks) falls back to the family cap
rather than blocking: every genome strategy near the top IS measured here.

Reading the window is not a look at a sealed result: these runs choose between
strategies that already passed every gate; nothing here ranks, admits or rejects.

    ./venv/bin/python strategy_diversity.py --run [--top 40]
    ./venv/bin/python strategy_diversity.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import logging
import sqlite3
import sys

import numpy as np
import pandas as pd

log = logging.getLogger("strategy_diversity")
START = "2023-01-01"
MIN_WEEKS = 26


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS strategy_weekly (
        strategy_key TEXT NOT NULL, version INTEGER NOT NULL, week TEXT NOT NULL,
        mean_ret REAL NOT NULL, trades INTEGER NOT NULL, computed_at TEXT NOT NULL,
        PRIMARY KEY (strategy_key, version, week))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS strategy_correlation (
        key_a TEXT NOT NULL, ver_a INTEGER NOT NULL, key_b TEXT NOT NULL, ver_b INTEGER NOT NULL,
        corr REAL, weeks INTEGER NOT NULL, computed_at TEXT NOT NULL,
        PRIMARY KEY (key_a, ver_a, key_b, ver_b))""")
    conn.commit()


def weekly(result: dict, dates) -> pd.Series:
    """week (ISO 'YYYY-Www') -> mean net return of the trades entered that week."""
    if not result.get("n_trades"):
        return pd.Series(dtype=float)
    d = pd.to_datetime(pd.Series(np.asarray(dates)[result["entry_rows"]]))
    ret = np.asarray(result["pnl_series"], dtype=float) / 20.0
    wk = d.dt.strftime("%G-W%V")
    return pd.Series(ret).groupby(wk.to_numpy()).mean()


def corr(a: pd.Series, b: pd.Series) -> tuple:
    """(correlation, shared weeks). None below MIN_WEEKS — a thin overlap is not a measurement."""
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    n = len(j)
    if n < MIN_WEEKS or j.iloc[:, 0].std() == 0 or j.iloc[:, 1].std() == 0:
        return None, n
    return float(j.iloc[:, 0].corr(j.iloc[:, 1])), n


def lookup(conn, a: tuple, b: tuple):
    """The stored correlation of two (key, version) pairs, either order; None when unmeasured."""
    try:
        r = conn.execute("SELECT corr FROM strategy_correlation WHERE (key_a=? AND ver_a=? AND key_b=? AND ver_b=?) "
                         "OR (key_a=? AND ver_a=? AND key_b=? AND ver_b=?)", (*a, *b, *b, *a)).fetchone()
    except sqlite3.Error:
        return None
    return r[0] if r else None


def candidates(conn, cfg, top: int) -> list:
    """(key, version, genome) for the top `top` gate-passing strategies and every current holder."""
    import ranking
    import slots
    rows = [r for r in ranking.rank(conn, cfg) if r["passes_gate"]][:top]
    keys = [(r["strategy_key"], r["version"]) for r in rows]
    for h in slots.current(conn, cfg).values():
        if h and (h["strategy_key"], h["version"]) not in keys:
            keys.append((h["strategy_key"], h["version"]))
    out = []
    for key, ver in keys:
        try:
            g = slots.genome_for(conn, key, ver)
        except Exception:                                    # noqa: BLE001
            g = None
        if g and isinstance(g.get("entry"), dict) and not (g.get("pair") or g.get("value") or g.get("crypto")):
            out.append((key, ver, g))
    return out


def run(conn, cfg, top: int = 40) -> dict:
    import costs as costs_mod
    import factory_pipeline as fp
    import simulator
    import storage
    init(conn)
    end = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
    todo = candidates(conn, cfg, top)
    size = float(cfg["risk"]["position_size_usd"])
    cap = int((cfg.get("factory") or {}).get("max_entries_per_backtest", 5000))
    cm, now = costs_mod.CostModel(cfg), dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    series = {}
    for need in (False, True):
        group = [(k, v, g) for k, v, g in todo if storage.needs_panel(g) == need]
        if not group:
            continue
        p = fp.panel(conn, cfg, (START, end), need)
        if p is None:
            continue
        for key, ver, g in group:
            try:
                r = simulator.simulate(g, p, cm, size, max_entries=cap)
            except Exception as e:                            # noqa: BLE001
                log.warning(f"{key} v{ver}: {type(e).__name__}: {e}")
                continue
            w = weekly(r, p.dates)
            series[(key, ver)] = w
            conn.execute("DELETE FROM strategy_weekly WHERE strategy_key=? AND version=?", (key, ver))
            conn.executemany("INSERT INTO strategy_weekly VALUES (?,?,?,?,?,?)",
                             [(key, ver, wk, float(v), 0, now) for wk, v in w.items()])
            conn.commit()
        fp._PANELS.clear()
    keys = sorted(series)
    pairs = 0
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            c, n = corr(series[a], series[b])
            conn.execute("INSERT OR REPLACE INTO strategy_correlation VALUES (?,?,?,?,?,?,?)", (*a, *b, c, n, now))
            pairs += 1
    conn.commit()
    return {"strategies": len(keys), "pairs": pairs, "window": [START, end]}


def report(conn, cfg) -> str:
    import slots
    init(conn)
    p = slots.plan(conn, cfg)
    names = {r["strategy_key"]: r.get("name") or r["strategy_key"] for r in p["ranked"]}
    lines = ["SLOT PLAN with the correlation limit "
             f"{slots.settings(cfg)['max_correlation']:.2f} (measured 2023 -> today, weekly)"]
    for slot, r, why in p["assign"]:
        lines.append(f"  slot {slot}: {names.get(r['strategy_key'], r['strategy_key'])[:50]}  — {why}")
    for s, h in (p["keep"] or {}).items():
        lines.append(f"  slot {s}: keeps {names.get(h['strategy_key'], h['strategy_key'])[:50]}")
    sk = p.get("skipped_correlated") or []
    if sk:
        lines += ["", "  skipped as too similar to a chosen strategy:"] + [
            f"    {names.get(k, k)[:46]:<47} corr {c:+.2f} with {names.get(w, w)[:40]}" for k, c, w in sk[:15]]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    init(conn)
    if a.run:
        print(json.dumps(run(conn, cfg, a.top), indent=2))
    if a.report or a.run:
        print(report(conn, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
