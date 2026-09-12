"""
Re-score already-recorded strategies against the current null. A diagnostic.

Written to answer one question: how much of a past result was the strategy, and
how much was the benchmark it happened to be measured against? Every stored
evaluation carries the fitness it earned under whatever null was in force at the
time, and three separate null bugs in this project have each silently changed
what "excess" meant. A number in the ledger is only as good as the benchmark
behind it.

This re-runs stored genomes over their original window under today's null and
prints the two side by side. It **does not write to the ledger** — a re-scored
figure is evidence about the scoring, not a new result the strategy earned, and
overwriting history would destroy the comparison that makes this useful.

Usage:
    python rescore.py --stage validation        # everything that passed validation
    python rescore.py --run <run_id> --limit 25
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import benchmark as bench
import costs as costs_mod
import genome as gn
import ledger
import reward
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rescore")


SELECT = """
    SELECT s.id, s.genome, s.entry_desc, s.complexity,
           e.net_pnl_usd, e.fitness, e.sharpe, e.n_trades,
           e.window_start, e.window_end
    FROM evaluations e JOIN strategies s ON s.id = e.strategy_id
"""


def _rows(conn, stage: str | None, run_id: str | None, limit: int) -> list[dict]:
    if stage:
        sql = (SELECT + " JOIN promotions p ON p.strategy_id = s.id"
               " WHERE p.stage = ? AND p.decision = 'pass'"
               " ORDER BY e.net_pnl_usd DESC LIMIT ?")
        params = (stage, limit)
    elif run_id:
        sql, params = SELECT + " WHERE s.run_id = ? ORDER BY e.net_pnl_usd DESC LIMIT ?", (run_id, limit)
    else:
        sql, params = SELECT + " ORDER BY e.net_pnl_usd DESC LIMIT ?", (limit,)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def run(cfg: dict, stage: str | None, run_id: str | None, limit: int,
        window: tuple[str, str] | None = None) -> None:
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    ledger.init(conn)
    rows = _rows(conn, stage, run_id, limit)
    if not rows:
        raise SystemExit("Nothing to re-score.")

    lab = cfg["lab"]
    if window is None:
        window = (rows[0]["window_start"], rows[0]["window_end"])

    log.info(f"Loading panel {window[0]} -> {window[1]}")
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True)
    panel = simulator.Panel(df)
    del df
    surface = bench.null_surface(conn, cfg, window)

    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    capital = size * cfg["risk"]["max_open_positions"]
    gates = lab.get("gates", {})
    max_entries = lab.get("max_entries_per_eval", 20000)

    print(f"\n  RE-SCORED AGAINST THE PRICE-BUCKETED NULL — {window[0]} to {window[1]}")
    print(f"  {'was fitness':>12}{'now fitness':>12}{'excess':>11}{'net P&L':>11}"
          f"{'med px':>8}{'null %':>8}  {'pass':<5} entry rule")
    print("  " + "-" * 110)

    still, total = 0, 0
    for r in rows:
        g = json.loads(r["genome"])
        res = simulator.simulate(g, panel, cm, size, max_entries=max_entries)
        sc = reward.fitness(res, gn.complexity(g), capital_usd=capital,
                            benchmark_surface=surface, position_size_usd=size)
        total += 1
        ok = (sc.get("excess_pnl_usd", 0) >= gates.get("min_excess_pnl_usd", 0)
              and sc.get("sharpe", 0) >= gates.get("min_sharpe", 0)
              and sc["n_trades"] >= gates.get("min_trades", 20))
        still += ok
        px = res.get("entry_price")
        med = float(sorted(px)[len(px) // 2]) if len(px) else 0.0
        print(f"  {(r['fitness'] or 0):>12.3f}{sc['fitness']:>12.3f}"
              f"{sc.get('excess_pnl_usd', 0):>+11,.0f}{sc['net_pnl_usd']:>+11,.0f}"
              f"{med:>8,.2f}{sc.get('benchmark_net_pct', 0):>+8.2f}  "
              f"{'PASS' if ok else 'fail':<5} {(r['entry_desc'] or '')[:40]}")

    print("  " + "-" * 110)
    print(f"  {still} of {total} still clear the gate once charged the null of the "
          f"stocks they bought.")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", default=None, help="Re-score everything that passed this stage.")
    parser.add_argument("--run", dest="run_id", default=None)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    args = parser.parse_args()
    cfg = load_config()
    runtime.be_nice()
    window = (args.start, args.end) if args.start and args.end else None
    run(cfg, args.stage, args.run_id, args.limit, window)


if __name__ == "__main__":
    main()
