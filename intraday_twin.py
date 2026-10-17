"""
Intraday Twin-ETF Runner (Addendum G, owner 2026-10-16): the same Runner machinery on the bull/bear ETF pairs.

Idea: trade the INDEX direction instead of a stock. For each pair (bull ETF, inverse ETF) the INDEX ETF (the bull leg)
decides the direction, and the Runner buys the matching leg, LONG: momentum going UP buys the bull ETF; momentum going
DOWN buys the inverse ETF (the "short" is an ordinary long position in the inverse fund; nothing is ever sold short).
Everything else is the stock Runner: the same ExecutionEngine / RiskEngine / LiveBroker path, the same monotone trailing
stop on the bought leg's OWN price, the same manager, ledger, flatten and failure handling. It never holds both legs.

v0 IS PRE-DECLARED AND UNCALIBRATED, like the stock rule. There is no evidence that intraday index momentum pays after
costs; this runner exists to find out, and every qualifying signal is logged for the evaluation.

The index ETF's direction (thresholds scaled by its leverage where noted):
    UP    price above a rising VWAP, 15-minute return >= +min_ret15 x leverage, price above the highest high of the
          30-to-4-minutes-ago window (a NEW breakout), the last 3 minutes not reversing
    DOWN  the mirror: below a falling VWAP, return <= -min_ret15 x leverage, price below the lowest low of that window
    both  volume over the last 15 minutes >= 1.2x the session's pace; not extended (move from the open under 1.5 daily
          ranges); data fresh.
The leg to be BOUGHT must only be tradeable: fresh bars, estimated round-trip cost small, and the plausible 15-minute
move at least 2x the cost. It does not have to pass the momentum tests on its own price (the index decides).
Stops: initial and trailing distance = trail_pct x leverage (0.35 % for a 1x ETF, 0.70 % for a 2x ETF) of the bought leg's
price: an index ETF moves a fraction of a stock's intraday range, so a 1 % stop would almost never trigger.

    config.yaml `intraday_twin:` (stage OFF | SHADOW | LIVE, slots, limits, pairs)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import math

import numpy as np
import pandas as pd

import intraday_momentum as mom
import intraday_runner as ir
import intraday_stops as st

BLOCK = "intraday_twin"
KEY_TWIN = "intraday:twin_etf_runner"

PAIRS = [("SPY", "SH", 1), ("SSO", "SDS", 2), ("QQQ", "PSQ", 1), ("QLD", "QID", 2), ("IWM", "RWM", 1)]

TWIN_DEFAULTS = {
    "stage": "OFF", "slots": [5], "position_dollars": 20.0,
    "max_entries_per_session": 3, "max_simultaneous": 1,
    "max_daily_loss_dollars": 1.0, "max_loss_per_trade_dollars": 0.50,
    "min_aum": 1e8, "min_dollar_volume": 2e7,
    "stop": {"mode": "pct", "initial_pct": 0.35, "trail_pct": 0.35, "max_hold_minutes": 60, "flatten_hhmm": "15:45"},
    "scanner": {"min_ret15": 0.0010, "min_vol_accel": 1.2, "max_ext": 1.5, "max_cost": 0.0015, "min_capacity_over_cost": 2.0,
                "slippage_round_trip": 0.0002, "max_bar_age_s": 150, "min_bars": 31},
}


def settings(cfg: dict) -> dict:
    s = ir.settings({BLOCK: {**TWIN_DEFAULTS, **((cfg or {}).get(BLOCK) or {})}}, BLOCK)
    for k in ("max_simultaneous", "max_daily_loss_dollars", "min_aum", "min_dollar_volume"):
        s[k] = ((cfg or {}).get(BLOCK) or {}).get(k, TWIN_DEFAULTS[k])
    s["scanner"] = {**TWIN_DEFAULTS["scanner"], **(((cfg or {}).get(BLOCK) or {}).get("scanner") or {})}
    s["stop"] = {**TWIN_DEFAULTS["stop"], **(((cfg or {}).get(BLOCK) or {}).get("stop") or {})}
    s["slots"] = ((cfg or {}).get(BLOCK) or {}).get("slots", TWIN_DEFAULTS["slots"])
    return s


def pairs_of(cfg: dict) -> list:
    given = ((cfg or {}).get(BLOCK) or {}).get("pairs")
    return [(p[0], p[1], int(p[2])) for p in given] if given else list(PAIRS)


def leverage_map(cfg: dict) -> dict:
    out = {}
    for bull, bear, lev in pairs_of(cfg):
        out[bull] = out[bear] = lev
    return out


def twin_universe(conn, cfg: dict) -> list:
    """Every leg of every configured pair that clears the size and liquidity floors (ETF 'market cap' is AUM)."""
    import market_caps
    s = settings(cfg)
    out = []
    for bull, bear, _ in pairs_of(cfg):
        for t in (bull, bear):
            cap, _src = market_caps.lookup(conn, t)
            r = conn.execute("SELECT dollar_volume_20 FROM features WHERE ticker=? AND dollar_volume_20 IS NOT NULL ORDER BY date DESC LIMIT 1", (t,)).fetchone()
            if cap and cap >= s["min_aum"] and r and r[0] >= s["min_dollar_volume"]:
                out.append(t)
    return out


def index_direction(f: dict | None, lev: int, s: dict):
    """The index ETF's momentum direction: ("UP"|"DOWN"|None, [reasons it is neither])."""
    sc = s["scanner"]
    if f is None:
        return None, ["too few bars"]
    r = []
    if f["age_s"] > sc["max_bar_age_s"]:
        r.append("stale data")
    if not f["vol_accel"] >= sc["min_vol_accel"]:
        r.append("no volume acceleration")
    if f["ext"] == f["ext"] and not abs(f["ext"]) <= sc["max_ext"]:
        r.append("extended")
    if r:
        return None, r
    need = sc["min_ret15"] * lev
    if f["dist_vwap"] > 0 and f["vwap_slope"] > 0 and f["ret15"] >= need and f["breakout"] > 0 and f["momentum_intact"]:
        return "UP", []
    if f["dist_vwap"] < 0 and f["vwap_slope"] < 0 and f["ret15"] <= -need and f["breakdown"] < 0 and f["momentum_down"]:
        return "DOWN", []
    return None, ["no index momentum"]


def leg_reasons(f: dict | None, s: dict) -> list:
    """Why the leg to be bought cannot be traded (it need not show momentum of its own)."""
    sc = s["scanner"]
    if f is None:
        return ["target leg: too few bars"]
    r = []
    if f["age_s"] > sc["max_bar_age_s"]:
        r.append("target leg: stale data")
    if f["cost"] > sc["max_cost"]:
        r.append("target leg: estimated cost too high")
    if not f["move_capacity"] >= sc["min_capacity_over_cost"] * f["cost"]:
        r.append("target leg: expected move too small for cost")
    return r


def scan_pairs(bars_by_ticker: dict, meta: dict, now, cfg: dict) -> dict:
    """Candidates in the shape the Runner expects. The index ETF (bull leg) sets the direction; UP buys the bull leg and
    DOWN buys the inverse leg. One candidate per pair, ranked by the index's 15-minute move in units of its own
    15-minute volatility (comparable across 1x and 2x pairs)."""
    s = settings(cfg)
    lev = leverage_map(cfg)
    ms = {**mom.DEFAULTS, **s["scanner"]}
    hist, out = {}, []

    def feats(t):
        b = bars_by_ticker.get(t)
        if b is None:
            return None
        m = meta.get(t, {})
        return mom.features(b, None, m.get("daily_atr_pct"), m.get("dollar_volume_20"), now, ms)

    for bull, bear, _ in pairs_of(cfg):
        fi = feats(bull)
        direction, why = index_direction(fi, lev.get(bull, 1), s)
        if direction is None:
            hist[why[0]] = hist.get(why[0], 0) + 1
            continue
        target = bull if direction == "UP" else bear
        ft = fi if target == bull else feats(target)
        why = leg_reasons(ft, s)
        if why:
            hist[why[0]] = hist.get(why[0], 0) + 1
            continue
        vol15 = fi["atr1m_pct"] * math.sqrt(15)
        out.append({**ft, "ticker": target, "pair": f"{bull}/{bear}", "lev": lev.get(target, 1), "direction": direction,
                    "index_ret15": fi["ret15"], "score": float(abs(fi["ret15"]) / vol15) if vol15 else 0.0})
    out.sort(key=lambda c: -c["score"])
    return {"candidates": out, "rejected": hist, "scanned": len(bars_by_ticker), "calibrated": False}


def meta_for_etfs(conn, tickers: list) -> dict:
    return ir.meta_for(conn, tickers)


class TwinRunner(ir.Runner):
    BLOCK = BLOCK
    KEY = KEY_TWIN

    def __init__(self, conn, cfg, engine, quote_fn, bars_fn, **kw):
        kw.setdefault("universe_fn", lambda: twin_universe(conn, cfg))
        kw.setdefault("meta_fn", lambda ts: meta_for_etfs(conn, ts))
        super().__init__(conn, {**cfg, BLOCK: {**TWIN_DEFAULTS, **(cfg.get(BLOCK) or {})}}, engine, quote_fn, bars_fn, **kw)
        # the scanner/stop settings come from this module, not the stock Runner's defaults
        self.s = settings(cfg)
        self.lev = leverage_map(cfg)

    def stop_for(self, symbol):
        lev = self.lev.get(symbol or "", 1)
        c = self.s["stop"]
        return st.StopConfig(mode="pct", initial_pct=c["initial_pct"] * lev, trail_pct=c["trail_pct"] * lev,
                             max_hold_minutes=c["max_hold_minutes"], flatten_hhmm=c["flatten_hhmm"])

    def scan(self, bars, spy, now):
        return scan_pairs({t: b for t, b in bars.items()}, self.meta, now, self.cfg)
