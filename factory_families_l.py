"""Stage L3: families rebuilt from published signals that survived publication.

Templates, not search. Each family is a fixed encoding of a published effect
whose post-publication evidence (JKP, survivorship-free, dead companies
included) still shows a t-statistic above 3; they are registered through
strategy_factory.family exactly like the built-in families, so the freeze
boundary of strategy_factory applies unchanged (no factory output may enter the
evolutionary population). Where an encoding deviates from the source paper the
rationale says so in a few words.

Importing this module registers the families as a side effect; registration is
idempotent (strategy_factory.family overwrites by name).
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import strategy_factory as sf

NEW_FAMILIES = (
    "momentum_12_1", "momentum_9_1", "fcf_to_price", "earnings_surprise",
)

# Which Research Library entries each family encodes, new and existing. The
# existing families are listed here so link_library can stamp them too; this
# module registers only NEW_FAMILIES.
PUBLISHED = {
    "momentum_12_1": ["published:jkp:ret_12_1"],
    "momentum_9_1": ["published:jkp:ret_9_1"],
    "fcf_to_price": ["published:jkp:fcf_me"],
    "earnings_surprise": ["published:jkp:niq_su"],
    "quality_piotroski": ["published:jkp:f_score"],
    "earnings_yield": ["published:jkp:ni_me"],
    "buyback": ["published:jkp:eqnetis_at", "published:jkp:chcsho_12m"],
    "value_book": ["published:jkp:be_me"],
    "profitability": ["published:jkp:gp_at"],
    "low_investment": ["published:jkp:at_gr1"],
    "low_accruals": ["published:jkp:oaccruals_at"],
    "liquidity_premium": ["published:jkp:ami_126d"],
    "seasonality_12m": ["published:jkp:seas_1_1an"],
}


def lag(a, n):
    return {"op": "lag", "args": [a], "n": int(n)}


def _register():
    sf.family(
        "momentum_12_1", "momentum",
        "Jegadeesh & Titman (1993) 12-1 month momentum; JKP post-publication "
        "long-tercile excess +0.45%/month (t 3.25, 1994-2025, dead companies "
        "included).",
        {"q": [0.8, 0.9], "stop": [3.0, 4.0]},
        lambda p: sf.G(
            sf.gt(sf.rank(lag(sf.pct(sf.col("close"), 231), 21)), sf.k(p["q"])),
            None, p["stop"], 21))

    sf.family(
        "momentum_9_1", "momentum",
        "9-1 month momentum; JKP post-publication +0.48%/month (t 3.43).",
        {"q": [0.8, 0.9], "stop": [3.0, 4.0]},
        lambda p: sf.G(
            sf.gt(sf.rank(lag(sf.pct(sf.col("close"), 168), 21)), sf.k(p["q"])),
            None, p["stop"], 21))

    sf.family(
        "fcf_to_price", "fundamental",
        "Free cash flow to price (Lakonishok, Shleifer & Vishny 1994); JKP "
        "post-publication +0.52%/month (t 4.43).",
        {"q": [0.8]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("fcf_to_price")), sf.k(p["q"])), None, 3.0, 60),
        data=("features", "daily_fundamentals", "free cash flow"), available=False,
        missing="free cash flow (operating cash flow minus capex) is not on the "
                "daily panel; value_metrics.fcf_yield is operating cash flow / "
                "market cap (JKP ocf_me), not free cash flow")

    sf.family(
        "earnings_surprise", "event",
        "Standardized earnings surprise (Foster, Olsen & Shevlin 1984); JKP "
        "post-publication +0.35%/month (t 3.43).",
        {"q": [0.8]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("sue")), sf.k(p["q"])), None, 3.0, 60),
        data=("features", "quarterly EPS"), available=False,
        missing="standardized unexpected earnings is computed by pead.py per "
                "filing but not projected onto the daily panel")


def link_library(conn):
    """Stamp strategy_library rows with the family that implements them.

    Only rows that already exist are touched; a missing entry is skipped, never
    created, so this cannot invent library coverage.
    """
    updated = 0
    for name, entry_ids in PUBLISHED.items():
        for entry_id in entry_ids:
            cur = conn.execute(
                "UPDATE strategy_library SET implementation=? WHERE entry_id=?",
                ("factory family " + name, entry_id))
            updated += cur.rowcount
    conn.commit()
    return updated


_register()
