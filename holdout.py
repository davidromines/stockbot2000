"""
The unseen-data test: every factory / knowledge strategy that passed its own backtest
and validation, run ONCE on 2023-01-01 -> today (owner, 2026-09-27: "Do 1").

Why this window: factory strategies are backtested on 2016-2019 and validated on
2020-2022; 2023 onward is the Lab's sealed period and no factory strategy has ever
been evaluated on it. Nearly four years of recent market that no rule was built,
chosen or tuned on is the most honest evidence available before forward trading.

The sealed period's rule applies here unchanged: each strategy VERSION is evaluated
against it exactly once, ever. A stored result is never recomputed, never
overwritten, and never feeds back into generation — recycling reads failure_log,
which this module never writes, and variants come from validation, not from here. A
strategy changed after its look is a new version and gets its own single look.

Same simulator, costs, next-open fills and gap-through-stop as every other backtest
(factory_pipeline.panel / simulator.simulate). Survivors-only data, but survivorship
is smallest in this window (our coverage of the knowable universe is ~84% in 2024).

ranking.py reads the result (settings `ranking.use_holdout`): a strategy that loses
on the unseen window fails the gate, and the unseen result becomes its prior in
place of the 2016-19 backtest.

    ./venv/bin/python holdout.py --run [--limit N]
    ./venv/bin/python holdout.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone

import league
import strategy_objects as so

log = logging.getLogger("holdout")
START = "2023-01-01"
PASSED = ("VALIDATED", "PROMISING", "PAPER", "QUALIFIED", "LIVE_CANDIDATE", "LIVE", "DEMOTED")


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS holdout_results (
        strategy_key TEXT NOT NULL, version INTEGER NOT NULL, window_start TEXT NOT NULL,
        window_end TEXT NOT NULL, trades INTEGER, gross_usd REAL, costs_usd REAL, net_usd REAL,
        per_trade REAL, win_rate REAL, excess_vs_null_usd REAL, gap_loss_usd REAL,
        evaluated_at TEXT NOT NULL, PRIMARY KEY (strategy_key, version))""")
    conn.commit()


def result(conn, key: str, ver: int) -> dict | None:
    try:
        r = conn.execute("SELECT * FROM holdout_results WHERE strategy_key=? AND version=?", (key, ver)).fetchone()
    except sqlite3.Error:
        return None
    if not r:
        return None
    cols = [d[0] for d in conn.execute("SELECT * FROM holdout_results LIMIT 0").description]
    return dict(zip(cols, r))


def candidates(conn) -> list:
    """(key, version, needs_panel) for every factory object past validation with no look yet."""
    import factory_pipeline as fp
    out = []
    for key, ver, st in conn.execute("""
            SELECT s.strategy_key, s.version, s.to_state FROM league_state s
            JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state GROUP BY 1, 2) m
            ON m.mid = s.id WHERE s.strategy_key LIKE 'fx_%'""").fetchall():
        if league.canonical(st) not in PASSED or result(conn, key, ver):
            continue
        g = so.genome(conn, key, ver)
        if not g or not g.get("entry"):
            continue
        out.append((key, ver, fp._needs_fund(so.meta(conn, key, ver) or {}, g)))
    return out


def evaluate(conn, cfg, key: str, ver: int, p, end: str) -> dict:
    """Run one strategy on the loaded unseen panel and store it. Refuses a second look."""
    import costs as costs_mod
    import factory_pipeline as fp
    import simulator
    if result(conn, key, ver):
        raise RuntimeError(f"{key} v{ver} already had its one look at the unseen window")
    g = so.genome(conn, key, ver)
    size = float(cfg["risk"]["position_size_usd"])
    cap = int((cfg.get("factory") or {}).get("max_entries_per_backtest", 5000))
    r = simulator.simulate(g, p, costs_mod.CostModel(cfg), size, max_entries=cap)
    m = fp._metrics(r)
    import hold_period
    hold_period.record(conn, key, ver, r.get("avg_hold_days"), "unseen window")
    per = m["net_usd"] / (m["trades"] * size) if m["trades"] else None
    row = {"strategy_key": key, "version": ver, "window_start": START, "window_end": end,
           "trades": m["trades"], "gross_usd": m["gross_usd"], "costs_usd": m["costs_usd"], "net_usd": m["net_usd"],
           "per_trade": per, "win_rate": m["win_rate"],
           "excess_vs_null_usd": fp._null_excess(conn, cfg, (START, end), r, g, size),
           "gap_loss_usd": float(r.get("gap_loss_usd") or 0),
           "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    conn.execute(f"INSERT INTO holdout_results ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                 tuple(row.values()))
    so.record_metrics(conn, key, ver, "holdout", window=json.dumps([START, end]), gross_usd=m["gross_usd"],
                      costs_usd=m["costs_usd"], net_usd=m["net_usd"], trades=m["trades"], win_rate=m["win_rate"],
                      excess_vs_null_usd=row["excess_vs_null_usd"], survivorship_status="SURVIVORSHIP_LIMITED",
                      detail={"per_trade": per, "one_look": True})
    conn.commit()
    return row


def run(conn, cfg, limit: int | None = None) -> dict:
    """Every candidate once. Panels are loaded once per kind (price-only / with the panel)."""
    import factory_pipeline as fp
    init(conn)
    end = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
    todo = candidates(conn)[:limit] if limit else candidates(conn)
    out = {"evaluated": 0, "positive": 0, "negative": 0, "no_trades": 0, "errors": 0, "window": [START, end]}
    # The random-entry null for this window loads its own full panel; build it (it is
    # stored) BEFORE a strategy panel is in memory — together they passed 5 GB (OOM, 09-27).
    if todo:
        import benchmark as bench
        import gc
        bench.null_surface(conn, cfg, (START, end))
        gc.collect()
    for need in (False, True):
        group = [(k, v) for k, v, n in todo if n == need]
        if not group:
            continue
        p = fp.panel(conn, cfg, (START, end), need)
        if p is None:
            continue
        for key, ver in group:
            try:
                row = evaluate(conn, cfg, key, ver, p, end)
            except Exception as e:                            # noqa: BLE001 — one strategy, not the run
                log.warning(f"{key} v{ver}: {type(e).__name__}: {e}")
                out["errors"] += 1
                continue
            out["evaluated"] += 1
            if not row["trades"]:
                out["no_trades"] += 1
            elif row["net_usd"] > 0:
                out["positive"] += 1
            else:
                out["negative"] += 1
            log.info(f"{key} v{ver}: {row['trades']} trades, net ${row['net_usd']:+.2f}"
                     + (f" ({row['per_trade']:+.3%}/trade)" if row["per_trade"] is not None else ""))
    return out


def report(conn) -> str:
    init(conn)
    rows = conn.execute("""SELECT h.strategy_key, h.version, h.trades, h.per_trade, h.net_usd,
        (SELECT net_usd * 1.0 / NULLIF(trades, 0) / 20 FROM strategy_metrics m WHERE m.strategy_key=h.strategy_key
         AND m.version=h.version AND m.phase='backtest' ORDER BY id DESC LIMIT 1) bt,
        (SELECT family FROM strategy_meta sm WHERE sm.strategy_key=h.strategy_key AND sm.version=h.version) fam
        FROM holdout_results h ORDER BY h.per_trade DESC""").fetchall()
    if not rows:
        return "no strategy has had its unseen-window look yet"
    pos = [r for r in rows if r[4] and r[4] > 0]
    kept = [r for r in rows if r[5] is not None and r[3] is not None]
    held_up = sum(1 for r in kept if r[5] > 0 and r[3] > 0)
    lines = [f"UNSEEN WINDOW {START} -> today: {len(rows)} strategies, one look each",
             f"  net positive {len(pos)}, net negative or flat {len(rows) - len(pos)}",
             f"  positive in the 2016-19 backtest AND on the unseen window: {held_up} of "
             f"{sum(1 for r in kept if r[5] > 0)}", "",
             f"  {'strategy':<36}{'family':<22}{'trades':>7}{'backtest':>10}{'unseen':>10}"]
    for r in rows[:25]:
        lines.append(f"  {r[0][:35]:<36}{(r[6] or '')[:21]:<22}{r[2]:>7}"
                     f"{(f'{r[5]:+.2%}' if r[5] is not None else '—'):>10}"
                     f"{(f'{r[3]:+.2%}' if r[3] is not None else '—'):>10}")
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
    conn.row_factory = sqlite3.Row
    init(conn)
    if a.run:
        print(json.dumps(run(conn, cfg, a.limit), indent=2))
    if a.report or a.run:
        print(report(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
