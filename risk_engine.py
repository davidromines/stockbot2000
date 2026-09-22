"""
The gate every order passes. Phase 4.

WHAT THIS IS FOR
----------------
A strategy decides what it *wants*. This decides what is *allowed*. The two are
separate on purpose: strategies are rewritten constantly and are the least
trustworthy part of the system, while these limits change rarely and bound the
damage any of them can do.

**There is no path to a broker that does not pass through `validate()`.**
`execution.py` calls it and refuses to proceed on rejection. Nothing else in the
project is permitted to construct a broker order.

WHY IT TAKES A PORTFOLIO SNAPSHOT RATHER THAN READING STATE ITSELF
------------------------------------------------------------------
The caller fetches live account state and hands it in. That makes the engine
pure and testable — every limit below is exercised in tests with a synthetic
portfolio — and it means the engine cannot accidentally validate against stale
cached state, because it has no cache to be stale.

FAIL CLOSED
-----------
Anything the engine cannot evaluate is a rejection, not a pass. A missing quote,
an unknown market cap, a portfolio it could not read: all rejections. The
alternative is an order sized against a number nobody checked.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("risk")

RISK_CONFIG = Path("config/risk.yaml")


@dataclass
class RiskResult:
    approved: bool
    reasons: list = field(default_factory=list)
    sized_notional: float | None = None
    sized_quantity: float | None = None

    def reject(self, why: str) -> "RiskResult":
        self.approved = False
        self.reasons.append(why)
        return self


def load_limits(path: Path | str = RISK_CONFIG) -> dict:
    p = Path(path)
    if not p.exists():
        # Not a warning-and-defaults situation. Running without limits because a
        # file was missing is exactly the accident this module exists to prevent.
        raise FileNotFoundError(
            f"{p} not found. The risk engine will not run without explicit "
            f"limits — an absent config is not permission to trade unbounded.")
    return yaml.safe_load(p.read_text()) or {}


class RiskEngine:
    def __init__(self, limits: dict | None = None):
        self.L = limits if limits is not None else load_limits()

    # -- individual checks, each returning a reason string or None -----------

    def _check_instrument(self, sig) -> str | None:
        if sig.asset_type == "option" and not self.L.get("allow_options", False):
            return "options are not permitted"
        if sig.asset_type == "crypto" and not self.L.get("allow_crypto", False):
            return "crypto is not permitted"
        if sig.action == "SELL" and not self.L.get("allow_shorting", False):
            # SELL of a held position is a CLOSE; SELL without a position is a
            # short, which a cash account cannot do anyway.
            return None
        return None

    def _check_confidence(self, sig) -> str | None:
        floor = float(self.L.get("min_signal_confidence", 0.0) or 0.0)
        if floor and sig.confidence < floor:
            return f"confidence {sig.confidence:.2f} below floor {floor:.2f}"
        return None

    def _check_tradeability(self, sig, quote: dict | None) -> str | None:
        if quote is None:
            return "no quote available — cannot size or price the order"
        px = quote.get("price")
        if not px or px <= 0:
            return "quote has no usable price"
        mp = float(self.L.get("min_price", 0) or 0)
        if mp and px < mp:
            return f"price ${px:.2f} below floor ${mp:.2f}"
        dv = quote.get("dollar_volume_20")
        mdv = float(self.L.get("min_dollar_volume", 0) or 0)
        if mdv:
            if dv is None:
                return "liquidity unknown — rejected rather than assumed"
            if dv < mdv:
                return f"turnover ${dv:,.0f}/day below floor ${mdv:,.0f}"
        cap = quote.get("market_cap")
        mcap = float(self.L.get("min_market_cap_usd", 0) or 0)
        if mcap:
            # Unknown cap is a rejection. TNON had no market cap on record and a
            # "reject if below floor" test waved it through as unmeasured; it
            # then lost 29%. A missing measurement is not an average one.
            if cap is None:
                return "market cap unknown — rejected rather than assumed"
            if cap < mcap:
                return f"market cap ${cap/1e6:,.0f}M below floor ${mcap/1e6:,.0f}M"
        return None

    def _check_throttles(self, sig, today: dict) -> str | None:
        n = int(today.get("orders_today", 0))
        cap = int(self.L.get("max_orders_per_day", 10**9))
        if n >= cap:
            return f"daily order cap reached ({n}/{cap})"
        per = int(today.get("orders_for_symbol", 0))
        pcap = int(self.L.get("max_orders_per_symbol_per_day", 10**9))
        if per >= pcap:
            return f"per-symbol order cap reached for {sig.symbol} ({per}/{pcap})"
        return None

    def _check_losses(self, portfolio: dict) -> str | None:
        eq = float(portfolio.get("equity") or 0)
        dl = float(portfolio.get("daily_pnl") or 0)
        cap_usd = float(self.L.get("max_daily_loss_dollars", 0) or 0)
        if cap_usd and dl <= -abs(cap_usd):
            return f"daily loss ${dl:,.2f} breaches ${cap_usd:,.2f} limit"
        cap_pct = float(self.L.get("max_daily_loss_percent", 0) or 0)
        if cap_pct and eq > 0 and (dl / eq * 100) <= -abs(cap_pct):
            return f"daily loss {dl/eq*100:.1f}% breaches {cap_pct:.1f}% limit"
        dd = float(portfolio.get("drawdown_percent") or 0)
        cap_dd = float(self.L.get("max_drawdown_percent", 0) or 0)
        if cap_dd and dd >= abs(cap_dd):
            return f"drawdown {dd:.1f}% breaches {cap_dd:.1f}% limit"
        return None

    def _size(self, sig, quote: dict, portfolio: dict, res: RiskResult) -> str | None:
        """Decide the notional, then check it against every size limit."""
        px = float(quote["price"])
        want = (float(sig.notional_value) if sig.notional_value
                else float(sig.quantity) * px)

        trade_cap = float(self.L.get("max_trade_dollars", 0) or 0)
        if trade_cap:
            want = min(want, trade_cap)

        held = float(portfolio.get("positions", {}).get(sig.symbol, {}).get("value", 0))
        pos_cap = float(self.L.get("max_position_dollars", 0) or 0)
        if pos_cap:
            room = pos_cap - held
            if room <= 0:
                return (f"already holding ${held:,.2f} of {sig.symbol}, at the "
                        f"${pos_cap:,.2f} position cap")
            want = min(want, room)

        eq = float(portfolio.get("equity") or 0)
        pct_cap = float(self.L.get("max_position_percent", 0) or 0)
        if pct_cap and eq > 0:
            room = eq * pct_cap / 100.0 - held
            if room <= 0:
                return f"{sig.symbol} already at the {pct_cap:.0f}% position cap"
            want = min(want, room)

        cash = float(portfolio.get("buying_power") or 0)
        if want > cash:
            # Not an error: buy what there is room for. But a fill so small it
            # is mostly spread is worse than no trade.
            want = cash
        if want < 1.0:
            return f"sized down to ${want:,.2f}, below the $1 minimum worth trading"

        open_n = len(portfolio.get("positions", {}))
        max_open = int(self.L.get("max_open_positions", 10**9))
        if sig.action == "BUY" and sig.symbol not in portfolio.get("positions", {}) \
                and open_n >= max_open:
            return f"{open_n} positions open, at the cap of {max_open}"

        if not self.L.get("allow_fractional_shares", True):
            shares = int(want / px)
            if shares < 1:
                return f"whole shares only and ${want:,.2f} buys none at ${px:,.2f}"
            want = shares * px
            res.sized_quantity = float(shares)
        else:
            res.sized_quantity = want / px
        res.sized_notional = round(want, 2)
        return None

    # -- the entry point -----------------------------------------------------

    def validate(self, sig, portfolio: dict, quote: dict | None = None,
                 today: dict | None = None) -> RiskResult:
        """
        Approve or reject one signal. Collects EVERY reason, not just the first.

        Reporting one reason at a time turns diagnosis into a guessing game: fix
        the confidence floor, rerun, discover the liquidity floor, rerun again.
        """
        res = RiskResult(approved=True)
        today = today or {}
        sig.validate()

        if not sig.is_actionable():
            return res.reject(f"{sig.action} places no order")

        for check in (self._check_instrument(sig),
                      self._check_confidence(sig),
                      self._check_throttles(sig, today),
                      self._check_losses(portfolio)):
            if check:
                res.reject(check)

        if sig.action in ("SELL", "CLOSE"):
            # Exits are not size-limited. A limit that can block a sale is a
            # limit that traps capital in a losing position, which is the
            # opposite of risk control.
            held = portfolio.get("positions", {}).get(sig.symbol)
            if not held:
                res.reject(f"no open position in {sig.symbol} to close")
            return res

        tq = self._check_tradeability(sig, quote)
        if tq:
            res.reject(tq)
        if res.approved:
            sized = self._size(sig, quote, portfolio, res)
            if sized:
                res.reject(sized)
        return res
