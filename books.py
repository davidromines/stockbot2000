"""
Capital books and their limits in one place (Addendum D N9, owner 2026-09-27:
"let's get options fully up").

Scaling is a config edit, never a code change. Each book's numbers live in the
file that owns them, and this module reads them together and refuses a set that
does not add up — the mistake that matters when an account grows is changing one
number and not the ones that depend on it.

    book      capital                       sizing                          limits (config/risk.yaml unless noted)
    stocks    capital.stocks_usd (config)   slots.count x capital_per_slot  max_trade/position dollars, max_open_positions,
                                                                             daily loss, drawdown
    options   options.live.capital_usd      options.live.per_trade_usd x    options.live: max_open, max_daily_loss_usd,
              (config; armed by risk.yaml   max_open; paper uses            max_drawdown_pct, min_paper_trades
              allow_options)                options.stake_usd

    ./venv/bin/python books.py            # the books, and any problem (exit 1 if one)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import sys


def books(cfg: dict, limits: dict) -> dict:
    sl = cfg.get("slots") or {}
    cap = cfg.get("capital") or {}
    o = cfg.get("options") or {}
    ol = o.get("live") or {}
    return {
        "stocks": {"capital_usd": float(cap.get("stocks_usd", 100.0)), "slots": int(sl.get("count", 5)),
                   "per_slot_usd": float(sl.get("capital_per_slot", 20.0)),
                   "max_trade_usd": float(limits.get("max_trade_dollars", 0)),
                   "max_position_usd": float(limits.get("max_position_dollars", 0)),
                   "max_open_positions": int(limits.get("max_open_positions", 0)),
                   "max_daily_loss_usd": float(limits.get("max_daily_loss_dollars", 0)),
                   "max_drawdown_pct": float(limits.get("max_drawdown_percent", 0)), "armed": True},
        "options": {"capital_usd": float(ol.get("capital_usd", 1000.0)),
                    "per_trade_usd": float(ol.get("per_trade_usd", 100.0)), "max_open": int(ol.get("max_open", 10)),
                    "paper_stake_usd": float(o.get("stake_usd", 100.0)),
                    "max_daily_loss_usd": float(ol.get("max_daily_loss_usd", 150.0)),
                    "max_drawdown_pct": float(ol.get("max_drawdown_pct", 35.0)),
                    "min_paper_trades": int(ol.get("min_paper_trades", 20)),
                    "armed": bool(limits.get("allow_options"))},
    }


def problems(b: dict) -> list:
    """Every inconsistency that would make a book behave differently from its numbers."""
    out = []
    s = b["stocks"]
    if s["slots"] * s["per_slot_usd"] > s["capital_usd"] + 1e-9:
        out.append(f"stocks: {s['slots']} slots x ${s['per_slot_usd']:.2f} = ${s['slots'] * s['per_slot_usd']:.2f} "
                   f"is more than the ${s['capital_usd']:.2f} book")
    if s["per_slot_usd"] > s["max_trade_usd"]:
        out.append(f"stocks: a ${s['per_slot_usd']:.2f} slot is over the ${s['max_trade_usd']:.2f} per-order limit "
                   "— every entry would be refused")
    if s["per_slot_usd"] > s["max_position_usd"]:
        out.append(f"stocks: a ${s['per_slot_usd']:.2f} slot is over the ${s['max_position_usd']:.2f} per-position limit")
    if s["slots"] > s["max_open_positions"]:
        out.append(f"stocks: {s['slots']} slots but only {s['max_open_positions']} open positions allowed")
    if s["max_daily_loss_usd"] <= 0 or s["max_drawdown_pct"] <= 0:
        out.append("stocks: daily-loss and drawdown limits must be set")
    o = b["options"]
    if o["per_trade_usd"] * o["max_open"] > o["capital_usd"] + 1e-9:
        out.append(f"options: {o['max_open']} x ${o['per_trade_usd']:.2f} = ${o['per_trade_usd'] * o['max_open']:.2f} "
                   f"is more than the ${o['capital_usd']:.2f} book")
    if abs(o["per_trade_usd"] - o["paper_stake_usd"]) > 1e-9:
        out.append(f"options: paper measures ${o['paper_stake_usd']:.2f} trades but real trades are "
                   f"${o['per_trade_usd']:.2f} — the paper record would describe a different size")
    if o["max_daily_loss_usd"] <= 0 or o["max_drawdown_pct"] <= 0:
        out.append("options: daily-loss and drawdown limits must be set")
    return out


def render(b: dict, probs: list) -> str:
    s, o = b["stocks"], b["options"]
    L = [f"  STOCKS   ${s['capital_usd']:.0f}: {s['slots']} slots x ${s['per_slot_usd']:.0f} | order <= ${s['max_trade_usd']:.0f} "
         f"| daily loss <= ${s['max_daily_loss_usd']:.0f} | drawdown <= {s['max_drawdown_pct']:.0f}% | LIVE",
         f"  OPTIONS  ${o['capital_usd']:.0f}: up to {o['max_open']} x ${o['per_trade_usd']:.0f} | daily loss <= "
         f"${o['max_daily_loss_usd']:.0f} | drawdown <= {o['max_drawdown_pct']:.0f}% | proven = {o['min_paper_trades']}+ "
         f"paper trades | {'ARMED' if o['armed'] else 'paper only (allow_options false)'}"]
    L += [f"  PROBLEM  {p}" for p in probs] or ["  consistent"]
    return "\n".join(L)


def main() -> int:
    import risk_engine
    from universe import load_config
    b = books(load_config(), risk_engine.load_limits())
    p = problems(b)
    print(render(b, p))
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main())
