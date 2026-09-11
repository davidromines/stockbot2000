"""
Scores one genome against history. Phase 08. The hot inner loop.

Everything expensive is precomputed once per dataset, not once per candidate.
Forward price matrices, ATR and liquidity do not depend on the genome, so
building them per evaluation would dominate the cost of the search entirely.

What a candidate pays for, per evaluation:
  - evaluating its entry and exit trees over the panel
  - shifting the exit signal forward to find each position's exit day
  - a vectorised argmax to pick whichever exit fires first

**Costs are charged inside the simulator, not bolted on afterwards.** The search
optimises whatever it is scored on; scored on gross returns it would reliably
discover high-turnover strategies that cannot pay their own spread. Net P&L in
dollars is the output that matters.

Exit priority, in order: stop-loss, take-profit, the genome's exit rule, then the
holding-period limit. Stops come first because a position that gapped through its
stop did not get to wait for a nicer signal.
"""
import runtime  # noqa: F401  — must precede numpy/pandas

import numpy as np
import pandas as pd

import genome as gn

MAX_HOLD_CAP = 60   # matches the genome's max_hold_days ceiling


class Panel:
    """
    The precomputed evaluation surface. Built once, reused by every candidate.

    Memory is the reason this class exists rather than a pile of locals: the
    forward-price matrix is (rows x MAX_HOLD_CAP) float32, and on the Arena VM
    that has to be sized deliberately rather than discovered by an OOM kill.
    """

    def __init__(self, df: pd.DataFrame, max_hold: int = MAX_HOLD_CAP):
        df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
        if "returns" not in df:
            df["returns"] = df.groupby("ticker", observed=True)["close"].pct_change()
        self.df = df
        self.max_hold = int(max_hold)
        self.n = len(df)

        g = df.groupby("ticker", observed=True)["close"]
        # Forward closes for every possible holding day, computed once.
        self.fwd = np.full((self.n, self.max_hold + 1), np.nan, dtype="float32")
        for k in range(1, self.max_hold + 1):
            self.fwd[:, k] = g.shift(-k).to_numpy(dtype="float32")

        self.close = df["close"].to_numpy(dtype="float32")
        self.atr = (df["atr_14"].to_numpy(dtype="float32")
                    if "atr_14" in df else np.full(self.n, np.nan, dtype="float32"))
        self.dv = (df["dollar_volume_20"].to_numpy(dtype="float64")
                   if "dollar_volume_20" in df else np.zeros(self.n))
        self.ticker_codes = df["ticker"].astype("category").cat.codes.to_numpy()
        self.dates = df["date"].to_numpy()

    def memory_gb(self) -> float:
        return (self.fwd.nbytes + self.close.nbytes + self.atr.nbytes) / 1e9


def simulate(genome: dict, panel: Panel, cost_model, position_size_usd: float,
             max_entries: int | None = None) -> dict:
    """
    Run one genome over the panel and return its trade record and net P&L.

    `max_entries` caps how many signals are taken, standing in for the
    portfolio's position limit. A full portfolio simulation with day-by-day slot
    accounting is far more faithful but cannot run hundreds of thousands of
    times; this samples the signals uniformly instead, which preserves the
    strategy's character without the sequential bookkeeping.
    """
    risk = genome["risk"]
    max_hold = min(int(risk.get("max_hold_days", 5)), panel.max_hold)

    entry = gn._as_bool(gn.evaluate(genome["entry"], panel.df)).to_numpy()
    valid = entry & np.isfinite(panel.close) & (panel.close > 0)
    idx = np.flatnonzero(valid)
    if idx.size == 0:
        return _empty_result()

    if max_entries and idx.size > max_entries:
        step = idx.size / max_entries
        idx = idx[(np.arange(max_entries) * step).astype(int)]

    entry_px = panel.close[idx].astype("float64")
    fwd = panel.fwd[idx, 1:max_hold + 1].astype("float64")     # (n_entries, max_hold)

    # --- exit conditions, evaluated across the whole holding window ---------
    atr = panel.atr[idx].astype("float64")
    stop_mult = float(risk.get("stop_atr_multiple", 2.0))
    stop_px = np.where(np.isfinite(atr) & (atr > 0),
                       entry_px - stop_mult * atr,
                       entry_px * 0.92)                        # fallback: 8% stop
    hit_stop = fwd <= stop_px[:, None]

    tp = risk.get("take_profit_pct")
    hit_tp = (fwd >= (entry_px * (1 + float(tp) / 100))[:, None]) if tp else np.zeros_like(hit_stop)

    exit_sig = gn._as_bool(gn.evaluate(genome["exit"], panel.df)).to_numpy()
    exit_fwd = np.zeros_like(hit_stop, dtype=bool)
    for k in range(1, max_hold + 1):
        shifted = np.roll(exit_sig, -k)
        shifted[-k:] = False
        # Only valid where the forward bar belongs to the same ticker.
        same = np.roll(panel.ticker_codes, -k) == panel.ticker_codes
        same[-k:] = False
        exit_fwd[:, k - 1] = shifted[idx] & same[idx]

    triggered = hit_stop | hit_tp | exit_fwd | ~np.isfinite(fwd)
    # argmax finds the first True; where nothing fires we hold to the limit.
    first = np.where(triggered.any(axis=1), triggered.argmax(axis=1), max_hold - 1)

    rows = np.arange(len(idx))
    exit_px = fwd[rows, first]
    # A position whose forward price is missing exits at the last price we have.
    bad = ~np.isfinite(exit_px)
    if bad.any():
        last_good = np.where(np.isfinite(fwd[bad]), fwd[bad], entry_px[bad][:, None])
        exit_px[bad] = last_good[:, -1]

    reason = np.where(hit_stop[rows, first], "stop_loss",
             np.where(hit_tp[rows, first], "take_profit",
             np.where(exit_fwd[rows, first], "exit_rule", "max_hold")))

    shares = position_size_usd / entry_px
    gross = position_size_usd * (exit_px / entry_px - 1)
    costs = cost_model.round_trip(position_size_usd, panel.dv[idx], shares)
    net = gross - costs

    return {
        "n_trades": int(len(idx)),
        "net_pnl_usd": float(net.sum()),
        "gross_pnl_usd": float(gross.sum()),
        "costs_usd": float(np.sum(costs)),
        "win_rate": float((net > 0).mean()),
        "avg_hold_days": float(first.mean() + 1),
        "pnl_series": net,
        "entry_rows": idx,
        "exit_reason": reason,
        "entry_price": entry_px,
        "exit_price": exit_px,
    }


def _empty_result() -> dict:
    return {"n_trades": 0, "net_pnl_usd": 0.0, "gross_pnl_usd": 0.0, "costs_usd": 0.0,
            "win_rate": 0.0, "avg_hold_days": 0.0, "pnl_series": np.array([]),
            "entry_rows": np.array([], dtype=int), "exit_reason": np.array([]),
            "entry_price": np.array([]), "exit_price": np.array([])}


def trades_frame(result: dict, panel: Panel) -> pd.DataFrame:
    """Expand a result into per-trade rows for the ledger."""
    if not result["n_trades"]:
        return pd.DataFrame()
    idx = result["entry_rows"]
    return pd.DataFrame({
        "ticker": panel.df["ticker"].to_numpy()[idx],
        "entry_date": panel.dates[idx],
        "entry_price": result["entry_price"],
        "exit_price": result["exit_price"],
        "net_pnl_usd": result["pnl_series"],
        "exit_reason": result["exit_reason"],
    })
