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
        {"q": [0.8, 0.9], "hold": [40, 60], "stop": [3.0, 5.0]},
        lambda p: sf.G(sf.gt(sf.rank(sf.col("fcf_to_price")), sf.k(p["q"])),
                       sf.lt(sf.rank(sf.col("fcf_to_price")), sf.k(0.5)), p["stop"], p["hold"]),
        # Available since 2026-09-26: value_metrics.fcf_to_price = (OCF - capex) / market
        # cap, projected into daily_fundamentals. The same shape as value_book /
        # earnings_yield (top of the rank in, below the median out).
        data=("features", "daily_fundamentals"))

    sf.family(
        "earnings_surprise", "event",
        "Standardized earnings surprise (Foster, Olsen & Shevlin 1984); JKP "
        "post-publication +0.35%/month (t 3.43).",
        {"q": [0.8, 0.9], "age": [5, 10], "hold": [40, 60]},
        # Available since 2026-09-26 (sue_features.py -> daily_sue, joined by
        # storage.attach_fundamentals). Bought only within `age` calendar days of the
        # filing, so an old surprise is never bought as news.
        lambda p: sf.G(sf.and_(sf.gt(sf.rank(sf.col("sue")), sf.k(p["q"])),
                               sf.lt(sf.col("sue_age"), sf.k(p["age"] + 0.5))), None, 3.0, p["hold"]),
        data=("features", "daily_fundamentals"))


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
