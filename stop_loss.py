"""
Computes the stop-loss price for a new position, and checks open positions
against current prices to flag exits. Two modes (config.yaml -> risk.stop_loss_type):

- "atr": stop = entry_price - (atr_multiple * ATR_14 at entry). Adapts to each
  stock's own volatility — the standard approach in most of the reference
  projects reviewed.
- "fixed_pct": stop = entry_price * (1 - fixed_pct / 100). Simpler, same for
  every ticker regardless of volatility.
"""
from universe import load_config


def calculate_stop_loss(entry_price: float, atr_14: float, cfg: dict = None) -> float:
    cfg = cfg or load_config()
    risk = cfg["risk"]

    if risk["stop_loss_type"] == "atr":
        if atr_14 is None or atr_14 <= 0:
            # fall back to fixed pct if ATR isn't available for this ticker yet
            return entry_price * (1 - risk["stop_loss_fixed_pct"] / 100)
        return entry_price - (risk["stop_loss_atr_multiple"] * atr_14)
    elif risk["stop_loss_type"] == "fixed_pct":
        return entry_price * (1 - risk["stop_loss_fixed_pct"] / 100)
    else:
        raise ValueError(f"Unknown stop_loss_type: {risk['stop_loss_type']}")


def check_stop_triggered(current_price: float, stop_loss_price: float) -> bool:
    return current_price <= stop_loss_price


def check_take_profit_triggered(current_price: float, entry_price: float, cfg: dict = None) -> bool:
    cfg = cfg or load_config()
    take_profit_pct = cfg["risk"].get("take_profit_pct")
    if take_profit_pct is None:
        return False
    return current_price >= entry_price * (1 + take_profit_pct / 100)
