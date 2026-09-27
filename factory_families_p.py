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

NEW_FAMILIES = ("analog_top",)


def _register():
    sf.family(
        "analog_top", "tactical",
        "Analog forecaster: stocks whose most similar past setups (chart shape and "
        "fundamentals, percentile-matched) rose most often over the next 20 sessions.",
        {"q": [0.9, 0.95], "hold": [10, 20], "stop": [2.5]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("analog_p_up")), sf.k(p["q"])), None, p["stop"], p["hold"]),
        data=("features", "daily_fundamentals", "analog scores"))


_register()
