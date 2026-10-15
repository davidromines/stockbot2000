"""
Intraday Momentum Runner (Addendum G), M2: the minute-bar trade simulator.

The simulator's job is to be pessimistic where the data cannot say what happened. Its rules are the plan's R2.5
specification, one-to-one:

  * Signal observed at the CLOSE of bar `signal_idx`. The fill is at the OPEN of bar `signal_idx + 1 + latency_bars`
    (default one extra bar), never at a price that existed before the decision could be acted on.
  * Entries pay the ask side: open x (1 + half-spread + slippage); exits receive the bid side: price x (1 - half-spread
    - slippage), less the sell-side regulatory fee. Costs are therefore inside net_pct, and gross_pct is the mid-price move.
  * Inside one bar the adverse extreme is assumed to come FIRST: each bar is checked against the stop as it stood at the
    START of the bar (built from earlier bars' highs); only afterwards does the bar's high lift the trailing stop.
  * A bar that starts before the fill can never lift the stop (intraday_stops.TrailingStop).
  * A stop breach inside a bar fills at the next executable price: min(next bar's open, trigger). A bar that OPENS at or
    below the stop is a gap: it fills at that open. The stop price is stored as `trigger_price`, the sale as `exec_ref`;
    the gap or slippage loss against the trigger is reported (`past_trigger_pct`).
  * Time exits (maximum hold, the New-York-time flatten) execute at the first open at or after the moment.
  * Signal exits (`exit_signal(k, ctx)` -> reason or None) execute at the next bar's open.

Bars: a DataFrame with tz-aware `ts` (bar START, one minute), open, high, low, close. Nothing here reads a database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

import intraday_stops as st


@dataclass(frozen=True)
class Costs:
    half_spread_bps: float = 2.0
    slippage_bps: float = 2.0         # per side, on top of the half spread
    sell_fee_bps: float = 0.3         # SEC + FINRA fees on the sale, approximated
    latency_bars: int = 1             # whole bars between the signal bar and the fill bar (beyond the next open)

    @property
    def side_bps(self) -> float:
        return self.half_spread_bps + self.slippage_bps


def simulate_trade(bars: pd.DataFrame, signal_idx: int, cfg: st.StopConfig, costs: Costs = Costs(),
                   position_dollars: float = 20.0, exit_signal=None) -> dict | None:
    """One long round trip, or None when there is no bar to fill on. See the module docstring for the rules."""
    n = len(bars)
    fill_idx = signal_idx + 1 + costs.latency_bars
    if fill_idx >= n:
        return None
    ts, op, hi, lo, cl = (bars[c].to_numpy() for c in ("ts", "open", "high", "low", "close"))
    ts = list(bars["ts"])
    fill_time = ts[fill_idx]
    entry_ref = float(op[fill_idx])
    entry_px = entry_ref * (1 + costs.side_bps / 1e4)
    stop = st.TrailingStop(entry_px, fill_time, cfg)
    day = fill_time.astimezone(st.NY).date()
    flat_at = st.flatten_at(day, cfg)
    deadline = fill_time + timedelta(minutes=cfg.max_hold_minutes) if cfg.max_hold_minutes else None

    mfe = mae = 0.0
    exit_idx, exec_ref, trigger, reason = None, None, None, None
    for k in range(fill_idx, n):
        # 1. time exits are decided before the bar is traded: from this bar's open the position is to be out
        if ts[k] >= flat_at:
            exit_idx, exec_ref, trigger, reason = k, float(op[k]), None, "end-of-session flatten"
            break
        if deadline is not None and ts[k] >= deadline:
            exit_idx, exec_ref, trigger, reason = k, float(op[k]), None, "maximum holding time"
            break
        # 2. adverse first: the stop as it stood at the start of the bar
        level = stop.stop_price
        if op[k] <= level:                                       # gap through the stop: sold at the open
            exit_idx, exec_ref, trigger, reason = k, float(op[k]), level, f"{stop.reason()} (gap)"
            mae = min(mae, op[k] / entry_px - 1)
            break
        if lo[k] <= level:                                       # breached inside the bar: next executable price
            nxt = float(op[k + 1]) if k + 1 < n else float(cl[k])
            exit_idx, exec_ref, trigger, reason = min(k + 1, n - 1), min(nxt, level), level, stop.reason()
            mae = min(mae, lo[k] / entry_px - 1)
            break
        mae = min(mae, lo[k] / entry_px - 1)
        # 3. then the favourable extreme: lifts the stop for the bars that follow
        stop.observe_bar_high(ts[k], float(hi[k]))
        mfe = max(mfe, hi[k] / entry_px - 1)
        # 4. signal exits act on the next open
        if exit_signal is not None:
            why = exit_signal(k, {"stop": stop.stop_price, "highest": stop.highest, "close": float(cl[k])})
            if why and k + 1 < n:
                exit_idx, exec_ref, trigger, reason = k + 1, float(op[k + 1]), None, why
                break
    if exit_idx is None:                                         # data ended with the position open
        exit_idx, exec_ref, trigger, reason = n - 1, float(cl[n - 1]), None, "data ended"

    exit_px = exec_ref * (1 - costs.side_bps / 1e4) * (1 - costs.sell_fee_bps / 1e4)
    gross = (exec_ref / entry_ref - 1) * 100
    net = (exit_px / entry_px - 1) * 100
    held = (ts[exit_idx] - fill_time).total_seconds() / 60
    shares = position_dollars / entry_px
    return {
        "signal_time": ts[signal_idx], "fill_time": fill_time, "exit_time": ts[exit_idx],
        "entry_ref": entry_ref, "entry_px": entry_px, "trigger_price": trigger, "exec_ref": exec_ref, "exit_px": exit_px,
        "reason": reason, "gross_pct": gross, "net_pct": net, "costs_pct": gross - net,
        "mfe_pct": mfe * 100, "mae_pct": mae * 100, "hold_minutes": held,
        "stopped": trigger is not None,
        "past_trigger_pct": (max(0.0, (trigger - exec_ref) / trigger * 100) if trigger else 0.0),
        "intended_stop_loss_pct": (1 - stop.initial / entry_px) * 100,
        "gross_usd": shares * (exec_ref * 1.0 - entry_ref), "net_usd": shares * (exit_px - entry_px),
        "final_stop": stop.stop_price, "highest": stop.highest,
        "date": str(fill_time.astimezone(st.NY).date()),
    }


def summarize(trades: list) -> dict:
    """The statistics the plan requires for every tested configuration (Phase 7)."""
    if not trades:
        return {"trades": 0}
    d = pd.DataFrame(trades).sort_values("exit_time")
    net = d["net_pct"]
    equity = d["net_usd"].cumsum()
    dd = float((equity.cummax() - equity).max())
    gap = d[d["past_trigger_pct"] > 0]
    return {"trades": int(len(d)), "dates": int(d["date"].nunique()), "win_rate": float((net > 0).mean()),
            "mean_net_pct": float(net.mean()), "median_net_pct": float(net.median()),
            "gross_usd": float(d["gross_usd"].sum()), "costs_usd": float(d["gross_usd"].sum() - d["net_usd"].sum()),
            "net_usd": float(d["net_usd"].sum()), "mfe_pct": float(d["mfe_pct"].mean()), "mae_pct": float(d["mae_pct"].mean()),
            "hold_minutes": float(d["hold_minutes"].mean()), "stop_rate": float(d["stopped"].mean()),
            "gap_losses": int(len(gap)), "gap_loss_pct_mean": float(gap["past_trigger_pct"].mean()) if len(gap) else 0.0,
            "max_drawdown_usd": dd}
