"""
The random-strategy control. Does the ladder actually filter anything?

A validation gate is only worth having if noise fails it. This runs N random,
never-evolved strategies through the same gates a real candidate faces and
reports the pass rate. That rate **is** the false-positive rate of the ladder.

The measurement that prompted this module: under the original gates, **52% of
random strategies passed validation** and 38% were profitable in-sample. A filter
that admits half of all noise is not a filter, and running a 200,000-candidate
search behind it would have produced a shortlist of roughly 100,000 coincidences.

Run this after any change to the fitness function or the gates. A gate that has
never been tested against noise is an assumption, not a control.

Target: random strategies should pass at **under 5%**. Higher than that and any
shortlist the search produces is mostly luck.

Usage:
    python control.py --n 100                  # measure the current gates
    python control.py --n 100 --calibrate      # also suggest thresholds
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np

import benchmark as bench
import costs as costs_mod
import genome as gn
import reward
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("control")


def _panel(conn, cfg, window):
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True)
    return simulator.Panel(df), df


def run(cfg: dict, n: int, calibrate: bool = False, seed: int = 1234) -> dict:
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    lab = cfg["lab"]
    search_w = (lab["search_start"], lab["search_end"])
    valid_w = (lab["validation_start"], lab["validation_end"])

    log.info("Loading panels")
    search_panel, df = _panel(conn, cfg, search_w)
    valid_panel, _ = _panel(conn, cfg, valid_w)
    curve_s = bench.null_curve(conn, cfg, search_w)
    curve_v = bench.null_curve(conn, cfg, valid_w)
    log.info(f"Null curve (validation): {curve_v[5]:+.3f}% at 5d, {curve_v[45]:+.3f}% at 45d")

    stats = gn.column_stats(df, FEATURE_COLS + gn.BASE_PRIMITIVES)
    grammar = gn.Grammar(FEATURE_COLS, stats, max_depth=lab.get("max_depth", 4), seed=seed)
    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    capital = size * cfg["risk"]["max_open_positions"]
    max_entries = lab.get("max_entries_per_eval", 20000)
    gates = lab.get("gates", {"min_excess_pnl_usd": 0.0, "min_sharpe": 0.0, "min_trades": 20})

    raw_profit = beats_null = passes_validation = 0
    excesses, sharpes = [], []

    for i in range(n):
        g = grammar.random_genome()
        rs = simulator.simulate(g, search_panel, cm, size, max_entries=max_entries)
        fs = reward.fitness(rs, gn.complexity(g), capital_usd=capital,
                            benchmark_curve=curve_s, position_size_usd=size)
        rv = simulator.simulate(g, valid_panel, cm, size, max_entries=max_entries)
        fv = reward.fitness(rv, gn.complexity(g), capital_usd=capital,
                            benchmark_curve=curve_v, position_size_usd=size)

        raw_profit += fv["net_pnl_usd"] > 0
        beats_null += fv.get("excess_pnl_usd", 0) > 0
        # The live gate, exactly as promote.validate applies it — read from the
        # same config, so this can never drift from what the ladder enforces.
        if (fv.get("excess_pnl_usd", 0) >= gates.get("min_excess_pnl_usd", 0)
                and fv.get("sharpe", 0) >= gates.get("min_sharpe", 0)
                and fv["n_trades"] >= gates.get("min_trades", 20)):
            passes_validation += 1
        excesses.append(fv.get("excess_pnl_usd", 0.0))
        sharpes.append(fv.get("sharpe", 0.0))
        if (i + 1) % 25 == 0:
            log.info(f"  {i + 1}/{n} — {passes_validation} passing")

    conn.close()
    ex = np.array(excesses, dtype="float64")
    sh = np.array(sharpes, dtype="float64")

    print(f"\n  RANDOM-STRATEGY CONTROL — {n} never-evolved genomes")
    print("  " + "-" * 62)
    print(f"  profitable against zero (the old gate) : {raw_profit:>4}/{n}  {raw_profit/n:>6.0%}")
    print(f"  beats the null                         : {beats_null:>4}/{n}  {beats_null/n:>6.0%}")
    print(f"  PASSES THE VALIDATION GATE             : {passes_validation:>4}/{n}  "
          f"{passes_validation/n:>6.0%}")
    print()
    verdict = ("GOOD — noise is being filtered" if passes_validation / n < 0.05 else
               "TOO LOOSE — the gate admits noise")
    print(f"  verdict: {verdict}   (target is under 5%)")

    if calibrate:
        print("\n  Calibration — thresholds that would admit under 5% of noise:")
        for label, arr in (("excess P&L (USD)", ex), ("Sharpe", sh)):
            if arr.size:
                print(f"    {label:<20} 95th pct of noise = {np.percentile(arr, 95):>10.3f}"
                      f"   99th = {np.percentile(arr, 99):>10.3f}")
        print("\n  Set the gate above the 95th percentile of these, not at zero.")

    return {"n": n, "passes": passes_validation, "rate": passes_validation / n,
            "p95_excess": float(np.percentile(ex, 95)) if ex.size else 0.0,
            "p95_sharpe": float(np.percentile(sh, 95)) if sh.size else 0.0}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()
    cfg = load_config()
    runtime.be_nice()
    run(cfg, args.n, args.calibrate, args.seed)


if __name__ == "__main__":
    main()
