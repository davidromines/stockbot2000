"""
Two checks against the bull-market problem, part of the testing group (owner, 2026-09-27:
"implement the checks as part of the larger testing group. Don't automatically
disqualify an idea but add it to the system").

A long-only strategy makes money in a rising market whether or not it has any skill;
random buying did too. So every strategy past validation carries two more verdicts:

  unseen_vs_random   on the unseen window (holdout.py, 2023 -> today), did it beat
                     random entry at the same prices and holding periods? (the null
                     surface, benchmark.py — what chance earned there)
  bear_vs_random     trades ENTERED during the market's falls — 2008-09, 2011, late
                     2018, the 2020 crash, 2022 — against random entry in those same
                     windows. In a fall random buying loses too, so the question is
                     whether the strategy lost LESS (or made money).

Verdicts: PASS (beat random), FAIL (did not), NA (too few trades to say). They are
recorded, shown in the ranking, the funnel and the Control Center, and they DISQUALIFY
NOTHING — no gate reads them. Same simulator, costs and fills as every backtest.

Bear windows are SPY peak-to-trough periods, fixed here and never tuned. Each window's
panel carries 400 days of warm-up so a rule's lookbacks are defined on day one;
entries are restricted to the window by an extra condition, exits run past it.

    ./venv/bin/python market_checks.py --run [--limit N]
    ./venv/bin/python market_checks.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import copy
import datetime as dt
import json
import logging
import sqlite3
import sys

import league
import strategy_objects as so

log = logging.getLogger("market_checks")
BEAR_WINDOWS = (("gfc_2008", "2007-10-09", "2009-03-09"),
                ("debt_ceiling_2011", "2011-07-22", "2011-10-03"),
                ("selloff_2018q4", "2018-09-20", "2018-12-24"),
                ("covid_2020", "2020-02-19", "2020-03-23"),
                ("bear_2022", "2022-01-03", "2022-10-12"))
WARMUP_DAYS = 400
MIN_TRADES = 30
PASSED = ("VALIDATED", "PROMISING", "PAPER", "QUALIFIED", "LIVE_CANDIDATE", "LIVE", "DEMOTED")
FLAG = "_kc_in_window"


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS market_checks (
        strategy_key TEXT NOT NULL, version INTEGER NOT NULL, check_name TEXT NOT NULL,
        window TEXT NOT NULL, trades INTEGER, net_per_trade REAL, null_per_trade REAL,
        excess_per_trade REAL, verdict TEXT NOT NULL, detail TEXT, computed_at TEXT NOT NULL,
        PRIMARY KEY (strategy_key, version, check_name, window))""")
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def verdict(trades: int, excess_per_trade: float | None) -> str:
    if not trades or trades < MIN_TRADES or excess_per_trade is None:
        return "NA"
    return "PASS" if excess_per_trade > 0 else "FAIL"


def _store(conn, key, ver, check, window, trades, net, null, excess, detail=None) -> str:
    v = verdict(trades, excess)
    conn.execute("INSERT OR REPLACE INTO market_checks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (key, ver, check, window, trades, net, null, excess, v,
                  json.dumps(detail) if detail is not None else None, _now()))
    return v


def checks(conn, key: str, ver: int) -> dict:
    """{check_name: {verdict, excess_per_trade, trades, ...}} — the pooled rows only."""
    try:
        rows = conn.execute("SELECT check_name, trades, net_per_trade, null_per_trade, excess_per_trade, verdict "
                            "FROM market_checks WHERE strategy_key=? AND version=? AND window='all'",
                            (key, ver)).fetchall()
    except sqlite3.Error:
        return {}
    return {r[0]: {"trades": r[1], "net_per_trade": r[2], "null_per_trade": r[3], "excess_per_trade": r[4],
                   "verdict": r[5]} for r in rows}


# --- check 1: the unseen window against random entry ----------------------------------

def unseen_vs_random(conn, key: str, ver: int) -> str | None:
    """From holdout.py's stored one-look result; nothing is re-run."""
    import holdout
    h = holdout.result(conn, key, ver)
    if not h:
        return None
    size = 20.0
    n = int(h.get("trades") or 0)
    ex = (h["excess_vs_null_usd"] / (n * size)) if n and h.get("excess_vs_null_usd") is not None else None
    net = h.get("per_trade")
    null = (net - ex) if (net is not None and ex is not None) else None
    return _store(conn, key, ver, "unseen_vs_random", "all", n, net, null, ex,
                  {"window": [h["window_start"], h["window_end"]]})


# --- check 2: bear markets against random entry -----------------------------------------

def _panel(conn, cfg, name, start, end, fundamentals):
    """The warm-up panel for one bear window, with the entry-window flag column."""
    import factory_pipeline as fp
    lo = (dt.date.fromisoformat(start) - dt.timedelta(days=WARMUP_DAYS)).isoformat()
    p = fp.panel(conn, cfg, (lo, end), fundamentals)
    if p is None:
        return None
    d = p.df["date"].astype(str).str[:10]
    p.df[FLAG] = ((d >= start) & (d <= end)).astype("float32")
    return p


def _in_window(g: dict) -> dict:
    g = copy.deepcopy(g)
    g["entry"] = {"op": "and", "args": [g["entry"], {"op": "gt", "args": [{"col": FLAG}, {"const": 0.5}]}]}
    return g


def bear_candidates(conn, only_missing: bool = True) -> list:
    out = []
    for key, ver, st in conn.execute("""
            SELECT s.strategy_key, s.version, s.to_state FROM league_state s
            JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state GROUP BY 1, 2) m
            ON m.mid = s.id WHERE s.strategy_key LIKE 'fx_%'""").fetchall():
        if league.canonical(st) not in PASSED:
            continue
        if only_missing and conn.execute("SELECT 1 FROM market_checks WHERE strategy_key=? AND version=? AND "
                                         "check_name='bear_vs_random' AND window='all'", (key, ver)).fetchone():
            continue
        g = so.genome(conn, key, ver)
        if g and g.get("entry"):
            out.append((key, ver, g))
    return out


def run_bear(conn, cfg, limit: int | None = None) -> dict:
    import benchmark as bench
    import costs as costs_mod
    import factory_pipeline as fp
    import gc
    import simulator
    todo = bear_candidates(conn)
    todo = todo[:limit] if limit else todo
    if not todo:
        return {"strategies": 0}
    size = float(cfg["risk"]["position_size_usd"])
    cap = int((cfg.get("factory") or {}).get("max_entries_per_backtest", 5000))
    cm = costs_mod.CostModel(cfg)
    need = {(k, v): fp._needs_fund(so.meta(conn, k, v) or {}, g) for k, v, g in todo}
    per = {(k, v): [] for k, v, _ in todo}
    for name, start, end in BEAR_WINDOWS:
        bench.null_surface(conn, cfg, (start, end))           # stored; built before a panel is held
        gc.collect()
        for fund in (False, True):
            group = [(k, v, g) for k, v, g in todo if need[(k, v)] == fund]
            if not group:
                continue
            p = _panel(conn, cfg, name, start, end, fund)
            if p is None:
                continue
            for key, ver, g in group:
                try:
                    gw = _in_window(g)
                    r = simulator.simulate(gw, p, cm, size, max_entries=cap)
                    n = int(r.get("n_trades") or 0)
                    net = float(r.get("net_pnl_usd") or 0)
                    ex = fp._null_excess(conn, cfg, (start, end), r, gw, size) if n else None
                except Exception as e:                        # noqa: BLE001 — one strategy, one window
                    log.warning(f"{key} v{ver} {name}: {type(e).__name__}: {e}")
                    continue
                npt = net / (n * size) if n else None
                ept = ex / (n * size) if (n and ex is not None) else None
                _store(conn, key, ver, "bear_vs_random", name, n, npt,
                       (npt - ept) if (npt is not None and ept is not None) else None, ept)
                per[(key, ver)].append((n, net, ex))
            conn.commit()
            fp._PANELS.clear()
            gc.collect()
        log.info(f"{name}: {len(todo)} strategies")
    out = {"strategies": len(todo), "PASS": 0, "FAIL": 0, "NA": 0}
    for (key, ver), parts in per.items():
        n = sum(x[0] for x in parts)
        net = sum(x[1] for x in parts)
        exs = [x[2] for x in parts if x[0] and x[2] is not None]
        ex = sum(exs) if exs else None
        npt = net / (n * size) if n else None
        ept = ex / (n * size) if (n and ex is not None) else None
        v = _store(conn, key, ver, "bear_vs_random", "all", n, npt,
                   (npt - ept) if (npt is not None and ept is not None) else None, ept,
                   {"windows": [w[0] for w in BEAR_WINDOWS]})
        out[v] += 1
    conn.commit()
    return out


def run(conn, cfg, limit: int | None = None) -> dict:
    init(conn)
    u = {"PASS": 0, "FAIL": 0, "NA": 0}
    try:
        keys = conn.execute("SELECT strategy_key, version FROM holdout_results").fetchall()
    except sqlite3.Error:
        keys = []
    for key, ver in keys:
        v = unseen_vs_random(conn, key, ver)
        if v:
            u[v] += 1
    conn.commit()
    return {"unseen_vs_random": u, "bear_vs_random": run_bear(conn, cfg, limit)}


def summary(conn) -> dict:
    init(conn)
    out = {}
    for check, v, n in conn.execute("SELECT check_name, verdict, COUNT(*) FROM market_checks WHERE window='all' "
                                    "GROUP BY 1, 2"):
        out.setdefault(check, {})[v] = n
    return out


def report(conn) -> str:
    s = summary(conn)
    lines = ["MARKET CHECKS (recorded, never a gate)"]
    for c in ("unseen_vs_random", "bear_vs_random"):
        d = s.get(c, {})
        lines.append(f"  {c:<18} PASS {d.get('PASS', 0):>4}  FAIL {d.get('FAIL', 0):>4}  NA {d.get('NA', 0):>4}")
    rows = conn.execute("""SELECT b.strategy_key, m.family, b.trades, b.net_per_trade, b.excess_per_trade, b.verdict,
        u.excess_per_trade, u.verdict FROM market_checks b
        LEFT JOIN market_checks u ON u.strategy_key=b.strategy_key AND u.version=b.version
             AND u.check_name='unseen_vs_random' AND u.window='all'
        LEFT JOIN strategy_meta m ON m.strategy_key=b.strategy_key AND m.version=b.version
        WHERE b.check_name='bear_vs_random' AND b.window='all' AND b.trades >= ?
        ORDER BY b.excess_per_trade DESC""", (MIN_TRADES,)).fetchall()
    lines += ["", f"  {'strategy':<36}{'family':<22}{'bear trades':>12}{'bear net':>10}{'vs random':>10}"
                  f"{'unseen vs random':>18}"]
    for r in rows[:25]:
        lines.append(f"  {r[0][:35]:<36}{(r[1] or '')[:21]:<22}{r[2]:>12}"
                     f"{(f'{r[3]:+.2%}' if r[3] is not None else '—'):>10}"
                     f"{(f'{r[4]:+.2%}' if r[4] is not None else '—'):>10}"
                     f"{(f'{r[6]:+.2%}' if r[6] is not None else '—'):>18}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    init(conn)
    if a.run:
        print(json.dumps(run(conn, cfg, a.limit), indent=2))
    if a.report or a.run:
        print(report(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
