"""
What a trade actually costs. Phase 07.

Every P&L figure this project has produced so far has been gross. At 0.43% per
trade over roughly five trading days, costs are not a rounding error — they are
plausibly the whole result, which is why this has to exist before any strategy is
judged on money.

Four components, all configurable:

**Commission.** Zero on Robinhood. Kept configurable anyway, because "free" is a
broker choice rather than a law, and a strategy that only works at zero
commission is worth knowing about.

**Spread.** The real cost of a commission-free broker. Dollar-amount orders are
market orders (see CLAUDE.md), so every entry pays the offer and every exit hits
the bid. Charged as half the spread per side, estimated from liquidity: thin
names have wider spreads, and the relationship is far from linear.

**Slippage.** Market orders move the price against you. Small for a $10 order,
but not zero, and it grows as liquidity falls.

**SEC and FINRA fees.** Sells only, a few cents per $10k. Genuinely negligible at
this size, included because leaving them out invites the question.

The spread model is an estimate, not a measurement — we hold no quote data, only
daily bars. It is deliberately pessimistic: a strategy that survives an
overstated cost assumption is interesting, one that dies under it was never
viable, and the Strategy Lab will actively hunt for strategies whose profit
depends on costs being small.
"""
import runtime  # noqa: F401  — must precede numpy/pandas

import pandas as pd

# Spread estimates by average daily dollar volume. Round numbers on purpose:
# these are informed guesses, and false precision would imply a measurement we
# have not made.
SPREAD_TIERS = [
    (100_000_000, 0.0005),   # >$100M/day — mega caps, ~5 bps
    (20_000_000,  0.0010),   # >$20M/day  — large caps, ~10 bps
    (5_000_000,   0.0020),   # >$5M/day   — mid caps, ~20 bps
    (1_000_000,   0.0040),   # >$1M/day   — small caps, ~40 bps
    (0,           0.0100),   # below that — 100 bps, and optimistic
]


def estimate_spread_pct(dollar_volume) -> "pd.Series | float":
    """
    Round-trip spread as a fraction of price, from average daily dollar volume.

    Liquidity is the only spread proxy available from daily bars. It is a decent
    one: spread and turnover are strongly related in US equities.
    """
    if isinstance(dollar_volume, pd.Series):
        out = pd.Series(SPREAD_TIERS[-1][1], index=dollar_volume.index, dtype="float64")
        for floor, spread in SPREAD_TIERS[:-1]:
            out = out.mask(dollar_volume >= floor, spread)
            # mask() applies to rows still above this floor, and tiers descend,
            # so the tightest matching tier wins.
        return out
    for floor, spread in SPREAD_TIERS:
        if dollar_volume >= floor:
            return spread
    return SPREAD_TIERS[-1][1]


class CostModel:
    """Per-trade costs in dollars. One place, so backtest and paper agree."""

    def __init__(self, cfg: dict):
        c = cfg.get("costs", {})
        self.enabled = c.get("enabled", True)
        self.commission_per_trade = float(c.get("commission_per_trade_usd", 0.0))
        self.slippage_pct = float(c.get("slippage_pct_per_side", 0.05)) / 100.0
        self.spread_multiplier = float(c.get("spread_multiplier", 1.0))
        self.sec_fee_rate = float(c.get("sec_fee_per_million_usd", 27.80)) / 1_000_000
        self.finra_taf_per_share = float(c.get("finra_taf_per_share_usd", 0.000166))
        self.finra_taf_cap = float(c.get("finra_taf_cap_usd", 8.30))

    def round_trip(self, notional_usd, dollar_volume=None, shares=None):
        """
        Total cost of entering and exiting one position.

        Spread is charged once per round trip rather than twice: the quoted
        spread is the full bid-offer, and each side crosses half of it.
        """
        if not self.enabled:
            zero = notional_usd * 0 if isinstance(notional_usd, pd.Series) else 0.0
            return zero

        spread_pct = (estimate_spread_pct(dollar_volume) * self.spread_multiplier
                      if dollar_volume is not None else 0.0)
        spread_cost = notional_usd * spread_pct
        slip_cost = notional_usd * self.slippage_pct * 2      # both sides
        commission = self.commission_per_trade * 2
        sec_fee = notional_usd * self.sec_fee_rate            # sell side only
        taf = 0.0
        if shares is not None:
            taf = (shares * self.finra_taf_per_share).clip(upper=self.finra_taf_cap) \
                if isinstance(shares, pd.Series) else \
                min(shares * self.finra_taf_per_share, self.finra_taf_cap)
        return spread_cost + slip_cost + commission + sec_fee + taf

    def describe(self) -> str:
        if not self.enabled:
            return "costs DISABLED — figures are gross"
        return (f"costs: spread by liquidity x{self.spread_multiplier:g}, "
                f"slippage {self.slippage_pct * 100:.3g}%/side, "
                f"commission ${self.commission_per_trade:g}/side, SEC+TAF fees")
