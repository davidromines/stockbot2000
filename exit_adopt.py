"""
Adopt the profit exits that won the registered sweep (Profit exits, step P3).

The experiment `exit_rules` (exit_sweep.py) tested each slot strategy AS IT WAS
against take-profit / trailing-stop variants, with the adoption rule written
before any result: a cell is ADOPTABLE only if it beats the strategy's own
exits on net P&L per trade over 2006-2019 AND in a majority of two-year blocks.

For each strategy with an adoptable cell, the best one (net per trade) becomes
a NEW strategy — never an edit of the old one:

  - the genome exactly as tested (the experiment spec froze it) with the
    winning exit genes applied — the same apply() the sweep used
  - its own paper fund (paper_trading.start), so it builds its own forward
    record; a changed rule never inherits the old one's
  - registered in the league at PAPER with parent_key = the original and
    source_ref = exit_rules, so its ancestry is permanent
  - the original is untouched and keeps its slot until the ranking and the
    slot engine's own replacement rules say otherwise

Nothing here touches a slot, an order or the live account. The ranking scores
the new strategy once survivorship_backtest.py has run for it (nightly, or
--run by hand).

    ./venv/bin/python exit_adopt.py            # show what would be adopted
    ./venv/bin/python exit_adopt.py --apply    # open the funds, register, complete the experiment
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import exit_sweep as xs

SINK = Path("data/exit_sweep.jsonl")
ACTOR = "exit_adopt"


def winners(rows: list) -> dict:
    """strategy -> (cell, aggregate, verdict) for its best ADOPTABLE cell."""
    agg = xs.combine(rows)
    v = xs.verdicts(agg)
    out = {}
    for (s, c), vv in v.items():
        if not vv["adoptable"]:
            continue
        if s not in out or agg[(s, c)]["net_per_trade"] > out[s][1]["net_per_trade"]:
            out[s] = (c, agg[(s, c)], vv)
    return {s: w + (agg[(s, xs.AS_IS)],) for s, w in out.items()}


def _overrides(cell: str) -> dict:
    return dict(xs.cells())[cell]


def existing(conn, parent: str, cell: str) -> str | None:
    r = conn.execute("SELECT strategy_key FROM league_strategies WHERE parent_key=? AND source_ref=? "
                     "AND hypothesis LIKE ?", (parent, "exit_rules", f"%[{cell}]%")).fetchone()
    return r[0] if r else None


def adopt(conn, cfg, spec: dict, rows: list, apply_: bool) -> list:
    import league
    import migrate_league
    import paper_trading
    done = []
    for strat, (cell, a, vv, base) in sorted(winners(rows).items()):
        parent, ver = strat.split("@v")
        name = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                             (parent, int(ver))).fetchone() or [parent])[0]
        new_name = f"{name} · exit {cell}"
        item = {"parent": parent, "name": new_name, "cell": cell,
                "net_per_trade": a["net_per_trade"], "base_net_per_trade": base["net_per_trade"],
                "blocks_won": f"{vv['blocks_won']}/{vv['blocks']}", "trades": a["trades"]}
        have = existing(conn, parent, cell)
        if have:
            done.append({**item, "strategy_key": have, "status": "already adopted"})
            continue
        if not apply_:
            done.append({**item, "status": "would adopt"})
            continue
        genome = xs.apply(spec["entry_rule"][strat], _overrides(cell))
        family = (conn.execute("SELECT family FROM paper_runs WHERE run_id=?",
                               (parent.split(":", 1)[1],)).fetchone() or [None])[0]
        paper_trading.init(conn)
        run_id = paper_trading.start(conn, cfg, name=new_name, strategy=json.dumps(genome, sort_keys=True))
        conn.execute("UPDATE paper_runs SET label=?, family=? WHERE run_id=?", (new_name[:60], family, run_id))
        conn.commit()
        key = f"paper:{run_id}"
        run = dict(zip(("strategy", "family", "capital_usd"),
                       conn.execute("SELECT strategy, family, capital_usd FROM paper_runs WHERE run_id=?",
                                    (run_id,)).fetchone()))
        hyp = (f"exit_rules sweep [{cell}]: net ${a['net_per_trade']:+.3f}/trade vs ${base['net_per_trade']:+.3f} "
               f"as it was, 2006-2019, won {vv['blocks_won']}/{vv['blocks']} two-year blocks")
        league.register(conn, key, new_name, migrate_league._paper_spec(run), author=ACTOR,
                        source_kind="experiment", source_ref="exit_rules", parent_key=parent,
                        ancestry=[parent], hypothesis=hyp)
        league.transition(conn, key, "PAPER", f"adopted from experiment exit_rules: {hyp}", actor=ACTOR)
        done.append({**item, "strategy_key": key, "status": "adopted"})
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Adopt the exit_rules sweep's winning profit exits.")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    import experiment_registry as er
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    e = er.get(conn, xs.EXPERIMENT)
    spec = json.loads(e["spec"])
    rows = [json.loads(x) for x in SINK.read_text().splitlines() if x.strip()]
    out = adopt(conn, cfg, spec, rows, a.apply)
    for r in out:
        print(f"  {r['status']:<16} {r['name']}: ${r['base_net_per_trade']:+.3f} -> ${r['net_per_trade']:+.3f} "
              f"net/trade, {r['blocks_won']} blocks" + (f"  [{r['strategy_key']}]" if r.get("strategy_key") else ""))
    if a.apply and e["status"] != "COMPLETE":
        agg = xs.combine(rows)
        v = xs.verdicts(agg)
        results = {"rows": len(rows), "adoptable": sorted(f"{s} {c}" for (s, c), vv in v.items() if vv["adoptable"]),
                   "adopted": [{k: r.get(k) for k in ("parent", "cell", "strategy_key", "net_per_trade",
                                                      "base_net_per_trade", "blocks_won")} for r in out]}
        er.complete(conn, xs.EXPERIMENT, results,
                    "Tight profit exits (5-10% take-profit, 2-3 ATR trailing) lowered net per trade for every "
                    "slot strategy. A +20% take-profit is adoptable for Rising 200 Stop 2.5 only; MACD Pullback "
                    "does better WITHOUT its take-profit. Adopted as new versions with their own paper funds.")
        print(f"  experiment {xs.EXPERIMENT} COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
