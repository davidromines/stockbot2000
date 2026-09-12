"""
The evolutionary search. Phase 09.

Generate random strategies, score them on money, keep the winners, mutate them,
repeat. Everything tried is recorded in the ledger with its parentage.

The loop is deliberately plain: tournament selection, elitism, mutation and
crossover. Sophistication in the search is not where the risk lies — the risk is
in the fitness function and the validation ladder, and those are handled
elsewhere. A clever optimiser pointed at a bad objective just finds bad answers
faster.

**Selection pressure is on net P&L after costs**, via the fitness function.
Strategies that lose money score exactly zero, so they neither reproduce nor
anchor the population.

Parallelism: workers inherit the panel through fork rather than receiving it over
a pipe. Copy-on-write keeps that nearly free on Linux as long as nothing writes to
it, and nothing does — the panel is read-only once built. Pickling a 1.3 GB panel
to each worker instead would cost more than the parallelism saves.

Measured on the full 2006-2019 window: 0.97 evaluations/sec on one core, so the
200k-per-night figure in STRATEGY_LAB.md was only ever reachable with workers.

Usage:
    python evolve.py --generations 10 --population 200
    python evolve.py --report                 # best strategies by money
    python evolve.py --lineage <strategy_id>  # how a winner was arrived at
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import multiprocessing as mp
import os
import random
import signal
import sys
import time

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
log = logging.getLogger("evolve")

_stop = False


def _handle_interrupt(signum, frame):
    global _stop
    if _stop:
        sys.exit(130)
    _stop = True
    log.warning("Interrupt received. Finishing this generation, then stopping.")


_W: dict = {}     # per-worker state, populated by fork


def _init_worker(panel, cost_model, position_size, capital, max_entries, surface,
                 reward_params):
    """Runs once per worker. The panel arrives by fork, not by pickle."""
    _W.update(panel=panel, cost_model=cost_model, position_size=position_size,
              capital=capital, max_entries=max_entries, surface=surface,
              reward_params=reward_params)


def _eval_worker(genome_dict):
    return evaluate_one(genome_dict, _W["panel"], _W["cost_model"],
                        _W["position_size"], _W["capital"], _W["max_entries"],
                        _W["surface"], _W["reward_params"])


def evaluate_one(genome_dict, panel, cost_model, position_size, capital, max_entries,
                 benchmark_surface=None, reward_params=None):
    """Simulate and score one candidate. Kept separate so it can be parallelised."""
    result = simulator.simulate(genome_dict, panel, cost_model, position_size,
                                max_entries=max_entries)
    scored = reward.fitness(result, gn.complexity(genome_dict), capital_usd=capital,
                            benchmark_surface=benchmark_surface,
                            position_size_usd=position_size, cfg=reward_params)
    scored["gross_pnl_usd"] = result.get("gross_pnl_usd")
    scored["costs_usd"] = result.get("costs_usd")
    scored["win_rate"] = result.get("win_rate")
    return scored


def tournament(pop, rng, k: int = 3):
    """Pick the best of k at random. Cheap, and keeps diversity alive."""
    return max(rng.sample(pop, min(k, len(pop))), key=lambda x: x[0]["fitness"])


def run(config: dict, generations: int, population: int, window: tuple[str, str],
        seed: int | None = None) -> str:
    lab = config.get("lab", {})
    max_entries = lab.get("max_entries_per_eval", 20000)
    elite_frac = lab.get("elite_fraction", 0.15)
    mutation_rate = lab.get("mutation_rate", 0.6)
    rng = random.Random(seed)

    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)
    ledger.init(conn)

    log.info(f"Loading panel {window[0]} -> {window[1]}")
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=config["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=config["risk"].get("min_price"),
        min_dollar_volume=config["risk"].get("min_dollar_volume"),
        include_liquidity=True)
    panel = simulator.Panel(df)
    log.info(f"Panel: {panel.n:,} rows, {panel.memory_gb():.2f} GB")

    stats = gn.column_stats(df, FEATURE_COLS + gn.BASE_PRIMITIVES)
    grammar = gn.Grammar(FEATURE_COLS, stats, max_depth=lab.get("max_depth", 4), seed=seed)
    cost_model = costs_mod.CostModel(config)
    reward_params = reward.params_from_config(config)
    position_size = config["risk"]["position_size_usd"]
    capital = position_size * config["risk"]["max_open_positions"]

    surface = bench.null_surface(conn, config, window)
    bands = bench.price_bands(config)
    log.info(f"Null surface for this window ({len(bands)} price bands x "
             f"{len(bench.ANCHORS)} holding periods):")
    for b in bands:
        log.info(f"  ${b[0]:>6,.0f}-${min(b[1], 99999):>6,.0f}  "
                 f"{surface[b][5]:+.3f}% at 5d, {surface[b][45]:+.3f}% at 45d")
    log.info("  each strategy is charged the null of the stocks it actually bought, "
             "at its own holding period")

    run_id = ledger.new_run(conn, window, generations, population,
                            {"lab": lab, "risk": config["risk"], "costs": config["costs"]})
    log.info(f"Run {run_id}: {generations} generations x {population} candidates")

    workers = int(lab.get("workers", max(1, (os.cpu_count() or 2) - 1)))
    pool = None
    if workers > 1:
        # fork so the panel is inherited rather than pickled to each worker.
        ctx = mp.get_context("fork")
        pool = ctx.Pool(workers, initializer=_init_worker,
                        initargs=(panel, cost_model, position_size, capital,
                                  max_entries, surface))
        log.info(f"Evaluating across {workers} workers")

    trial = 0
    pop: list = []
    started = time.time()

    for gen in range(generations):
        if _stop:
            break
        candidates = []

        if gen == 0:
            for _ in range(population):
                candidates.append((grammar.random_genome(), "random", None))
        else:
            n_elite = max(1, int(population * elite_frac))
            elites = sorted(pop, key=lambda x: x[0]["fitness"], reverse=True)[:n_elite]
            for scored, g, sid in elites:
                candidates.append((g, "elite", sid))
            while len(candidates) < population:
                if rng.random() < mutation_rate or len(pop) < 2:
                    _, parent, pid = tournament(pop, rng)
                    candidates.append((grammar.mutate(parent), "mutation", pid))
                else:
                    _, a, aid = tournament(pop, rng)
                    _, b, _ = tournament(pop, rng)
                    candidates.append((grammar.crossover(a, b), "crossover", aid))

        genomes = [g for g, _, _ in candidates]
        if pool is not None:
            # chunksize 1: evaluation time varies a lot between genomes, and
            # larger chunks leave workers idle at the end of a generation.
            scores = pool.map(_eval_worker, genomes, chunksize=1)
        else:
            scores = [evaluate_one(g, panel, cost_model, position_size, capital,
                                   max_entries, surface, reward_params) for g in genomes]

        scored_pop = []
        for (g, origin, parent_id), scored in zip(candidates, scores):
            trial += 1
            sid = ledger.record(conn, run_id, gen, origin, g, gn.describe,
                                gn.complexity(g), parent_id, scored, window, trial)
            scored_pop.append((scored, g, sid))
        conn.commit()

        if not scored_pop:
            break
        pop = scored_pop
        best = max(pop, key=lambda x: x[0]["fitness"])[0]
        money = max(pop, key=lambda x: x[0].get("excess_pnl_usd", 0))[0]
        profitable = sum(1 for s, _, _ in pop if s.get("excess_pnl_usd", 0) > 0)
        rate = trial / (time.time() - started)
        log.info(f"gen {gen + 1}/{generations}  best fitness {best['fitness']:.3f}  "
                 f"best excess ${money.get('excess_pnl_usd', 0):+,.0f}  "
                 f"beating the null {profitable}/{len(pop)}  {rate:.1f} evals/s")

    if pool is not None:
        pool.close()
        pool.join()
    ledger.finish_run(conn, run_id, trial)
    s = ledger.run_stats(conn, run_id)
    log.info("-" * 60)
    log.info(f"Run {run_id}: {s.get('evaluated', trial):,} evaluated, "
             f"{s.get('profitable') or 0:,} profitable, "
             f"best net P&L ${(s.get('best_pnl') or 0):+,.2f}")
    if _stop:
        log.warning("Stopped early — the run is recorded and the ledger is intact.")
    conn.close()
    return run_id


def report(config: dict, run_id: str | None, limit: int = 15) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    ledger.init(conn)
    rows = ledger.top_by_pnl(conn, run_id, limit)
    if not rows:
        print("No strategies recorded yet — run --generations first.")
        conn.close()
        return
    print(f"{'net P&L':>10} {'fitness':>8} {'trades':>8} {'gen':>4} {'origin':>9}  entry rule")
    print("-" * 100)
    for r in rows:
        print(f"{r['net_pnl_usd']:>+10.2f} {r['fitness']:>8.3f} {r['n_trades']:>8,} "
              f"{r['generation']:>4} {r['origin']:>9}  {(r['entry_desc'] or '')[:52]}")
    print(f"\n  id of best: {rows[0]['id']}   (evolve.py --lineage {rows[0]['id']})")
    conn.close()


def show_lineage(config: dict, sid: str) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    ledger.init(conn)
    chain = ledger.lineage(conn, sid)
    if not chain:
        print("No such strategy.")
    else:
        print(f"{'gen':>4} {'origin':>9} {'fitness':>8} {'net P&L':>10}  entry rule")
        print("-" * 96)
        for r in chain:
            print(f"{r['generation']:>4} {r['origin']:>9} {(r['fitness'] or 0):>8.3f} "
                  f"{(r['net_pnl_usd'] or 0):>+10.2f}  {(r['entry_desc'] or '')[:48]}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--population", type=int, default=200)
    parser.add_argument("--start", default=None, help="Search window start (default from config).")
    parser.add_argument("--end", default=None, help="Search window end.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--lineage", metavar="ID")
    args = parser.parse_args()

    config = load_config()
    runtime.be_nice()

    if args.lineage:
        show_lineage(config, args.lineage); return
    if args.report:
        report(config, args.run_id); return

    lab = config.get("lab", {})
    window = (args.start or lab.get("search_start", "2006-01-01"),
              args.end or lab.get("search_end", "2019-12-31"))
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)
    run(config, args.generations, args.population, window, args.seed)


if __name__ == "__main__":
    main()
