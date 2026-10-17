"""
Intraday Momentum Runner (Addendum G): the scanner and the v0 entry model. Pure functions: bars in, candidates out.

v0 IS A PRE-DECLARED, TRANSPARENT RULE, NOT A CALIBRATED FORECAST. Its thresholds are fixed here (and mirrored in
config.yaml `intraday:`), recorded with every signal, and not tuned to any result. It makes no claim that continuation
is profitable: the project's own same-day shadow evidence (288 trades, momentum-type rules negative) says otherwise.
What it does claim is the plan's structure: do not buy because a stock is up; require the move to be confirmed by
relative strength, volume acceleration, a breakout, price above a rising VWAP, not extended, with room to move
against costs, in a market that is not weak, on fresh data.

Features at decision time t use only completed 1-minute bars up to t (a truncation test pins this).

  ret15 / ret30       return over the last 15 / 30 bars
  rs15                ret15 minus SPY's ret15
  vwap, dist_vwap     session VWAP and distance from it; vwap_slope = VWAP now vs 10 bars ago
  vol_accel           volume of the last 15 bars / the session's average 15-bar volume so far
  breakout            close vs the highest high of bars t-30..t-4 (the move must be NEW, not the last three bars)
  ext                 move from the open in units of the stock's typical DAILY range (daily ATR %)
  move_capacity       1-minute range volatility x sqrt(15): what a 15-minute move could plausibly be
  cost                estimated round trip (spread tier from daily dollar volume + slippage)

The rank among qualifying names is the mean cross-sectional percentile of relative strength, volume acceleration,
breakout strength, (less) extension and (lower) cost. It orders candidates; it is not an expected return, and every
signal is logged as UNCALIBRATED so that the SHADOW record can calibrate it.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import math

import numpy as np
import pandas as pd

import costs

DEFAULTS = {
    "min_bars": 31,
    "max_bar_age_s": 150,            # freshness of the newest completed bar
    "min_ret15": 0.0015,
    "min_rs15": 0.0010,
    "min_vol_accel": 1.5,
    "max_ext": 1.0,                  # move from the open, in daily ATRs
    "max_pct_open": 0.06,
    "max_cost": 0.0020,              # estimated round trip, fraction of price
    "slippage_round_trip": 0.0004,
    "min_capacity_over_cost": 3.0,
    "spy_min_pct_open": -0.004,
    "spy_max_below_vwap": 0.001,
}


def settings(cfg: dict | None) -> dict:
    return {**DEFAULTS, **((cfg or {}).get("scanner") or {})}


def _vwap_series(b: pd.DataFrame) -> pd.Series:
    tp = (b["high"] + b["low"] + b["close"]) / 3.0
    pv = (tp * b["volume"]).cumsum()
    v = b["volume"].cumsum().replace(0, np.nan)
    return pv / v


def features(bars: pd.DataFrame, spy: pd.DataFrame | None, daily_atr_pct: float | None, dollar_volume_20: float | None,
             now=None, s: dict | None = None) -> dict | None:
    """Features from today's completed bars (columns ts, open, high, low, close, volume), or None when too short."""
    s = s or DEFAULTS
    n = len(bars)
    if n < s["min_bars"]:
        return None
    c, h, l, o, v = (bars[k].to_numpy(float) for k in ("close", "high", "low", "open", "volume"))
    price, op = c[-1], o[0]
    vw = _vwap_series(bars)
    vwap, vwap10 = float(vw.iloc[-1]), float(vw.iloc[-11])
    tot = v.sum()
    f = {
        "price": float(price), "pct_open": float(price / op - 1),
        "ret15": float(price / c[-16] - 1), "ret30": float(price / c[-31] - 1),
        "vwap": vwap, "dist_vwap": float(price / vwap - 1) if vwap == vwap else float("nan"),
        "vwap_slope": float(vwap / vwap10 - 1) if vwap10 == vwap10 and vwap10 else float("nan"),
        "vol_accel": float(v[-15:].sum() / (tot / (n / 15.0))) if tot > 0 else float("nan"),
        "breakout": float(price / h[-31:-3].max() - 1),
        "breakdown": float(price / l[-31:-3].min() - 1),          # negative when price is below the lowest low of t-30..t-4
        "momentum_down": bool(price <= c[-4]),
        "orb_break": bool(n > 30 and price > h[:30].max()),
        "atr1m_pct": float(np.mean((h[-14:] - l[-14:]) / c[-14:])),
        "momentum_intact": bool(price >= c[-4]),
        "bars": n, "last_bar": bars["ts"].iloc[-1],
    }
    f["ext"] = float(f["pct_open"] / daily_atr_pct) if daily_atr_pct else float("nan")
    rt = (float(costs.estimate_spread_pct(float(dollar_volume_20))) if dollar_volume_20 else 0.003) + s["slippage_round_trip"]
    f["cost"] = rt
    f["move_capacity"] = float(f["atr1m_pct"] * math.sqrt(15))
    if spy is not None and len(spy) >= 16:
        sc = spy["close"].to_numpy(float)
        f["spy_ret15"] = float(sc[-1] / sc[-16] - 1)
        f["spy_pct_open"] = float(sc[-1] / spy["open"].iloc[0] - 1)
        sv = _vwap_series(spy)
        f["spy_dist_vwap"] = float(sc[-1] / sv.iloc[-1] - 1)
    else:
        f["spy_ret15"] = f["spy_pct_open"] = f["spy_dist_vwap"] = float("nan")
    f["rs15"] = float(f["ret15"] - f["spy_ret15"]) if f["spy_ret15"] == f["spy_ret15"] else float("nan")
    if now is not None:
        f["age_s"] = float((pd.Timestamp(now) - (f["last_bar"] + pd.Timedelta(minutes=1))).total_seconds())
    else:
        f["age_s"] = 0.0
    return f


def reject_reasons(f: dict | None, s: dict | None = None) -> list:
    """Every reason a candidate is refused; an empty list means it qualifies."""
    s = s or DEFAULTS
    if f is None:
        return ["too few bars"]
    r = []
    if f["age_s"] > s["max_bar_age_s"]:
        r.append("stale data")
    if not (f["dist_vwap"] > 0 and f["vwap_slope"] > 0):
        r.append("below or falling VWAP")
    if not f["ret15"] >= s["min_ret15"]:
        r.append("weak 15-minute return")
    if not f["rs15"] >= s["min_rs15"]:
        r.append("weak relative strength")
    if not f["breakout"] > 0:
        r.append("no new breakout")
    if not f["vol_accel"] >= s["min_vol_accel"]:
        r.append("no volume acceleration")
    if not (f["ext"] <= s["max_ext"] and f["pct_open"] <= s["max_pct_open"]):
        r.append("extended")
    if not f["momentum_intact"]:
        r.append("momentum fading")
    if f["cost"] > s["max_cost"]:
        r.append("estimated cost too high")
    if not f["move_capacity"] >= s["min_capacity_over_cost"] * f["cost"]:
        r.append("expected move too small for cost")
    if not (f["spy_pct_open"] >= s["spy_min_pct_open"] and f["spy_dist_vwap"] >= -s["spy_max_below_vwap"]):
        r.append("weak market")
    return r


def scan(bars_by_ticker: dict, spy: pd.DataFrame | None, meta: dict, now=None, cfg: dict | None = None) -> dict:
    """bars_by_ticker {ticker: DataFrame}; meta {ticker: {"daily_atr_pct": x, "dollar_volume_20": y}}.
    Returns {"candidates": [...best first...], "rejected": {reason: count}, "scanned": n}."""
    s = settings(cfg)
    rows, hist = [], {}
    for t, b in bars_by_ticker.items():
        m = meta.get(t, {})
        f = features(b, spy, m.get("daily_atr_pct"), m.get("dollar_volume_20"), now, s)
        why = reject_reasons(f, s)
        for w in why[:1] or []:
            hist[w] = hist.get(w, 0) + 1
        if not why:
            rows.append({"ticker": t, **f})
    if rows:
        d = pd.DataFrame(rows)
        pr = lambda col, asc=True: d[col].rank(pct=True, ascending=asc)       # noqa: E731
        d["score"] = (pr("rs15") + pr("vol_accel") + pr("breakout") + pr("ext", False) + pr("cost", False)) / 5.0
        d = d.sort_values("score", ascending=False)
        cands = d.to_dict("records")
    else:
        cands = []
    return {"candidates": cands, "rejected": hist, "scanned": len(bars_by_ticker), "calibrated": False}
