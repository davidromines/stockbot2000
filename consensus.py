"""
Build ONE strategy from what 455 survivors agree on, and test it once.

THE PROBLEM THIS SOLVES
-----------------------
A million trials produced 455 validation survivors. Picking the best of them is
worthless: the best of N noise trials shows about sqrt(2 ln N) standard errors of
apparent skill by chance, which at N = 1,022,905 is 5.26 SE. The median survivor
Sharpe is 1.114. Selecting a champion from that pile is the multiple-testing trap
this project has already fallen into four times.

**But the consensus is not a selection.** If 85% of structurally distinct
survivors independently contain the same two ideas, that agreement is a single
hypothesis about the market, not the winner of a lottery. One hypothesis tested
once carries no multiple-testing penalty at all.

So: extract the modal terms, take the median threshold for each, assemble one
rule, WRITE IT DOWN, and only then run it on data the survivors were never
selected on.

THE DISCIPLINE THAT MAKES IT VALID
-----------------------------------
The consensus is derived from SEARCH-WINDOW survivors only. The validation
window is then genuinely out of sample for it — not because the rule has never
seen those dates, but because nothing about the rule was chosen using them.

**The rule is written to disk before it is scored.** `--derive` produces
`data/consensus_strategy.json` and stops. `--test` reads that file and scores
it. Deriving and testing in one pass would let a disappointing result quietly
become a reason to re-derive, which is how pre-registration dies.

WHAT IT CANNOT FIX
------------------
Consensus among survivors of a biased sample is consensus about the bias. Every
one of these rules was found on data missing 7,062 delisted companies. If that
absence favours a particular shape, 455 searches will agree on it enthusiastically
and be 455 times as wrong. Forward paper trading is the only answer to that, and
it is why `--open-fund` exists.

Usage:
    python consensus.py --derive        # extract and WRITE the hypothesis
    python consensus.py --show
    python consensus.py --test          # score it, once, out of sample
    python consensus.py --open-fund     # run it forward
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import re
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consensus")

SPEC = Path("data/consensus_strategy.json")
GATE_DATE = "2026-09-19"      # survivors from after the gate raise and fill fix

# Terms parsed out of an entry description. Each is (name, regex capturing the
# threshold). Deliberately a small vocabulary: the point is to find what the
# survivors agree on, not to reconstruct any individual rule faithfully.
TERMS = {
    "rank_price_above_sma50":  r"rank\(price_above_sma50\)\s*>\s*([\d.]+)",
    "rank_price_above_sma200": r"rank\(price_above_sma200\)\s*>\s*([\d.]+)",
    "rank_macd":               r"rank\(macd\)\s*>\s*([\d.]+)",
    "rank_rsi":                r"rank\(rsi_14\)\s*>\s*([\d.]+)",
    "rsi_oversold":            r"rsi_14\s*<\s*([\d.]+)",
    "below_sma200":            r"price_above_sma200\s*<\s*([\d.]+)",
    "drawdown_200":            r"drawdown_200\s*>\s*([\d.]+)",
    "off_52w_low":             r"pct_off_52w_low\s*<\s*([\d.]+)",
    "atr":                     r"atr_14\s*>\s*([\d.]+)",
}


def survivors(conn, since: str = GATE_DATE) -> list:
    return [dict(r) for r in conn.execute("""
        SELECT s.entry_desc, s.genome, e.excess_pnl_usd, e.sharpe, e.n_trades,
               json_extract(s.genome,'$.risk.stop_atr_multiple') AS stop_mult,
               json_extract(s.genome,'$.risk.max_hold_days') AS hold
        FROM promotions p
        JOIN strategies s ON s.id = p.strategy_id
        JOIN lab_runs r ON r.run_id = s.run_id
        LEFT JOIN evaluations e ON e.strategy_id = s.id
        WHERE p.stage='validation' AND p.decision='pass'
          AND r.started_at >= ? AND s.entry_desc IS NOT NULL""", (since,))]


def derive(rows: list, min_share: float = 0.5) -> dict:
    """
    The modal terms and their median thresholds.

    `min_share` is the bar for inclusion: a term must appear in at least this
    fraction of survivors. Set at 0.5 so a term has to be in the MAJORITY, not
    merely common — a 20% term is a minority opinion, and including it would be
    reading the pile rather than its consensus.

    Medians, not means: thresholds are bounded and skewed, and one survivor with
    an extreme constant should not drag the consensus.
    """
    n = len(rows)
    hits, vals = Counter(), {}
    for r in rows:
        d = r["entry_desc"] or ""
        for name, pat in TERMS.items():
            m = re.search(pat, d, re.I)
            if m:
                hits[name] += 1
                vals.setdefault(name, []).append(float(m.group(1)))

    chosen = {}
    for name, c in hits.items():
        share = c / n
        if share >= min_share:
            chosen[name] = {"share": round(share, 3), "n": c,
                            "threshold": round(float(np.median(vals[name])), 4),
                            "iqr": [round(float(np.percentile(vals[name], 25)), 4),
                                    round(float(np.percentile(vals[name], 75)), 4)]}

    stops = [float(r["stop_mult"]) for r in rows if r.get("stop_mult")]
    holds = [int(r["hold"]) for r in rows if r.get("hold")]
    return {
        "derived_on": date.today().isoformat(),
        "derived_from": {"survivors": n, "since": GATE_DATE,
                         "min_share": min_share},
        "terms": chosen,
        "rejected_terms": {k: round(v / n, 3) for k, v in hits.items()
                           if v / n < min_share},
        "risk": {"stop_atr_multiple": round(float(np.median(stops)), 2) if stops else 3.0,
                 "stop_iqr": [round(float(np.percentile(stops, 25)), 2),
                              round(float(np.percentile(stops, 75)), 2)] if stops else None,
                 "max_hold_days": int(np.median(holds)) if holds else 20},
    }


def to_genome(spec: dict) -> dict:
    """Assemble the consensus terms into one entry tree, ANDed together."""
    t = spec["terms"]
    clauses = []
    if "rank_price_above_sma50" in t:
        clauses.append({"op": "gt", "args": [
            {"op": "rank", "args": [{"col": "price_above_sma50"}]},
            {"const": t["rank_price_above_sma50"]["threshold"]}]})
    if "rank_price_above_sma200" in t:
        clauses.append({"op": "gt", "args": [
            {"op": "rank", "args": [{"col": "price_above_sma200"}]},
            {"const": t["rank_price_above_sma200"]["threshold"]}]})
    if "rank_macd" in t:
        clauses.append({"op": "gt", "args": [
            {"op": "rank", "args": [{"col": "macd"}]},
            {"const": t["rank_macd"]["threshold"]}]})
    if "rank_rsi" in t:
        clauses.append({"op": "gt", "args": [
            {"op": "rank", "args": [{"col": "rsi_14"}]},
            {"const": t["rank_rsi"]["threshold"]}]})
    if "rsi_oversold" in t:
        clauses.append({"op": "lt", "args": [
            {"col": "rsi_14"}, {"const": t["rsi_oversold"]["threshold"]}]})
    if "below_sma200" in t:
        clauses.append({"op": "lt", "args": [
            {"col": "price_above_sma200"}, {"const": t["below_sma200"]["threshold"]}]})
    if "drawdown_200" in t:
        clauses.append({"op": "gt", "args": [
            {"col": "drawdown_200"}, {"const": t["drawdown_200"]["threshold"]}]})
    if not clauses:
        raise SystemExit("no term reached the majority bar — there is no consensus "
                         "to test, which is itself the finding")
    entry = clauses[0]
    for c in clauses[1:]:
        entry = {"op": "and", "args": [entry, c]}
    return {"entry": entry,
            "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0.0}]},
            "risk": {"max_hold_days": spec["risk"]["max_hold_days"],
                     "stop_atr_multiple": spec["risk"]["stop_atr_multiple"]}}


def describe(spec: dict) -> str:
    import genome as gn
    g = to_genome(spec)
    L = [f"CONSENSUS STRATEGY   derived {spec['derived_on']} from "
         f"{spec['derived_from']['survivors']} survivors",
         "  " + "-" * 68,
         f"  entry: {gn.describe(g['entry'])}",
         f"  stop:  {spec['risk']['stop_atr_multiple']} ATR"
         f"   hold: {spec['risk']['max_hold_days']}d", "",
         "  terms that reached the majority bar:"]
    for k, v in sorted(spec["terms"].items(), key=lambda kv: -kv[1]["share"]):
        L.append(f"    {k:<26}{v['share']*100:>5.0f}% of survivors   "
                 f"median {v['threshold']:<9} IQR {v['iqr']}")
    if spec.get("rejected_terms"):
        L.append("  terms that did NOT (minority opinions, excluded):")
        for k, v in sorted(spec["rejected_terms"].items(), key=lambda kv: -kv[1])[:6]:
            L.append(f"    {k:<26}{v*100:>5.0f}%")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--derive", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--open-fund", action="store_true")
    ap.add_argument("--min-share", type=float, default=0.5)
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.derive:
        rows = survivors(conn)
        if not rows:
            raise SystemExit("no survivors since the gate change")
        spec = derive(rows, a.min_share)
        if SPEC.exists():
            # Re-deriving after seeing a test result is how pre-registration
            # dies. It is still allowed, but it is loud and it is dated.
            prior = json.loads(SPEC.read_text())
            log.warning(f"OVERWRITING a hypothesis derived {prior['derived_on']}. "
                        f"If it has already been tested, this is no longer "
                        f"pre-registered and the result must be reported as such.")
        SPEC.write_text(json.dumps(spec, indent=2))
        print(describe(spec))
        print(f"\n  written to {SPEC}")
        print("  NOT scored. Run --test to spend the out-of-sample window on it.")
        conn.close(); return

    if not SPEC.exists():
        raise SystemExit("no hypothesis on disk. Run --derive first.")
    spec = json.loads(SPEC.read_text())

    if a.show:
        print(describe(spec))
    if a.test:
        import benchmark as bench, costs as costs_mod, reward, simulator
        from train_model import FEATURE_COLS
        g = to_genome(spec)
        cm = costs_mod.CostModel(cfg)
        size = float(cfg["risk"]["position_size_usd"])
        for label, win in (("SEARCH (in sample — expected to look good)",
                            (cfg["lab"]["search_start"], cfg["lab"]["search_end"])),
                           ("VALIDATION (out of sample — the real test)",
                            (cfg["lab"]["validation_start"], cfg["lab"]["validation_end"]))):
            df = storage.load_training_frame(
                conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
                start_date=win[0], end_date=win[1],
                min_price=cfg["risk"].get("min_price"),
                min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
                include_liquidity=True, include_open=True)
            if df.empty:
                continue
            px = storage.load_exit_prices(conn, df["ticker"].astype(str).unique(),
                                          win[0], "2099-12-31")
            panel = simulator.Panel(df, exit_prices=px)
            r = simulator.simulate(g, panel, cm, size, max_entries=20000)
            surf = bench.null_surface(conn, cfg, win)
            f = reward.fitness(r, complexity=len(spec["terms"]) * 3,
                               position_size_usd=size, benchmark_surface=surf,
                               cfg=reward.params_from_config(cfg))
            gate = float(cfg["lab"]["gates"]["min_excess_pnl_usd"])
            print(f"\n  {label}  {win[0]} -> {win[1]}")
            print(f"    trades {r['n_trades']:,}   net ${r['net_pnl_usd']:,.0f}   "
                  f"excess ${f['excess_pnl_usd']:,.0f}   win {r['win_rate']*100:.1f}%")
            print(f"    gate ${gate:,.0f}  ->  "
                  f"{'CLEARS' if f['excess_pnl_usd'] > gate else 'FAILS'}")
    conn.close()


if __name__ == "__main__":
    main()
