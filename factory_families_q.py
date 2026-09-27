"""Stage Q: short-term strategies (owner, 2026-09-27: "let's build the testing on
short-term trading strategies").

Holds of one to five sessions. Every entry fills at the next open, so a one-day
hold is the overnight trade: bought at the open after the signal, sold at the
open after that. Same-day round trips are not modelled here: the account allows
three in five sessions (pattern-day-trader rule), so intraday ideas are recorded
in SHADOW by intraday.py instead of backtested on daily bars.

Templates, not search: fixed small grids of well-known short-horizon effects,
registered through strategy_factory.family like every other family, then
backtest -> paper (paper_all tracks each one from the day it exists) -> ranking.

    short-term reversal   Jegadeesh 1990; Lehmann 1990 (last week's losers bounce)
    pullback in uptrend   Connors-style: a short drop inside a long uptrend
    oversold oscillators  RSI / stochastic / Bollinger extremes above the 200-day
    one-day momentum      the opposite bet, as a control for the reversal families
    volume-shock reversal a heavy-volume down day (Campbell, Grossman & Wang 1993)

Importing this module registers the families; registration is idempotent.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import strategy_factory as sf

NEW_FAMILIES = (
    "st_reversal_1d", "st_reversal_5d", "st_momentum_1d", "st_uptrend_pullback",
    "st_rsi_oversold", "st_stoch_oversold", "st_bollinger_low", "st_volume_shock",
)


def LIQ(q):
    """The more liquid part of the universe: short holds trade often, so only names
    that trade heavily."""
    return sf.gt(sf.rank(sf.col("log_dollar_volume")), sf.k(q))


UPTREND = sf.gt(sf.col("price_above_sma200"), sf.k(0.5))


def _register():
    sf.family(
        "st_reversal_1d", "mean_reversion",
        "One-day reversal: the day's biggest losers among liquid names bounce over "
        "the next sessions (Lehmann 1990).",
        {"q": [0.05, 0.1], "hold": [1, 2, 3], "stop": [2.0]},
        lambda p: sf.G(sf.and_(sf.lt(sf.rank(sf.pct(sf.col("close"), 1)), sf.k(p["q"])), LIQ(0.5)),
                       None, p["stop"], p["hold"]))

    sf.family(
        "st_reversal_5d", "mean_reversion",
        "Weekly reversal: last week's biggest losers outperform next week "
        "(Jegadeesh 1990; Lehmann 1990).",
        {"q": [0.05, 0.1], "hold": [2, 3, 5], "stop": [2.5]},
        lambda p: sf.G(sf.and_(sf.lt(sf.rank(sf.pct(sf.col("close"), 5)), sf.k(p["q"])), LIQ(0.5)),
                       None, p["stop"], p["hold"]))

    sf.family(
        "st_momentum_1d", "tactical",
        "One-day momentum: the day's biggest gainers keep going — the opposite bet to "
        "the reversal families, kept as their control.",
        {"q": [0.9, 0.95], "hold": [1, 2], "stop": [2.0]},
        lambda p: sf.G(sf.and_(sf.gt(sf.rank(sf.pct(sf.col("close"), 1)), sf.k(p["q"])), LIQ(0.5)),
                       None, p["stop"], p["hold"]))

    sf.family(
        "st_uptrend_pullback", "mean_reversion",
        "Pullback in an uptrend: a sharp three-day drop in a stock above its 200-day "
        "average is bought for a few sessions.",
        {"q": [0.05, 0.1], "hold": [2, 3, 5], "stop": [2.5]},
        lambda p: sf.G(sf.and_(UPTREND, sf.lt(sf.rank(sf.pct(sf.col("close"), 3)), sf.k(p["q"])), LIQ(0.5)),
                       None, p["stop"], p["hold"]))

    sf.family(
        "st_rsi_oversold", "mean_reversion",
        "RSI oversold above the 200-day: buy RSI(14) below the threshold in an uptrend, "
        "sell when RSI recovers above 50 or at the holding limit.",
        {"rsi": [25, 30], "hold": [3, 5], "stop": [2.5]},
        lambda p: sf.G(sf.and_(UPTREND, sf.lt(sf.col("rsi_14"), sf.k(p["rsi"])), LIQ(0.5)),
                       sf.gt(sf.col("rsi_14"), sf.k(50)), p["stop"], p["hold"]))

    sf.family(
        "st_stoch_oversold", "mean_reversion",
        "Stochastic oversold above the 200-day: %K below the threshold in an uptrend.",
        {"k": [10, 20], "hold": [2, 3], "stop": [2.5]},
        lambda p: sf.G(sf.and_(UPTREND, sf.lt(sf.col("stoch_k"), sf.k(p["k"])), LIQ(0.5)),
                       sf.gt(sf.col("stoch_k"), sf.k(60)), p["stop"], p["hold"]))

    sf.family(
        "st_bollinger_low", "mean_reversion",
        "Below the lower Bollinger band in an uptrend: bought for a few sessions.",
        {"hold": [2, 3, 5], "stop": [2.5]},
        lambda p: sf.G(sf.and_(UPTREND, sf.lt(sf.col("bb_pct"), sf.k(0.0)), LIQ(0.5)),
                       sf.gt(sf.col("bb_pct"), sf.k(0.5)), p["stop"], p["hold"]))

    sf.family(
        "st_volume_shock", "mean_reversion",
        "Volume-shock reversal: a heavy-volume down day among liquid names reverses "
        "(Campbell, Grossman & Wang 1993).",
        {"hold": [1, 2, 3], "stop": [2.5]},
        lambda p: sf.G(sf.and_(sf.gt(sf.rank(sf.col("vol_ratio")), sf.k(0.95)),
                               sf.lt(sf.rank(sf.pct(sf.col("close"), 1)), sf.k(0.1)), LIQ(0.5)),
                       None, p["stop"], p["hold"]))


_register()
