"""Stage K3: the single simulation engine for low-turnover daily crypto rules.

Fill convention: a signal is evaluated on the CLOSE of bar i and fills at the
OPEN of bar i+1 -- never at c[i]. A stop is checked intrabar against the low;
if the bar opens below the stop the fill is the open (gap-through), otherwise
the fill is the stop price, i.e. min(open, stop).

Costs: hs is a fraction charged per side, so a round trip pays it twice:
    net   = exit_px * (1 - hs) / (entry_px * (1 + hs)) - 1
    gross = exit_px / entry_px - 1
"""
import runtime  # noqa: F401  (must precede numpy: thread limits are read at import)

import numpy as np

FAMILIES = ("trend_sma", "tsmom", "breakout")


def atr(h, l, c, n=14):
    """Average true range over the trailing n bars; NaN until n bars exist."""
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    c = np.asarray(c, dtype=float)
    N = len(c)
    out = np.full(N, np.nan)
    if N == 0 or n <= 0:
        return out
    tr = np.empty(N, dtype=float)
    tr[0] = h[0] - l[0]
    if N > 1:
        prev = c[:-1]
        tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev), np.abs(l[1:] - prev)])
    # Cumulative sum keeps this O(N) rather than O(N*n) for long lookbacks.
    cs = np.concatenate(([0.0], np.cumsum(tr)))
    if N >= n:
        out[n - 1:] = (cs[n:] - cs[:N - n + 1]) / n
    return out


def signals(o, h, l, c, g):
    """Entry/exit/defined boolean arrays. Undefined bars are False in both."""
    o = np.asarray(o, dtype=float)
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    c = np.asarray(c, dtype=float)
    N = len(c)
    fam = g["family"]
    n = int(g["n"])
    entry = np.zeros(N, dtype=bool)
    exit_ = np.zeros(N, dtype=bool)
    defined = np.zeros(N, dtype=bool)
    if fam not in FAMILIES or n < 1:
        return entry, exit_, defined

    if fam in ("trend_sma", "tsmom"):
        if fam == "trend_sma":
            # mean(c[i-n+1..i]) via a rolling sum; defined for i >= n-1.
            cs = np.concatenate(([0.0], np.cumsum(c)))
            for i in range(n - 1, N):
                defined[i] = True
                entry[i] = c[i] > (cs[i + 1] - cs[i - n + 1]) / n
        else:
            for i in range(n, N):
                defined[i] = True
                entry[i] = (c[i] / c[i - n] - 1.0) > 0.0
        exit_ = defined & ~entry
    else:
        m = max(2, n // 2)
        for i in range(n, N):
            defined[i] = True
            entry[i] = c[i] > np.max(h[i - n:i])
        for i in range(m, N):
            # The exit rule has its own definition window; a bar can be exit-
            # defined before it is entry-defined, so `defined` is the union.
            defined[i] = True
            exit_[i] = c[i] < np.min(l[i - m:i])
    return entry, exit_, defined


def simulate(o, h, l, c, g, hs, start_i=0, close_at_end=True):
    """Walk the bars once. Returns {"trades": [...], "open": None or dict}."""
    o = np.asarray(o, dtype=float)
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    c = np.asarray(c, dtype=float)
    N = len(c)
    entry, exit_, defined = signals(o, h, l, c, g)
    a = atr(h, l, c, int(g.get("atr_n", 14)))
    stop_atr = float(g["stop_atr"])

    trades = []
    open_pos = None
    waiting = False
    i = 0
    while i < N:
        if open_pos is None:
            if waiting:
                # Cleared at the first bar whose entry signal is False (defined).
                if defined[i] and not entry[i]:
                    waiting = False
            if (not waiting and i >= start_i and entry[i] and np.isfinite(a[i])
                    and i + 1 < N):
                e = i + 1
                open_pos = {"entry_i": e, "entry_px": float(o[e]),
                            "stop": float(o[e] - stop_atr * a[i])}
                i = e
                continue
            i += 1
            continue

        # In a position: stop first (intrabar), then the signal exit.
        if l[i] <= open_pos["stop"]:
            px = min(float(o[i]), open_pos["stop"])
            trades.append(_trade(open_pos, i, px, "stop", hs))
            open_pos = None
            waiting = True
            i += 1
            continue
        if exit_[i] and i + 1 < N:
            x = i + 1
            trades.append(_trade(open_pos, x, float(o[x]), "signal", hs))
            open_pos = None
            # Entry checking resumes with the signal at bar x, so the earliest
            # possible fill is o[x+1]; the loop's i += 1 lands on x.
            i += 1
            continue
        i += 1

    if open_pos is not None and close_at_end:
        trades.append(_trade(open_pos, N - 1, float(c[N - 1]), "end", hs))
        open_pos = None
    return {"trades": trades, "open": open_pos}


def _trade(pos, exit_i, exit_px, reason, hs):
    entry_px = pos["entry_px"]
    return {
        "entry_i": pos["entry_i"],
        "exit_i": exit_i,
        "entry_px": entry_px,
        "exit_px": exit_px,
        "stop": pos["stop"],
        "reason": reason,
        "bars": exit_i - pos["entry_i"],
        "gross": exit_px / entry_px - 1.0,
        "net": exit_px * (1.0 - hs) / (entry_px * (1.0 + hs)) - 1.0,
    }


def null_per_trade(o, trades, hs, lo_i, hi_i):
    """Mean net return of a random entry held for the same number of bars."""
    o = np.asarray(o, dtype=float)
    per_trade = []
    for t in trades:
        bars = max(1, int(t["bars"]))
        hi = hi_i - bars
        if hi < lo_i:
            continue
        js = np.arange(lo_i, hi + 1)
        if len(js) == 0:
            continue
        vals = o[js + bars] * (1.0 - hs) / (o[js] * (1.0 + hs)) - 1.0
        per_trade.append(float(np.mean(vals)))
    if not per_trade:
        return None
    return float(np.mean(per_trade))


def buy_and_hold(o, c, lo_i, hi_i, hs):
    """Net return of buying at o[lo_i] and selling at c[hi_i]."""
    o = np.asarray(o, dtype=float)
    c = np.asarray(c, dtype=float)
    return float(c[hi_i] * (1.0 - hs) / (o[lo_i] * (1.0 + hs)) - 1.0)


def summarize(trades):
    if not trades:
        return {"trades": 0, "gross_per_trade": None, "net_per_trade": None,
                "win_rate": None, "mean_bars": None}
    gross = np.array([t["gross"] for t in trades], dtype=float)
    net = np.array([t["net"] for t in trades], dtype=float)
    bars = np.array([t["bars"] for t in trades], dtype=float)
    return {
        "trades": len(trades),
        "gross_per_trade": float(np.mean(gross)),
        "net_per_trade": float(np.mean(net)),
        "win_rate": float(np.mean(net > 0)),
        "mean_bars": float(np.mean(bars)),
    }
