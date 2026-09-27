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

NEW_FAMILIES = ("multi_signal",)


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


_register()
