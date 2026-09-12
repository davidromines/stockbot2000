"""
Re-test existing strategies against the synthetic delistings they never saw.

**Why this is safe when evolving on synthetic data would not be.** The
discriminability test says a classifier separates our synthetic rows from real
delisted ones at AUC 0.978 — a generator signature the search would certainly
learn if it were allowed to evolve against these bars. It is not allowed to. The
strategies re-tested here were evolved on real data only and are frozen; they
cannot have exploited a fingerprint that did not exist when they were found. All
the synthetic failures can do to them is take money away.

That asymmetry is the whole licence for this module, and it is why the same data
must never be fed to `evolve.py`.

Each strategy is run against the real panel and then against the real panel plus
each ensemble member, and the result is reported as a **distribution** — the
family, not an average. A strategy that is profitable on real data and loses
across most of the ensemble was living on the absence of the dead.

Usage:
    python retest_synthetic.py --stage validation --members 10
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import numpy as np
import pandas as pd

import benchmark as bench
import costs as costs_mod
import features as feat_mod
import genome as gn
import reward
import simulator
import storage
import synthetic_delistings as sd
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("retest")


def _augmented_panel(conn, cfg, window, member, real_df):
    """Real bars plus one ensemble member's synthetic delistings, indicators computed alike."""
    syn = sd.realise(conn, member, window[0], window[1])
    if syn.empty:
        return None
    parts = []
    for _, g in syn.groupby("ticker", observed=True):
        if len(g) < 210:
            continue
        try:
            parts.append(feat_mod.compute_features_for_ticker(g.reset_index(drop=True)))
        except Exception:
            continue
    if not parts:
        return None
    sf = pd.concat(parts, ignore_index=True)

    mp = cfg["risk"].get("min_price") or 0
    mv = cfg["risk"].get("min_dollar_volume") or 0
    if mp:
        sf = sf[sf["close"] >= mp]
    if mv and "dollar_volume_20" in sf:
        sf = sf[sf["dollar_volume_20"] >= mv]
    # Keep the provenance flag. Intersecting columns with the real frame silently
    # dropped it, so the augmented panel carried synthetic bars that no longer
    # announced themselves — the one property this design promises never to lose.
    cols = [c for c in real_df.columns if c in sf.columns]
    sf = sf[cols + (["synthetic"] if "synthetic" in sf.columns else [])].dropna(
        subset=[c for c in ("close", "date", "ticker") if c in cols])
    real_tagged = real_df[cols].copy()
    real_tagged["synthetic"] = 0
    if "synthetic" not in sf.columns:
        sf["synthetic"] = 1
    both = pd.concat([real_tagged, sf], ignore_index=True)
    both = both.sort_values(["ticker", "date"]).reset_index(drop=True)
    return both


def run(cfg, stage="validation", members=10, limit=12):
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    lab = cfg["lab"]
    window = (lab["search_start"], lab["search_end"])

    rows = conn.execute("""
        SELECT s.id, s.genome, s.entry_desc, e.excess_pnl_usd, e.net_pnl_usd
        FROM promotions p JOIN strategies s ON s.id = p.strategy_id
        JOIN evaluations e ON e.strategy_id = s.id
        WHERE p.stage=? AND p.decision='pass' ORDER BY e.excess_pnl_usd DESC LIMIT ?
    """, (stage, limit)).fetchall()
    if not rows:
        raise SystemExit(f"Nothing has passed {stage}.")

    log.info(f"Loading the real panel {window[0]} -> {window[1]}")
    real = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True)
    real = real.sort_values(["ticker", "date"]).reset_index(drop=True)

    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    cap = size * cfg["risk"]["max_open_positions"]
    rp = reward.params_from_config(cfg)
    me = lab.get("max_entries_per_eval", 20000)

    base_panel = simulator.Panel(real)
    surface = bench.null_surface(conn, cfg, window)
    genomes = []
    for r in rows:
        try:
            genomes.append((r, json.loads(r["genome"])))
        except Exception:
            pass

    log.info(f"Baseline on real data for {len(genomes)} strategies")
    base = {}
    for r, g in genomes:
        res = simulator.simulate(g, base_panel, cm, size, max_entries=me)
        sc = reward.fitness(res, gn.complexity(g), capital_usd=cap,
                            benchmark_surface=surface, position_size_usd=size, cfg=rp)
        base[r["id"]] = sc["net_pnl_usd"]
    del base_panel

    results = {r["id"]: [] for r, _ in genomes}
    for m in range(members):
        aug = _augmented_panel(conn, cfg, window, m, real)
        if aug is None:
            continue
        panel = simulator.Panel(aug)
        nsyn = int(aug["synthetic"].sum()) if "synthetic" in aug else 0
        log.info(f"  member {m}: panel {panel.n:,} rows ({nsyn:,} synthetic)")
        for r, g in genomes:
            res = simulator.simulate(g, panel, cm, size, max_entries=me)
            sc = reward.fitness(res, gn.complexity(g), capital_usd=cap,
                                benchmark_surface=surface, position_size_usd=size, cfg=rp)
            results[r["id"]].append(sc["net_pnl_usd"])
        del panel, aug

    print(f"\n  RE-TEST AGAINST THE SYNTHETIC DELISTING ENSEMBLE — {members} members")
    print(f"  {'real':>11}{'ens.median':>12}{'ens.worst':>11}{'% loss':>9}"
          f"{'still +ve':>11}  entry rule")
    print("  " + "-" * 106)
    survived = 0
    for r, _ in genomes:
        v = np.array(results[r["id"]], dtype="float64")
        if v.size == 0:
            continue
        b = base[r["id"]]
        med = float(np.median(v)); worst = float(v.min())
        drop = (b - med) / abs(b) if b else 0.0
        pos = float((v > 0).mean())
        survived += pos >= 0.95
        print(f"  {b:>+11,.0f}{med:>+12,.0f}{worst:>+11,.0f}{drop:>8.0%}"
              f"{pos:>11.0%}  {(r['entry_desc'] or '')[:42]}")
    print("  " + "-" * 106)
    print(f"  {survived} of {len(genomes)} stay profitable across 95%+ of the ensemble.")
    print("\n  These strategies were evolved on real data and never saw a synthetic bar,")
    print("  so they cannot have gamed the generator — the ensemble can only take money")
    print("  from them. A large drop means the strategy was living on the absence of")
    print("  the dead.")
    print("\n  READ A SMALL DROP WITH CARE. Measured 2026-09-12: the crash-buying")
    print("  survivors took only 8-18% damage, and not because they dodged the")
    print("  synthetic failures — 23.5% of their entries landed in them, slightly MORE")
    print("  than the 19.9% those names make up of the panel. They survived because a")
    print("  60-day holding cap and an ATR stop exit a dying company at -10 or -20%")
    print("  long before it reaches zero.")
    print("\n  That is only true while the decline is smooth enough for a stop to fill,")
    print("  and these paths are. Real bankruptcies gap: the position opens through the")
    print("  stop with no liquidity behind it, which is a limitation this project already")
    print("  documents for live trading and which the generator under-represents. The")
    print("  honest reading is that this ensemble tests slow death well and sudden death")
    print("  badly.")
    conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="validation")
    ap.add_argument("--members", type=int, default=10)
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    run(cfg, a.stage, a.members, a.limit)


if __name__ == "__main__":
    main()
