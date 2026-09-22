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

**Orders fill on the bar AFTER the signal, at its open.** This was the largest
remaining look-ahead in the project. Every entry condition is computed from a
bar's own close — `sma_200`, `rsi_14`, the close itself — and the simulator then
bought at that same close, which is a price you cannot obtain from information
you only have once the session has ended. The same applied to exits: a stop
detected at a close was filled at that close.

So a signal at the close of bar t now fills at the open of t+1, and an exit
triggered at the close of bar t+k fills at the open of t+k+1. That is exactly
what this account can actually do — read the close after the bell, place a market
order, receive the next session's opening print.

**This is where gap risk finally appears.** With close-to-close fills a stop was
a guarantee: the exit was booked at the very price that breached it. Filling at
the next open lets the position gap straight through, which is the real
behaviour of a stop that cannot rest at the broker — and CLAUDE.md has said for
months that overnight gaps are unprotected while the simulator quietly assumed
otherwise. `gap_loss_usd` reports what that costs.
"""
import runtime  # noqa: F401  — must precede numpy/pandas

import numpy as np
import pandas as pd

import logging

import genome as gn

log = logging.getLogger("simulator")

MAX_HOLD_CAP = 60   # matches the genome's max_hold_days ceiling


class Panel:
    """
    The precomputed evaluation surface. Built once, reused by every candidate.

    Memory is the reason this class exists rather than a pile of locals: the
    forward-price matrix is (rows x MAX_HOLD_CAP) float32, and on the Arena VM
    that has to be sized deliberately rather than discovered by an OOM kill.
    """

    def __init__(self, df: pd.DataFrame, max_hold: int = MAX_HOLD_CAP,
                 exit_prices: pd.DataFrame | None = None):
        df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
        if "returns" not in df:
            df["returns"] = df.groupby("ticker", observed=True)["close"].pct_change()
        self.df = df
        self.max_hold = int(max_hold)
        self.n = len(df)

        # Forward closes for every possible holding day, computed once.
        #
        # **Exits must be priced off the UNFILTERED series.** Tradeability floors
        # decide what may be *bought*; a position already open has to be priced
        # wherever it goes. Shifting within the filtered frame silently prices
        # the exit at the last bar above the $5 floor, so a company that falls
        # from $6 to $0.20 books an exit near $5.50 and its collapse never
        # happens. Measured on the top survivor: 11.9% of its 20,000 trades had
        # a truncated forward series, and those returned -0.02% against +15.29%
        # for the rest — the downside was being capped by the filter.
        #
        # This is the same defect already fixed once in the daily pipeline (see
        # storage.price_series); the Lab simulator kept it, and it flatters every
        # strategy that buys falling stocks, which is most of what the search
        # finds.
        self.fwd = np.full((self.n, self.max_hold + 1), np.nan, dtype="float32")
        # Flat unfiltered opens plus, per filtered row, that row's position in
        # them and where its ticker's block ends. A forward OPEN is then one
        # gather at an arbitrary k — which is all the fill logic needs, since it
        # asks for exactly two bars per trade (entry+1 and exit+1) rather than
        # the whole window. Materialising a second (rows x 61) matrix beside the
        # close matrix would have cost another 2.4 GB on an 11.7 GB machine to
        # answer two questions per row.
        self._uopen = np.zeros(0, dtype="float32")
        self._upos = np.full(self.n, -1, dtype="int64")
        self._uend = np.zeros(self.n, dtype="int64")
        if exit_prices is None or exit_prices.empty:
            g = df.groupby("ticker", observed=True)["close"]
            for k in range(1, self.max_hold + 1):
                self.fwd[:, k] = g.shift(-k).to_numpy(dtype="float32")
            self._open_from_filtered(df)
        else:
            self._forward_from_unfiltered(df, exit_prices)

        self.close = df["close"].to_numpy(dtype="float32")
        self.open = (df["open"].to_numpy(dtype="float32")
                     if "open" in df else np.full(self.n, np.nan, dtype="float32"))
        self.atr = (df["atr_14"].to_numpy(dtype="float32")
                    if "atr_14" in df else np.full(self.n, np.nan, dtype="float32"))
        self.dv = (df["dollar_volume_20"].to_numpy(dtype="float64")
                   if "dollar_volume_20" in df else np.zeros(self.n))
        self.ticker_codes = df["ticker"].astype("category").cat.codes.to_numpy()
        self.dates = df["date"].to_numpy()

    def _forward_from_unfiltered(self, df: pd.DataFrame, full: pd.DataFrame) -> None:
        """
        Fill the forward matrix from the complete price series, per ticker.

        Done ticker by ticker with `searchsorted` rather than by building a
        forward matrix over the whole unfiltered frame: the unfiltered set for
        2006-2019 is several times larger than the tradeable one, and a full
        (rows x 61) float32 matrix over it would not fit in this VM's memory.
        """
        # Normalise both date columns to datetime64. The filtered frame arrives
        # from load_training_frame with real datetimes while a direct SQL read
        # gives ISO strings, and searchsorted compares them without complaint
        # right up until it raises.
        full = full.copy()
        full["date"] = pd.to_datetime(full["date"])
        full = full.sort_values(["ticker", "date"])
        by_ticker = {t: (g["date"].to_numpy(dtype="datetime64[ns]"),
                         g["close"].to_numpy(dtype="float32"))
                     for t, g in full.groupby("ticker", observed=True)}
        # One flat opens array, ticker blocks laid end to end, plus each filtered
        # row's index into it. `_uend` is that row's ticker block boundary, so a
        # gather can tell "no such bar" apart from "the next ticker's bar".
        if "open" not in full.columns:
            # Silent fallbacks are how this project reintroduces look-ahead. A
            # frame with no opens can only be filled at the close, which is the
            # bias this module just removed — so it is said out loud rather than
            # discovered later in a number nobody can explain.
            log.warning("exit_prices has no 'open' column — fills fall back to "
                        "CLOSE, which restores the look-ahead this simulator "
                        "exists to avoid")
        blocks, offs, cursor = [], {}, 0
        for t, g in full.groupby("ticker", observed=True):
            o = (g["open"].to_numpy(dtype="float32") if "open" in g
                 else g["close"].to_numpy(dtype="float32"))
            blocks.append(o)
            offs[t] = (cursor, cursor + len(o))
            cursor += len(o)
        self._uopen = (np.concatenate(blocks) if blocks
                       else np.zeros(0, dtype="float32"))

        tick = df["ticker"].astype(str).to_numpy()
        dates = pd.to_datetime(df["date"]).to_numpy(dtype="datetime64[ns]")
        order = np.argsort(tick, kind="stable")
        start = 0
        while start < len(order):
            end = start
            t = tick[order[start]]
            while end < len(order) and tick[order[end]] == t:
                end += 1
            rows = order[start:end]
            entry = by_ticker.get(t)
            if entry is not None:
                fd, fc = entry
                pos = np.searchsorted(fd, dates[rows])
                pos = np.clip(pos, 0, len(fc) - 1)
                for k in range(1, self.max_hold + 1):
                    nxt = pos + k
                    ok = nxt < len(fc)
                    vals = np.full(len(rows), np.nan, dtype="float32")
                    vals[ok] = fc[nxt[ok]]
                    self.fwd[rows, k] = vals
                lo, hi = offs.get(t, (0, 0))
                self._upos[rows] = lo + pos
                self._uend[rows] = hi
            start = end

    def _open_from_filtered(self, df: pd.DataFrame) -> None:
        """
        The same index, built from the filtered frame when no unfiltered set was
        supplied. Used by tests and by callers that genuinely have no wider
        series; production always passes `exit_prices`, because a fill priced
        inside the tradeable frame has the truncation defect fixed above.
        """
        if "open" not in df:
            log.warning("panel frame has no 'open' column — fills fall back to "
                        "CLOSE, restoring look-ahead")
        col = "open" if "open" in df else "close"
        self._uopen = df[col].to_numpy(dtype="float32")
        codes = df["ticker"].astype("category").cat.codes.to_numpy()
        self._upos = np.arange(self.n, dtype="int64")
        # Block end = one past the last row of each ticker's contiguous run.
        ends = np.searchsorted(codes, codes, side="right")
        self._uend = ends.astype("int64")

    def open_at(self, rows: np.ndarray, k: np.ndarray) -> np.ndarray:
        """
        Opening price `k` bars after each row, or NaN where that bar does not
        exist. `k` may differ per row, which is the whole point — an exit fill
        lands wherever that trade's exit happened to trigger.
        """
        if self._uopen.size == 0:
            return np.full(len(rows), np.nan)
        pos = self._upos[rows] + k
        ok = (self._upos[rows] >= 0) & (pos < self._uend[rows])
        out = np.full(len(rows), np.nan)
        if ok.any():
            out[ok] = self._uopen[pos[ok]]
        return out

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

    # Kept before the cap. `n_trades` saturates at `max_entries`, so anything
    # reading it as a turnover measure reports the sampling cap instead of the
    # strategy — every capped strategy looks identically busy. Found 2026-09-22
    # when the random control's turnover distribution came back with p95, p99
    # and max all equal to max_entries / window_years.
    n_signals = int(idx.size)
    capped = bool(max_entries and idx.size > max_entries)
    if capped:
        step = idx.size / max_entries
        idx = idx[(np.arange(max_entries) * step).astype(int)]

    # **Entry fills at the NEXT bar's open, not the signal bar's close.** The
    # signal is computed from the close; that price is only knowable once the
    # session is over, so buying at it is look-ahead. Trades whose next bar does
    # not exist — the last bar of a ticker's history, including a delisting — are
    # dropped rather than filled at the close, because there was no session in
    # which to buy them.
    entry_px = panel.open_at(idx, np.ones(len(idx), dtype="int64"))
    fillable = np.isfinite(entry_px) & (entry_px > 0)
    if not fillable.all():
        idx = idx[fillable]
        entry_px = entry_px[fillable]
        if idx.size == 0:
            return _empty_result()
    signal_px = panel.close[idx].astype("float64")
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
    trigger_px = fwd[rows, first]
    # **Exit fills at the open AFTER the bar that triggered it.** `first` is
    # 0-based over bars t+1..t+max_hold, so the trigger is bar t+first+1 and the
    # fill is t+first+2.
    exit_px = panel.open_at(idx, first.astype("int64") + 2)
    # No such bar — the ticker's series ends inside the holding window. Fall back
    # to the trigger close, then to the last finite forward price. This is the
    # delisting case and it is rare; what matters is that it does NOT fall back
    # to the entry price, which would book a dead company as a flat trade.
    bad = ~np.isfinite(exit_px) | (exit_px <= 0)
    if bad.any():
        fallback = trigger_px[bad]
        still_bad = ~np.isfinite(fallback)
        if still_bad.any():
            last_good = np.where(np.isfinite(fwd[bad]), fwd[bad],
                                 entry_px[bad][:, None])
            fallback = np.where(still_bad, last_good[:, -1], fallback)
        exit_px[bad] = fallback

    # Gap through the stop: the loss taken BELOW the stop level because the fill
    # came at the next open rather than at the breaching close. Close-to-close
    # fills made a stop a guarantee; this is what it is actually worth.
    stopped = hit_stop[rows, first]
    gap = np.where(stopped & np.isfinite(exit_px),
                   np.minimum(exit_px - stop_px, 0.0), 0.0)
    gap_loss_usd = float(np.sum(position_size_usd / entry_px * gap))

    reason = np.where(hit_stop[rows, first], "stop_loss",
             np.where(hit_tp[rows, first], "take_profit",
             np.where(exit_fwd[rows, first], "exit_rule", "max_hold")))

    shares = position_size_usd / entry_px
    gross = position_size_usd * (exit_px / entry_px - 1)
    costs = cost_model.round_trip(position_size_usd, panel.dv[idx], shares)
    net = gross - costs

    # What the old close-fill convention was worth, reported rather than merely
    # removed. `entry_slip_usd` is the P&L difference between filling at the
    # signal close and filling at the next open, summed over every trade: it is
    # the size of the look-ahead this change deletes.
    entry_slip_usd = float(np.sum(position_size_usd * (entry_px / signal_px - 1)))

    return {
        "n_trades": int(len(idx)),
        # Signals the rule actually produced, before uniform subsampling. Use
        # this for turnover, never n_trades.
        "n_signals": n_signals,
        "entries_capped": capped,
        "net_pnl_usd": float(net.sum()),
        "gross_pnl_usd": float(gross.sum()),
        "costs_usd": float(np.sum(costs)),
        "gap_loss_usd": gap_loss_usd,
        "entry_slip_usd": entry_slip_usd,
        "n_stopped": int(stopped.sum()),
        "n_gapped": int(np.sum(gap < 0)),
        "win_rate": float((net > 0).mean()),
        # Bars held = exit bar - entry bar = (first+2) - 1 = first+1. Not
        # first+2: that is the exit bar's OFFSET from the signal, and the signal
        # bar is not held. Overstating it by a day charges the strategy a null
        # for a longer horizon than it ran, and the null grows with horizon — so
        # the error silently taxed every strategy by one day of drift.
        "avg_hold_days": float(first.mean() + 1),
        "pnl_series": net,
        "entry_rows": idx,
        "exit_reason": reason,
        "entry_price": entry_px,
        "exit_price": exit_px,
    }


def _empty_result() -> dict:
    return {"n_trades": 0, "n_signals": 0, "entries_capped": False, "net_pnl_usd": 0.0, "gross_pnl_usd": 0.0, "costs_usd": 0.0,
            "gap_loss_usd": 0.0, "entry_slip_usd": 0.0, "n_stopped": 0, "n_gapped": 0,
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
