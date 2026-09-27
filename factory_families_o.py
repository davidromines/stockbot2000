"""Stage O: Knowledge Library translations into the Strategy Factory registry.

Templates, not search. These ten families are fixed encodings of published
effects, registered through strategy_factory.family exactly like the built-in
families; the freeze boundary of strategy_factory applies unchanged (no factory
output may enter the evolutionary population). Where an encoding deviates from
the source paper the rationale says so in a few words — the index-level effects
are traded here on the most liquid decile of stocks, and the January small-cap
effect on the least liquid names, because this universe has no index series.

Importing this module registers the families as a side effect; registration is
idempotent (strategy_factory.family overwrites by name).
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import strategy_factory as sf

NEW_FAMILIES = (
    "turn_of_month", "pre_holiday", "payday", "january_illiquid",
    "seasonality_12m", "liquidity_premium", "small_cap", "rd_intensity",
    "short_interest", "capm_alpha",
)

KNOWLEDGE = {
    "turn_of_month": ["qc_library:b2e0400834cd", "pwb_coded:8b0022f2370f"],
    "pre_holiday": ["qc_library:9eb436f81ad0"],
    "payday": ["pwb_coded:336bb3426a28"],
    "january_illiquid": ["qc_library:2ff4bfc415b4"],
    "seasonality_12m": ["pwb_coded:153777789290"],
    "liquidity_premium": ["qc_library:6450e56a750e"],
    "small_cap": ["qc_library:57785be8f6f4", "pwb_coded:4386f6dde875"],
    "rd_intensity": ["pwb_coded:ff2022843d1f"],
    "short_interest": ["pwb_coded:e43bdc6be336"],
    "capm_alpha": ["qc_library:0939e67287ee"],
}


def lag(a, n):
    return {"op": "lag", "args": [a], "n": int(n)}


def LIQ(q):
    """Most liquid names — the closest this stock universe gets to 'the index'."""
    return sf.gt(sf.rank(sf.col("log_dollar_volume")), sf.k(q))


def ILLIQ(q):
    return sf.lt(sf.rank(sf.col("log_dollar_volume")), sf.k(q))


def _register():
    sf.family(
        "turn_of_month", "tactical",
        "Turn-of-the-month: returns concentrate around the month boundary "
        "(Ariel 1987; Lakonishok & Smidt 1988); traded here on the most liquid "
        "decile of stocks, not the index.",
        {"last": [1, 2], "stop": [2.0, 3.0]},
        lambda p: sf.G(
            sf.and_(sf.lt(sf.col("cal_tdom_rev"), sf.k(p["last"] + 0.5)), LIQ(0.9)),
            sf.and_(sf.gt(sf.col("cal_tdom"), sf.k(3.5)), sf.lt(sf.col("cal_tdom"), sf.k(10))),
            p["stop"], 5))

    sf.family(
        "pre_holiday", "tactical",
        "Pre-holiday effect: the session before a market holiday earns abnormal "
        "returns (Ariel 1990); traded on the most liquid decile, not the index.",
        {"hold": [1, 2], "stop": [2.0, 3.0]},
        lambda p: sf.G(
            sf.and_(sf.gt(sf.col("cal_pre_holiday"), sf.k(0.5)), LIQ(0.9)),
            sf.gt(sf.col("cal_post_holiday"), sf.k(0.5)),
            p["stop"], p["hold"]))

    sf.family(
        "payday", "tactical",
        "Payday anomaly: returns are positive around the 14th-15th of the month "
        "when wages are paid (Ma & Pratt; Quantpedia payday anomaly); traded on "
        "the most liquid decile, not the index.",
        {"hold": [2, 3], "stop": [2.0, 3.0]},
        lambda p: sf.G(
            sf.and_(sf.gt(sf.col("cal_dom"), sf.k(13.5)),
                    sf.lt(sf.col("cal_dom"), sf.k(15.5)), LIQ(0.9)),
            None, p["stop"], p["hold"]))

    sf.family(
        "january_illiquid", "tactical",
        "January effect: small, illiquid names rally in January (Keim 1983; "
        "Reinganum 1983); traded here on the least liquid names, the closest "
        "available proxy for small caps.",
        {"q": [0.2, 0.3], "stop": [3.0, 5.0]},
        lambda p: sf.G(
            sf.and_(sf.gt(sf.col("cal_month"), sf.k(11.5)),
                    sf.lt(sf.col("cal_tdom_rev"), sf.k(1.5)), ILLIQ(p["q"])),
            sf.and_(sf.gt(sf.col("cal_month"), sf.k(1.5)), sf.lt(sf.col("cal_month"), sf.k(2.5))),
            p["stop"], 30))

    sf.family(
        "seasonality_12m", "momentum",
        "Twelve-month seasonality: the same calendar month's return one year ago "
        "predicts this month's return (Heston & Sadka 2008).",
        {"q": [0.9, 0.95], "stop": [3.0, 4.0]},
        lambda p: sf.G(
            sf.gt(sf.rank(lag(sf.pct(sf.col("close"), 21), 231)), sf.k(p["q"])),
            None, p["stop"], 21))

    sf.family(
        "liquidity_premium", "tactical",
        "Illiquidity premium: less liquid stocks earn higher expected returns "
        "(Amihud 2002).",
        {"q": [0.1, 0.2], "hold": [40, 60], "stop": [3.0, 5.0]},
        lambda p: sf.G(ILLIQ(p["q"]), None, p["stop"], p["hold"]))

    sf.family(
        "small_cap", "fundamental",
        "Size premium: small-capitalisation stocks outperform (Banz 1981).",
        {"q": [0.2]},
        lambda p: sf.G(sf.lt(sf.rank(sf.col("market_cap")), sf.k(p["q"])), None, 3.0, 60),
        data=("features", "daily_fundamentals", "market_cap"))   # projected 2026-09-27 (filing-date cap)

    sf.family(
        "rd_intensity", "fundamental",
        "R&D intensity: firms with high R&D to assets earn excess returns "
        "(Chan, Lakonishok & Sougiannis 2001).",
        {"q": [0.8]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("rd_to_assets")), sf.k(p["q"])), None, 3.0, 60),
        data=("features", "daily_fundamentals", "R&D expense"))   # rd_to_assets, 2026-09-27

    sf.family(
        "short_interest", "fundamental",
        "Short selling: heavily shorted stocks underperform, lightly shorted ones do not "
        "(Boehmer, Jones & Zhang 2008; Asquith, Pathak & Ritter 2005). Measured with FINRA's "
        "daily short-sale volume over 20 sessions (short_volume.py) — short selling "
        "activity, the free daily proxy for short interest.",
        {"q": [0.1, 0.2]},
        lambda p: sf.G(sf.lt(sf.rank(sf.col("short_volume_ratio_20")), sf.k(p["q"])), None, 3.0, 20),
        data=("features", "FINRA Reg SHO daily short volume"))

    sf.family(
        "capm_alpha", "momentum",
        "CAPM alpha: realised alpha relative to the market is compensated "
        "(Jensen 1968).",
        {"q": [0.8]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("alpha_252")), sf.k(p["q"])), None, 3.0, 20),
        data=("features", "risk_metrics"))   # alpha_252 from risk_metrics.alpha, 2026-09-27


_register()
