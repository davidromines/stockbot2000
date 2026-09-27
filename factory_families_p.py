"""Stage P3: the analog forecaster as a strategy family (owner, 2026-09-27).

Buy the stocks whose closest past analogs rose most often (analog.py; scores are
point-in-time: each used only analogs whose outcome was already known). A
template like every other family: backtest -> paper (paper_all tracks each one
from the day it exists) -> ranking. Synthetic dead companies carry no analog
score, so the dead-company test for this family reads "not measurable".

Importing this module registers the family; registration is idempotent.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import strategy_factory as sf

NEW_FAMILIES = ("analog_top", "analog_stop")


def _register():
    sf.family(
        "analog_top", "tactical",
        "Analog forecaster: stocks whose most similar past setups (chart shape and "
        "fundamentals, percentile-matched) rose most often over the next 20 sessions.",
        {"q": [0.9, 0.95], "hold": [10, 20], "stop": [2.5]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("analog_p_up")), sf.k(p["q"])), None, p["stop"], p["hold"]),
        data=("features", "daily_fundamentals", "analog scores"))

    # P4: the same entry with each trade's stop at its analogs' 10th-percentile outcome
    # (analog_q10): the loss that only one in ten similar past setups suffered.
    def _g(p):
        g = sf.G(sf.gt(sf.rank(sf.col("analog_p_up")), sf.k(p["q"])), None, p["stop"], p["hold"])
        g["risk"]["stop_pct_col"] = "analog_q10"
        return g
    sf.family(
        "analog_stop", "tactical",
        "Analog forecaster with per-trade stops: the stop sits at the 10th-percentile outcome "
        "of the stock's closest past analogs (Stage P4), tightest of that and the ATR stop.",
        {"q": [0.9, 0.95], "hold": [20], "stop": [3.0]}, _g,
        data=("features", "daily_fundamentals", "analog scores"))


_register()
