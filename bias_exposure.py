"""
How much does a strategy depend on companies that are missing from this database?

The survivorship haircut in `config.yaml` is a flat ~10 points a year applied to
everything. That is the right shape for a strategy that buys the market and the
wrong shape for every strategy this Lab actually finds, because **the bias is not
uniform and the search preferentially discovers the strategies that concentrate
it.** A haircut cannot fix a measurement the strategy was selected to exploit.

The concrete case that prompted this module. After the price-filter and dead-branch
fixes, the search's one surviving idea was:

    pct_change(sma_200, 10) < -0.0818      "buy when the 200-day average collapses"

Buy the crash. Measured against our own data: **5 tickers stopped trading during
the entire 2006-2019 search window**, against 9,029 companies the Internet Archive
says existed and we do not hold. So every crash this rule bought recovered, by
construction — not because crashes recover, but because the ones that did not are
absent. The losing half of the distribution is not understated here. It is gone.

What this measures: the share of a strategy's entries taken in names that are
deep below their own recent high. Those are the rows where the missing companies
would have been, so a strategy concentrated there is untestable on this data at
any haircut. It is an **exposure** measure, not a correction — there is nothing
to correct with.

Reported as a fraction of trades, and used as a promotion gate. A strategy over
`survivorship.max_drawdown_exposure` is refused rather than discounted, because a
number we cannot compute is not improved by multiplying it.

Usage:
    python bias_exposure.py --stage validation     # score everything that passed
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import numpy as np

import costs as costs_mod
import genome as gn
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bias_exposure")

DEEP = 0.30          # "deep below its own high" — 30% off the 200-day peak
LOOKBACK = 200


def drawdown_column(df) -> np.ndarray:
    """
    Each row's fall from its own trailing 200-day high, as a positive fraction.

    Computed per ticker, so it never sees another name's prices. This is the
    variable that decides whether a row is one where a delisting would plausibly
    have happened: companies do not go bankrupt from their highs.
    """
    peak = (df.groupby("ticker", observed=True)["close"]
              .transform(lambda s: s.rolling(LOOKBACK, min_periods=20).max()))
    dd = 1.0 - (df["close"].to_numpy() / peak.to_numpy())
    return np.nan_to_num(dd, nan=0.0, posinf=0.0, neginf=0.0)


def exposure(result: dict, dd: np.ndarray, deep: float = DEEP) -> dict:
    """
    The share of a strategy's entries taken in deeply drawn-down names.

    `entry_rows` indexes the panel, so this is the strategy's *actual* trades,
    not an approximation of what its rule might do.
    """
    idx = np.asarray(result.get("entry_rows", []), dtype=int)
    if idx.size == 0:
        return {"n": 0, "share_deep": 0.0, "mean_drawdown": 0.0, "share_severe": 0.0}
    d = dd[idx]
    return {"n": int(idx.size),
            "share_deep": float((d >= deep).mean()),
            "share_severe": float((d >= 0.60).mean()),
            "mean_drawdown": float(d.mean())}


def verdict(share_deep: float, limit: float) -> str:
    if share_deep >= limit:
        return "REFUSE — untestable on this data"
    if share_deep >= limit * 0.6:
        return "caution"
    return "ok"


def score_stage(cfg: dict, stage: str = "validation") -> list[dict]:
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    lab = cfg["lab"]
    window = (lab["search_start"], lab["search_end"])
    limit = float(cfg.get("survivorship", {}).get("max_drawdown_exposure", 0.35))

    rows = conn.execute("""
        SELECT s.id, s.genome, s.entry_desc, e.excess_pnl_usd, e.sharpe
        FROM promotions p JOIN strategies s ON s.id = p.strategy_id
        JOIN evaluations e ON e.strategy_id = s.id
        WHERE p.stage = ? AND p.decision = 'pass'
        ORDER BY e.excess_pnl_usd DESC
    """, (stage,)).fetchall()
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
    dd = drawdown_column(df)
    panel = simulator.Panel(df)
    del df

    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    max_entries = lab.get("max_entries_per_eval", 20000)

    print(f"\n  SURVIVORSHIP EXPOSURE — {stage} survivors, entries scored on "
          f"{window[0]} to {window[1]}")
    print(f"  {'excess':>9}{'>30% off':>10}{'>60% off':>10}{'mean DD':>9}  "
          f"{'verdict':<34} entry rule")
    print("  " + "-" * 118)

    out = []
    for r in rows:
        try:
            g = json.loads(r["genome"])
        except Exception:
            continue
        res = simulator.simulate(g, panel, cm, size, max_entries=max_entries)
        ex = exposure(res, dd)
        v = verdict(ex["share_deep"], limit)
        out.append({**ex, "id": r["id"], "verdict": v,
                    "excess": r["excess_pnl_usd"], "desc": r["entry_desc"]})
        print(f"  {(r['excess_pnl_usd'] or 0):>+9,.0f}{ex['share_deep']:>10.0%}"
              f"{ex['share_severe']:>10.0%}{ex['mean_drawdown']:>9.0%}  {v:<34} "
              f"{(r['entry_desc'] or '')[:44]}")

    refused = sum(1 for o in out if o["verdict"].startswith("REFUSE"))
    base = float((dd >= DEEP).mean()) if dd.size else 0.0
    print("  " + "-" * 118)
    print(f"  Baseline: {base:.0%} of all tradeable rows are more than 30% off their "
          f"own 200-day high.")
    print(f"  {refused} of {len(out)} concentrate the bias past the "
          f"{limit:.0%} limit and are refused promotion.")
    print("\n  Refused is not 'probably wrong'. It is 'this data cannot answer the "
          "question':\n  5 tickers stopped trading in the whole 2006-2019 window, "
          "against 9,029 companies\n  the Internet Archive says existed. Paper "
          "trading is the only test left for these.")
    conn.close()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", default="validation")
    args = parser.parse_args()
    cfg = load_config()
    runtime.be_nice()
    score_stage(cfg, args.stage)


if __name__ == "__main__":
    main()
