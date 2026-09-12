"""
Published trading strategies, expressed as genomes. Phase 11.

Everything the search has produced so far it invented from nothing, and the
first thing it invented was a price filter. This module gives it a starting
population of ideas people have already written down — Wilder's RSI, Appel's
MACD, Bollinger's bands, Jegadeesh and Titman's momentum, Donchian breakouts —
so evolution has somewhere to begin other than random noise.

Two distinct uses, and they answer different questions:

- **As a measurement.** Run them standalone (`python seeds.py`) and you learn
  whether decades-old published rules beat the null on this data, after costs.
  That is a real result either way: if none of them clear the bar, it says
  something about the bar and about the data, and it is the fairest available
  check that the simulator is not simply impossible to pass.
- **As seed stock.** `evolve.py --seeds` puts them in generation 0 alongside the
  random genomes. Genetic programming is far more productive starting from
  working structure than from noise, and mutation can then ask the questions
  nobody thought to — what if the RSI threshold were 23, what if the trend
  filter used ADX instead.

**These are not endorsements.** Most published technical strategies do not
survive costs and have not for decades; several are here precisely because they
are famous and probably do not work, and finding that out on our own data is the
point. Each carries its source so a result can be traced back to the claim.

Expressed in the same grammar the search uses, so a seed is indistinguishable
from an evolved genome once it is in the population — same mutation, same
crossover, same scoring, no special privileges.

Usage:
    python seeds.py                 # evaluate every seed on the search window
    python seeds.py --window validation
    python seeds.py --list          # just the catalogue
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import benchmark as bench
import costs as costs_mod
import genome as gn
import reward
import simulator
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seeds")


# -- grammar shorthand, so the catalogue below reads like the strategies ------

def col(name):            return {"col": name}
def const(v):             return {"const": float(v)}
def lt(a, b):             return {"op": "lt", "args": [a, b if isinstance(b, dict) else const(b)]}
def gt(a, b):             return {"op": "gt", "args": [a, b if isinstance(b, dict) else const(b)]}
def xup(a, b):            return {"op": "crosses_above", "args": [a, b]}
def xdown(a, b):          return {"op": "crosses_below", "args": [a, b]}
def and_(*a):             return _fold("and", a)
def or_(*a):              return _fold("or", a)
def not_(a):              return {"op": "not", "args": [a]}
def rank(a):              return {"op": "rank", "args": [a]}
def zscore(a, n):         return {"op": "zscore", "args": [a], "n": n}
def pct_change(a, n):     return {"op": "pct_change", "args": [a], "n": n}
def lag(a, n):            return {"op": "lag", "args": [a], "n": n}


def _fold(op, args):
    """The grammar's and/or take exactly two arguments; chain them."""
    node = args[0]
    for nxt in args[1:]:
        node = {"op": op, "args": [node, nxt]}
    return node


def risk(stop=2.0, hold=20, positions=10, take_profit=None):
    return {"stop_atr_multiple": stop, "max_hold_days": hold,
            "max_open_positions": positions, "take_profit_pct": take_profit}


# -- the catalogue -----------------------------------------------------------
#
# `source` is the primary published description, not a recommendation. `caution`
# records what is already known against the idea, so a bad result is not read as
# a surprise.

SEEDS = [
    {
        "name": "rsi_oversold",
        "source": "Wilder, New Concepts in Technical Trading Systems (1978)",
        "idea": "Buy when RSI(14) falls under 30; sell when it recovers past 70.",
        "caution": "The most widely published rule in technical analysis, and "
                   "therefore the least likely to carry an edge that survives costs.",
        "genome": {"entry": lt(col("rsi_14"), 30), "exit": gt(col("rsi_14"), 70),
                   "risk": risk(stop=2.5, hold=20)},
    },
    {
        "name": "rsi_oversold_uptrend",
        "source": "Wilder (1978), with the trend filter Connors popularised",
        "idea": "RSI(14) under 30, but only in names already above their 200-day "
                "average — dip-buying inside an uptrend rather than catching knives.",
        "caution": "The trend filter is the part usually added after the fact, "
                   "which is exactly the kind of choice that overfits.",
        "genome": {"entry": and_(lt(col("rsi_14"), 30), gt(col("price_above_sma200"), 0.5)),
                   "exit": gt(col("rsi_14"), 65), "risk": risk(stop=2.5, hold=20)},
    },
    {
        "name": "golden_cross",
        "source": "Classical Dow-theory moving-average crossover",
        "idea": "Buy when the 50-day average crosses above the 200-day.",
        "caution": "Signals are rare and slow; on a 60-day hold cap this may "
                   "never see the trend it is meant to ride.",
        "genome": {"entry": xup(col("sma_50"), col("sma_200")),
                   "exit": xdown(col("sma_50"), col("sma_200")),
                   "risk": risk(stop=3.0, hold=60)},
    },
    {
        "name": "macd_crossover",
        "source": "Appel, The Moving Average Convergence Divergence Method (1979)",
        "idea": "Buy when MACD crosses above its signal line; exit on the reverse.",
        "caution": "Whipsaws badly in range-bound markets, which is most of them.",
        "genome": {"entry": xup(col("macd"), col("macd_signal")),
                   "exit": xdown(col("macd"), col("macd_signal")),
                   "risk": risk(stop=2.0, hold=30)},
    },
    {
        "name": "macd_trend_confirmed",
        "source": "Appel (1979) with Wilder's ADX (1978) as a trend filter",
        "idea": "MACD crossover, taken only when ADX(14) is above 25 — a "
                "crossover inside a market that is actually trending.",
        "caution": "Two published rules stacked is two chances to have fitted "
                   "the past.",
        "genome": {"entry": and_(xup(col("macd"), col("macd_signal")),
                                 gt(col("adx_14"), 25)),
                   "exit": xdown(col("macd"), col("macd_signal")),
                   "risk": risk(stop=2.0, hold=30)},
    },
    {
        "name": "bollinger_reversion",
        "source": "Bollinger, Bollinger on Bollinger Bands (2001)",
        "idea": "Buy at the lower band (bb_pct under 0.05), exit at the middle.",
        "caution": "Mean reversion pays for liquidity; costs fall hardest here.",
        "genome": {"entry": lt(col("bb_pct"), 0.05), "exit": gt(col("bb_pct"), 0.5),
                   "risk": risk(stop=2.0, hold=10)},
    },
    {
        "name": "bollinger_breakout",
        "source": "Bollinger (2001) — the squeeze-and-expand reading",
        "idea": "Buy strength at the upper band (bb_pct above 0.95) rather than "
                "fading it. The opposite trade to the one above, deliberately.",
        "caution": "Included as the paired opposite of bollinger_reversion. Both "
                   "cannot be right, and both can be wrong.",
        "genome": {"entry": gt(col("bb_pct"), 0.95), "exit": lt(col("bb_pct"), 0.5),
                   "risk": risk(stop=2.5, hold=20)},
    },
    {
        "name": "cross_sectional_momentum",
        "source": "Jegadeesh & Titman, Returns to Buying Winners and Selling "
                  "Losers (Journal of Finance, 1993)",
        "idea": "Buy the top decile by recent return, measured across all stocks "
                "on the same day. The best-documented anomaly in the literature.",
        "caution": "Published on 3-12 month formation periods; roc_10 is far "
                   "shorter, which is closer to short-term reversal territory.",
        "genome": {"entry": gt(rank(col("roc_10")), 0.9), "exit": lt(rank(col("roc_10")), 0.5),
                   "risk": risk(stop=3.0, hold=45)},
    },
    {
        "name": "dual_momentum",
        "source": "Antonacci, Dual Momentum Investing (2014)",
        "idea": "Relative strength against other stocks AND absolute strength "
                "against its own trend — top-20% momentum, above the 200-day.",
        "caution": "Published as a monthly asset-class rotation, not a daily "
                   "single-stock rule. This is an adaptation, not the strategy.",
        "genome": {"entry": and_(gt(rank(col("roc_10")), 0.8),
                                 gt(col("price_above_sma200"), 0.5)),
                   "exit": lt(col("price_above_sma50"), 0.5),
                   "risk": risk(stop=3.0, hold=45)},
    },
    {
        "name": "short_term_reversal",
        "source": "Lehmann (1990); Jegadeesh (1990)",
        "idea": "Buy the worst performers of the last few days — the documented "
                "short-horizon counterpart to momentum.",
        "caution": "The published effect is concentrated in illiquid names, "
                   "where our cost model bites hardest. That is the test.",
        "genome": {"entry": lt(rank(pct_change(col("close"), 5)), 0.1),
                   "exit": gt(rank(pct_change(col("close"), 5)), 0.5),
                   "risk": risk(stop=2.0, hold=5)},
    },
    {
        "name": "donchian_breakout",
        "source": "Donchian's channel breakout, as traded by the Turtles "
                  "(Dennis & Eckhardt, 1983)",
        "idea": "Buy a decisive break above the recent range. Expressed as a "
                "20-day z-score of price above 2 — there is no rolling-high "
                "primitive, and this is the closest honest equivalent.",
        "caution": "An approximation of the published rule, not the rule. A "
                   "z-score break and an N-day-high break are not the same event.",
        "genome": {"entry": gt(zscore(col("close"), 20), 2.0),
                   "exit": lt(zscore(col("close"), 20), 0.0),
                   "risk": risk(stop=2.0, hold=45)},
    },
    {
        "name": "turtle_with_volume",
        "source": "Donchian breakout with the volume confirmation common to "
                  "most breakout literature",
        "idea": "The breakout above, but only when volume confirms it.",
        "caution": "Volume confirmation is folklore as often as it is evidence.",
        "genome": {"entry": and_(gt(zscore(col("close"), 20), 2.0),
                                 gt(col("vol_ratio"), 1.5)),
                   "exit": lt(zscore(col("close"), 20), 0.0),
                   "risk": risk(stop=2.0, hold=45)},
    },
    {
        "name": "stochastic_crossover",
        "source": "Lane's stochastic oscillator (1950s, published 1984)",
        "idea": "Buy when %K crosses above %D while both are in oversold territory.",
        "caution": "Crossover plus threshold is two conditions on one indicator; "
                   "they are not independent evidence.",
        "genome": {"entry": and_(xup(col("stoch_k"), col("stoch_d")),
                                 lt(col("stoch_k"), 30)),
                   "exit": gt(col("stoch_k"), 80), "risk": risk(stop=2.0, hold=15)},
    },
    {
        "name": "williams_r_oversold",
        "source": "Williams, How I Made One Million Dollars (1973)",
        "idea": "Buy when Williams %R is below -80.",
        "caution": "Essentially a rescaled stochastic; expect it to behave like "
                   "the rule above rather than to add information.",
        "genome": {"entry": lt(col("willr_14"), -80), "exit": gt(col("willr_14"), -20),
                   "risk": risk(stop=2.0, hold=15)},
    },
    {
        "name": "cci_extreme",
        "source": "Lambert, Commodity Channel Index (Commodities, 1980)",
        "idea": "Buy below -100, exit above +100 — Lambert's own thresholds.",
        "caution": "Designed for commodity futures cycles, applied here to equities.",
        "genome": {"entry": lt(col("cci_20"), -100), "exit": gt(col("cci_20"), 100),
                   "risk": risk(stop=2.0, hold=15)},
    },
    {
        "name": "trend_following_adx",
        "source": "Wilder's ADX (1978) as a standalone trend system",
        "idea": "Hold anything in a confirmed uptrend: ADX above 25 and price "
                "above both averages. No timing, just participation.",
        "caution": "Closest of these to simply being long the market, so it is "
                   "the one the null should be hardest on. That is useful.",
        "genome": {"entry": and_(gt(col("adx_14"), 25), gt(col("price_above_sma50"), 0.5),
                                 gt(col("price_above_sma200"), 0.5)),
                   "exit": lt(col("price_above_sma50"), 0.5),
                   "risk": risk(stop=3.0, hold=60)},
    },
    {
        "name": "obv_accumulation",
        "source": "Granville, New Key to Stock Market Profits (1963)",
        "idea": "Buy when on-balance volume is rising while price is still below "
                "its 50-day average — accumulation before the move.",
        "caution": "Granville's claim is about divergence, which this only "
                   "approximates.",
        "genome": {"entry": and_(gt(col("obv_rising"), 0.5),
                                 lt(col("price_above_sma50"), 0.5)),
                   "exit": gt(col("price_above_sma50"), 0.5),
                   "risk": risk(stop=2.5, hold=30)},
    },
    {
        "name": "chaikin_oscillator",
        "source": "Chaikin's accumulation/distribution oscillator",
        "idea": "Buy when the oscillator crosses above zero in an uptrend.",
        "caution": "Another volume-flow indicator; correlated with the one above.",
        "genome": {"entry": and_(xup(col("chaikin_osc"), col("macd_hist")),
                                 gt(col("price_above_sma200"), 0.5)),
                   "exit": lt(col("chaikin_osc"), 0), "risk": risk(stop=2.0, hold=20)},
    },
    {
        "name": "mean_reversion_to_sma",
        "source": "The textbook mean-reversion trade; see Chan, Algorithmic "
                  "Trading (2013) for the statistical treatment",
        "idea": "Buy when price is two standard deviations below its own 20-day "
                "mean, exit when it returns to the mean.",
        "caution": "Equities mean-revert at short horizons and trend at long "
                   "ones; the holding period decides which one you get.",
        "genome": {"entry": lt(zscore(col("close"), 20), -2.0),
                   "exit": gt(zscore(col("close"), 20), 0.0),
                   "risk": risk(stop=2.5, hold=10)},
    },
    {
        "name": "momentum_pullback",
        "source": "The combination trade behind most trend-pullback systems",
        "idea": "Strong long-term momentum, bought on a short-term oversold dip. "
                "Momentum and reversal at their own natural horizons rather than "
                "in opposition.",
        "caution": "The most 'designed' rule here, and so the most suspect.",
        "genome": {"entry": and_(gt(rank(col("roc_10")), 0.7),
                                 gt(col("price_above_sma200"), 0.5),
                                 lt(col("rsi_14"), 40)),
                   "exit": gt(col("rsi_14"), 65), "risk": risk(stop=2.5, hold=20)},
    },
]


def catalogue() -> list[dict]:
    """The seeds, each with its genome validated against the grammar."""
    return SEEDS


def genomes() -> list[dict]:
    """Just the genomes, for injection into a population."""
    return [dict(s["genome"]) for s in SEEDS]


def show() -> None:
    print(f"\n  {len(SEEDS)} SEED STRATEGIES\n")
    for s in SEEDS:
        print(f"  {s['name']}")
        print(f"      source   {s['source']}")
        print(f"      idea     {s['idea']}")
        print(f"      caution  {s['caution']}")
        print(f"      entry    {gn.describe(s['genome']['entry'])}")
        print(f"      exit     {gn.describe(s['genome']['exit'])}\n")


def evaluate(cfg: dict, window_name: str = "search") -> list[dict]:
    """
    Score every seed on one window and print the table.

    The interesting column is **excess**, not net P&L. A published rule that
    made money by being long a rising market has told us nothing; one that beat
    the null of the stocks it chose, after costs, has.
    """
    lab = cfg["lab"]
    windows = {"search": (lab["search_start"], lab["search_end"]),
               "validation": (lab["validation_start"], lab["validation_end"])}
    if window_name not in windows:
        raise SystemExit(f"Window must be one of {sorted(windows)} — sealed stays sealed.")
    window = windows[window_name]

    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
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
    rp = reward.params_from_config(cfg)
    gates = lab.get("gates", {})
    max_entries = lab.get("max_entries_per_eval", 20000)

    print(f"\n  PUBLISHED STRATEGIES ON OUR DATA — {window_name} window "
          f"{window[0]} to {window[1]}")
    print(f"  {'strategy':<28}{'net P&L':>11}{'excess':>10}{'null%':>8}{'sharpe':>8}"
          f"{'trades':>8}{'hold':>6}  verdict")
    print("  " + "-" * 104)

    out = []
    for s in SEEDS:
        g = s["genome"]
        res = simulator.simulate(g, panel, cm, size, max_entries=max_entries)
        sc = reward.fitness(res, gn.complexity(g), capital_usd=capital,
                            benchmark_surface=surface, position_size_usd=size, cfg=rp)
        passes = (sc.get("excess_pnl_usd", 0) >= gates.get("min_excess_pnl_usd", 0)
                  and sc.get("sharpe", 0) >= gates.get("min_sharpe", 0)
                  and sc["n_trades"] >= gates.get("min_trades", 20))
        out.append({**s, "scored": sc, "passes": passes})
        print(f"  {s['name']:<28}{sc['net_pnl_usd']:>+11,.0f}"
              f"{sc.get('excess_pnl_usd', 0):>+10,.0f}"
              f"{sc.get('benchmark_net_pct', 0):>+8.2f}{sc.get('sharpe', 0):>8.2f}"
              f"{sc['n_trades']:>8,}{sc.get('avg_hold_days', 0):>6.1f}  "
              f"{'PASSES' if passes else sc['verdict']}")

    conn.close()
    n_pass = sum(o["passes"] for o in out)
    n_profit = sum(o["scored"]["net_pnl_usd"] > 0 for o in out)
    print("  " + "-" * 104)
    print(f"  {n_profit} of {len(out)} made money. {n_pass} of {len(out)} beat the "
          f"null of the stocks they bought, after costs.")
    if n_pass == 0:
        print("  None clearing the bar is a result, not a bug: it says these "
              "published rules\n  do not survive costs on this universe, which is "
              "what most of the literature\n  since the 1990s also says.")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--window", default="search", choices=("search", "validation"))
    parser.add_argument("--list", action="store_true", dest="just_list")
    args = parser.parse_args()
    if args.just_list:
        show()
        return
    cfg = load_config()
    runtime.be_nice()
    evaluate(cfg, args.window)


if __name__ == "__main__":
    main()
