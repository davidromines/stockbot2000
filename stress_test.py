"""
What would this strategy have earned if the dead companies were still here?

The survivorship gap cannot be closed backwards — we hold 5 tickers that stopped
trading during 2006-2019 against 9,029 the Internet Archive says existed. But it
can be **bounded**. This module puts the missing companies back as an assumption,
prices them at the delisting returns the literature measured, and re-scores. The
output is not a truth. It is a worst case, and a strategy still profitable under
it is one whose edge does not depend on the hole in the data.

The model, stated plainly so it can be argued with:

1. **Not every delisting is a failure.** Roughly half of US delistings are
   mergers and acquisitions, which pay a *premium*. Treating every one as a
   bankruptcy would be as wrong as ignoring them, in the other direction. So a
   delisting is drawn as failure-or-merger, and the failure share rises with how
   far the name has already fallen.
2. **Failures are priced at Shumway's numbers** — the delisting returns measured
   in *The Delisting Bias in CRSP Data* (Journal of Finance, 1997): about -30%
   on NYSE/AMEX and -55% on Nasdaq. This project cannot tell which venue a row
   belongs to at the time of the trade, so it uses the more severe figure. That
   is deliberate: this is a worst case.
3. **Hazard rises with drawdown.** Companies do not fail from their highs. The
   per-year probability of delisting is scaled by the name's fall from its own
   trailing 200-day peak, anchored so the whole-universe rate lands near the
   6-8% a year the US market actually ran at over this period.
4. **Applied per trade, over its own holding period.** A 45-day hold is exposed
   to roughly 45/252 of a year of hazard. Long holds are punished more, correctly.

Every number above is in `config.yaml` under `stress`. They are estimates, and
the point of the tool is to show how much the answer moves when they change —
which is why `--sweep` exists.

**Why these were not recalibrated against our own delisted names (2026-09-12).**
The registry gave us 418 delisted companies we hold prices for, and measuring
their final year looks reassuring: median drawdown of 20% at delisting, a mean
return of **+1.3% over the final 60 trading days**, and a median last traded
price of $17.12. Read directly, that says delistings are nearly harmless and
every parameter here is far too harsh.

That reading would be wrong, and taking it would repeat the exact mistake this
project keeps making. Those 418 are the delisted names that *survived the
survivorship filter* — yfinance retains history for a cleanly acquired company
far more often than for a bankruptcy, so the sample is selected toward benign
delistings, which is why it looks benign. 7,062 delisted companies have no price
data here at all, and they are not missing at random.

So the sample can say something about **mergers** — acquisitions really do delist
near their highs at roughly flat final returns — and nothing trustworthy about
**failures**. The failure figures therefore stay at Shumway's, which were
measured on CRSP, where the whole population is present.

Usage:
    python stress_test.py --stage validation
    python stress_test.py --stage validation --sweep    # sensitivity to the assumptions
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import numpy as np

import bias_exposure as bias
import costs as costs_mod
import genome as gn
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stress")

DEFAULTS = {
    "base_hazard_per_year": 0.06,   # whole-universe delisting rate
    "hazard_at_full_drawdown": 0.45,  # a name 100% off its high, per year
    "failure_share_base": 0.45,     # of delistings, the share that are failures
    "failure_share_deep": 0.90,     # same, for deeply drawn-down names
    "failure_return": -0.55,        # Shumway, Nasdaq — the harsher of the two
    "merger_return": 0.15,          # acquisitions pay a premium
    "draws": 200,
}


def params(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("stress") or {})}


def hazard(dd: np.ndarray, p: dict) -> np.ndarray:
    """Per-year delisting probability as a function of fall from the 200-day high."""
    lo, hi = p["base_hazard_per_year"], p["hazard_at_full_drawdown"]
    return np.clip(lo + (hi - lo) * np.clip(dd, 0.0, 1.0), 0.0, 0.99)


def failure_share(dd: np.ndarray, p: dict) -> np.ndarray:
    """Of the delistings that happen, how many are failures rather than mergers."""
    lo, hi = p["failure_share_base"], p["failure_share_deep"]
    return np.clip(lo + (hi - lo) * np.clip(dd, 0.0, 1.0), 0.0, 1.0)


def stress_pnl(result: dict, dd_all: np.ndarray, p: dict, position_size: float,
               rng) -> np.ndarray:
    """
    One draw of the counterfactual P&L series.

    Each trade is exposed to its own holding period of hazard. Where a delisting
    is drawn, the realised trade return is **replaced** — not adjusted — because
    the company ceased to exist: the strategy did not get the recovery this data
    shows it getting.
    """
    idx = np.asarray(result.get("entry_rows", []), dtype=int)
    pnl = np.asarray(result.get("pnl_series", []), dtype="float64").copy()
    if idx.size == 0 or pnl.size != idx.size:
        return pnl

    dd = dd_all[idx]
    hold_years = max(float(result.get("avg_hold_days", 5.0)), 1.0) / 252.0
    p_delist = 1.0 - np.power(1.0 - hazard(dd, p), hold_years)

    hit = rng.random(idx.size) < p_delist
    if not hit.any():
        return pnl
    failed = rng.random(idx.size) < failure_share(dd, p)
    ret = np.where(failed, p["failure_return"], p["merger_return"])
    pnl[hit] = position_size * ret[hit]
    return pnl


def assess(result: dict, dd_all: np.ndarray, p: dict, position_size: float,
           seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    base = float(result.get("net_pnl_usd", 0.0))
    draws = [float(stress_pnl(result, dd_all, p, position_size, rng).sum())
             for _ in range(int(p["draws"]))]
    a = np.array(draws)
    return {"base": base, "mean": float(a.mean()), "p05": float(np.percentile(a, 5)),
            "p50": float(np.percentile(a, 50)), "survives": float((a > 0).mean())}


def run(cfg: dict, stage: str = "validation", sweep: bool = False, limit: int = 12) -> None:
    p = params(cfg)
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    lab = cfg["lab"]
    window = (lab["search_start"], lab["search_end"])

    rows = conn.execute("""
        SELECT s.id, s.genome, s.entry_desc, e.excess_pnl_usd
        FROM promotions p JOIN strategies s ON s.id = p.strategy_id
        JOIN evaluations e ON e.strategy_id = s.id
        WHERE p.stage = ? AND p.decision = 'pass'
        ORDER BY e.excess_pnl_usd DESC LIMIT ?
    """, (stage, limit)).fetchall()
    if not rows:
        raise SystemExit(f"Nothing has passed {stage}.")

    log.info(f"Loading panel {window[0]} -> {window[1]}")
    df = storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    dd_all = bias.drawdown_column(df)
    panel = simulator.Panel(df)
    del df

    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    max_entries = lab.get("max_entries_per_eval", 20000)

    print(f"\n  SURVIVORSHIP STRESS TEST — the dead companies put back as an assumption")
    print(f"  {int(p['draws'])} draws per strategy. Failures priced at "
          f"{p['failure_return']:+.0%} (Shumway, Nasdaq); mergers at {p['merger_return']:+.0%}.")
    print(f"\n  {'reported':>11}{'stressed':>11}{'5th pct':>11}{'still +ve':>11}  entry rule")
    print("  " + "-" * 104)

    results = []
    for r in rows:
        try:
            g = json.loads(r["genome"])
        except Exception:
            continue
        res = simulator.simulate(g, panel, cm, size, max_entries=max_entries)
        a = assess(res, dd_all, p, size)
        results.append((a, r))
        print(f"  {a['base']:>+11,.0f}{a['mean']:>+11,.0f}{a['p05']:>+11,.0f}"
              f"{a['survives']:>10.0%}   {(r['entry_desc'] or '')[:52]}")

    robust = [x for x in results if x[0]["survives"] >= 0.95]
    print("  " + "-" * 104)
    print(f"  {len(robust)} of {len(results)} stay profitable in at least 95% of draws.")
    print("\n  This is a bound, not a measurement. A strategy that survives it has an "
          "edge that\n  does not depend on the missing companies; one that does not is "
          "indistinguishable\n  from an artifact of their absence, and this data cannot "
          "tell the two apart.")

    if sweep:
        print(f"\n  SENSITIVITY — how much does the answer move with the assumptions?")
        print(f"  {'hazard at full DD':>20}{'failure return':>16}{'median stressed':>18}"
              f"{'still +ve':>11}")
        print("  " + "-" * 66)
        top = results[0] if results else None
        if top:
            res = simulator.simulate(json.loads(top[1]["genome"]), panel, cm, size,
                                     max_entries=max_entries)
            for hz in (0.25, 0.45, 0.65):
                for fr in (-0.30, -0.55, -0.80):
                    q = {**p, "hazard_at_full_drawdown": hz, "failure_return": fr,
                         "draws": 60}
                    a = assess(res, dd_all, q, size)
                    print(f"  {hz:>20.0%}{fr:>16.0%}{a['p50']:>+18,.0f}{a['survives']:>11.0%}")
            print(f"\n  Best strategy by reported excess, across the plausible range of "
                  f"assumptions.\n  If it is positive everywhere the conclusion is robust; "
                  f"if it flips, the\n  reported number was never the finding.")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", default="validation")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    runtime.be_nice()
    run(cfg, args.stage, args.sweep, args.limit)


if __name__ == "__main__":
    main()
