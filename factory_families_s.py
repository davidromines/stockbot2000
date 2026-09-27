"""Stage S3: the multi-signal composite as a strategy family.

Templates, not search. composite.py combines eight weak signals (value, earnings
yield, FCF/price, profitability, 9-1 momentum, earnings surprise, the analog score,
short volume) into one score per stock per day, weighted by each signal's trailing
out-of-sample IC with a covariance correction (Kakushadze & Yu 2016). This family
buys the top of that score. Registered through strategy_factory.family like every
other family, so the freeze boundary applies unchanged.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import strategy_factory as sf

NEW_FAMILIES = ("multi_signal", "insider_buying", "politician_buying")


def _register():
    sf.family(
        "multi_signal", "fundamental",
        "Combining weak signals: an IC-weighted, redundancy-corrected composite of "
        "value, earnings yield, FCF/price, profitability, 9-1 momentum, earnings "
        "surprise, the analog score and short volume (Kakushadze & Yu 2016, "
        "'How to Combine a Billion Alphas'). Weights use only ICs whose 20-session "
        "forward return had closed.",
        {"q": [0.9, 0.95], "hold": [20, 60], "stop": [3.0, 4.0]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("composite")), sf.k(p["q"])), None, p["stop"], p["hold"]),
        data=("features", "daily_fundamentals", "daily_composite"))

    # O-ins (owner, 2026-09-27): insider buying from SEC Form 4, the free EDGAR data.
    sf.family(
        "insider_buying", "fundamental",
        "Insider purchases: open-market buys by officers and directors predict returns, "
        "and 'opportunistic' buyers (not trading in the same month every year) carry "
        "the signal (Cohen, Malloy & Pomorski 2012; Lakonishok & Lee 2001). Usable "
        "from the first session after the filing date.",
        {"buyers": [1, 2], "hold": [20, 60], "stop": [3.0, 4.0]},
        lambda p: sf.G(sf.gt(sf.col("opp_buyers_90"), sf.k(p["buyers"] - 0.5)), None, p["stop"], p["hold"]),
        data=("features", "SEC Form 4 insider transactions"))

    # O-pol (owner, 2026-09-26, low priority): House members' disclosed purchases,
    # usable from the first session after the report was made public.
    sf.family(
        "politician_buying", "event",
        "Congressional trading: stocks bought by members of Congress, from STOCK Act "
        "periodic transaction reports, timed on the public filing date (Ziobrowski et "
        "al. 2004/2011; post-2012 evidence is weak — Belmont et al. 2022). A hypothesis, "
        "tested like any other.",
        {"buyers": [1, 2], "hold": [20, 60], "stop": [3.0]},
        lambda p: sf.G(sf.gt(sf.col("congress_buyers_90"), sf.k(p["buyers"] - 0.5)), None, p["stop"], p["hold"]),
        data=("features", "House periodic transaction reports"))


_register()
