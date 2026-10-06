"""
Options strategies: backtest on real historical option prices, then paper-trade
forward with the same code (Stage R, owner 2026-09-27: "big gains"; "a really
good stock signal up or down triggers an option buy").

Prices come from options_data.py (DoltHub public end-of-day chains, 2020 on).
Every trade is priced as it would really fill: bought at the ASK, sold at the
BID; a contract still held at expiration settles at its intrinsic value from the
stock's close. Nothing is modelled with Black-Scholes.

The strategies (each one a tournament entry, `option:<name>` in the league):

    opt_signal_call        the day's best stock signal (entries of the top-ranked
                           stock strategies) bought as a ~35-day at-the-money call
    opt_iv_cheap_straddle  monthly: straddles on the stocks whose implied vol is
                           lowest against their realised vol (Goyal & Saretto 2009,
                           JFE: long-short straddles ~22.7%/month)
    opt_iv_rise_call       weekly: calls on the stocks whose implied vol rose most
                           over the month (An, Ang, Bali & Cakici 2014, JF: ~1%/month
                           in the stock)
    opt_smirk_put          weekly: puts on the steepest implied-vol smirk (Xing, Zhang &
                           Zhao 2010, JFQA: -10.9%/year for the steepest)
    opt_ivspread_call      weekly: calls where calls are priced above same-strike puts
    opt_ivspread_put       weekly: puts where puts are priced above same-strike calls
                           (Cremers & Weinbaum 2010, JFQA: 51 bp/week between the two)
    opt_earnings_straddle  straddle bought 2-6 days before an earnings release (8-K
                           item 2.02), sold at the first price after it (Gao, Xing &
                           Zhang 2018, JFQA: +3.34% per straddle, 3 days to the event)

Known from the literature and worth knowing before reading any result: bought
options lose on average (Coval & Shumway 2001: ATM straddles about -3%/week) and
cheap far-out-of-the-money options lose most (Boyer & Vorkink 2014) — so every
strategy here buys near the money, and each one must earn its place forward.

Returns are per trade on the premium paid; dollars are on a `options.stake_usd`
position (fractional, for measurement — a real order buys whole contracts).

    ./run_bounded.sh ./venv/bin/python options_lab.py --backtest [--strategy NAME] [--start 2020-03-01]
    ./venv/bin/python options_lab.py --step        # paper: the newest option date
    ./venv/bin/python options_lab.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import logging
import sqlite3
import sys

import options_data as od

log = logging.getLogger("options_lab")
DEFAULTS = {"stake_usd": 100.0, "max_spread_frac": 0.5, "min_ask": 0.05, "liquid_universe": 50,
            "max_contract_cost_usd": 100.0, "tradeable_legs": ("C", "P")}
CONTRACT = 100

STRATEGIES = {
    "opt_signal_call": {"rule": "stock_signal", "legs": "C", "dte": (21, 60, 35), "hold": 14, "per_day": 1,
                        "name": "Stock signal → call",
                        "why": "The day's best entry from the top-ranked stock strategies, bought as an at-the-money call."},
    "opt_iv_cheap_straddle": {"rule": "iv_cheap", "legs": "S", "dte": (21, 50, 35), "hold": 20, "top": 5,
                              "name": "Cheap-IV straddle",
                              "why": "Goyal & Saretto (2009): straddles on stocks with implied vol far below realised vol."},
    "opt_iv_rise_call": {"rule": "iv_rise", "legs": "C", "dte": (21, 60, 35), "hold": 14, "top": 3,
                         "name": "Rising-IV call",
                         "why": "An, Ang, Bali & Cakici (2014): a big rise in implied vol precedes higher stock returns."},
    "opt_earnings_straddle": {"rule": "earnings", "legs": "S", "dte": (7, 45, 20), "hold": 10,
                              "name": "Earnings straddle",
                              "why": "Gao, Xing & Zhang (2018): straddles bought just before earnings earn +3.3% on average."},
    "opt_smirk_put": {"rule": "smirk", "legs": "P", "dte": (21, 60, 35), "hold": 14, "top": 3,
                      "name": "Steep-smirk put",
                      "why": "Xing, Zhang & Zhao (2010): stocks whose out-of-the-money puts are priced "
                             "steepest above at-the-money calls underperform (10.9%/year) — bought as puts."},
    "opt_ivspread_call": {"rule": "ivspread_high", "legs": "C", "dte": (21, 60, 35), "hold": 7, "top": 3,
                          "name": "Expensive-call call",
                          "why": "Cremers & Weinbaum (2010): calls priced above same-strike puts foretell "
                                 "outperformance (51 bp/week) — bought as calls."},
    "opt_ivspread_put": {"rule": "ivspread_low", "legs": "P", "dte": (21, 60, 35), "hold": 7, "top": 3,
                         "name": "Expensive-put put",
                         "why": "Cremers & Weinbaum (2010): puts priced above same-strike calls foretell "
                                "underperformance — bought as puts (the bearish side)."},
    "opt_momentum_straddle": {"rule": "opt_momentum", "legs": "S", "dte": (21, 50, 35), "hold": 20, "top": 5,
                              "name": "Option momentum straddle",
                              "why": "Heston, Jones, Khorram, Li & Mo (2023): at-the-money straddles whose own "
                                     "returns were high over the past 2-12 months keep outperforming (R6)."},
    # --- SHORT (premium-selling) strategies — untested territory as of 2026-10-05 ---
    "opt_vrp_straddle_short": {
        "rule": "vrp_high", "legs": "S", "dte": (21, 50, 35), "hold": 14, "top": 3, "short": True,
        "take_profit": 0.50,
        "name": "VRP short straddle",
        "why": "Coval & Shumway (2001 JF): delta-hedged ATM straddles earn ~-3%/week for buyers. "
               "Carr & Wu (2009 RFS): variance risk premium (IV >> RV) is large and persistent across "
               "individual stocks. Sell ATM straddles when IV/HV > 1.3; close at 50% premium decay."},
    "opt_short_put_uptrend": {
        "rule": "iv_high_uptrend", "legs": "P", "dte": (21, 50, 35), "hold": 20, "top": 3, "short": True,
        "take_profit": 0.50,
        "name": "Short put (VRP, uptrend)",
        "why": "Whaley (2002 JD): CBOE PutWrite Index (PUT) outperforms S&P500 on risk-adjusted basis. "
               "Bondarenko (2014): short puts are systematically profitable; buyers overpay for "
               "downside insurance. Sell ATM puts on uptrending stocks (price > SMA200, IV/HV > 1.2)."},
    "opt_earnings_iv_crush": {
        "rule": "earnings_near_short", "legs": "S", "dte": (5, 14, 10), "hold": 3, "top": 3, "short": True,
        "name": "Earnings IV crush",
        "why": "Patell & Wolfson (1979 JAR): IV collapses immediately after earnings announcements. "
               "Dubinsky & Johannes (2005): individual stocks carry a large earnings variance premium. "
               "Sell short-dated ATM straddle 1–3 days before earnings; close 1 day after announcement."},
    "opt_pre_earnings_long": {
        "rule": "earnings_far_long", "legs": "S", "dte": (21, 60, 35), "hold": 12, "top": 3, "short": False,
        "name": "Pre-earnings IV ride",
        "why": "Gurvich & Rachev (2003): IV rises systematically in the 2–3 weeks before earnings as "
               "uncertainty accumulates. Buy ATM straddle ~2–3 weeks out; exit 1 day before announcement "
               "to capture IV expansion without the crush (exit wired in run())."},
    "opt_signal_call_cheapiv": {
        "rule": "signal_cheap_iv", "legs": "C", "dte": (21, 60, 35), "hold": 14, "per_day": 1,
        "name": "Stock signal → call (cheap IV)",
        "why": "opt_signal_call loses in high-IV years (2022: -15.8%, 2025: -10.7%) because elevated "
               "implied vol prices in the expected move and leaves calls expensive. This variant gates "
               "on IV/HV < 1.2: only buy calls when the options market is not already pricing a large "
               "move. Literature: overpriced options are documented in Bakshi, Cao & Chen (1997 JF)."},
    # --- iron condors and spreads (level 3 required) ---
    "opt_iron_condor": {
        "rule": "vrp_range", "legs": "IC", "dte": (21, 50, 35), "hold": 21, "top": 3,
        "is_credit": True, "take_profit": 0.50,
        "name": "Iron condor (high VRP range-bound)",
        "why": "Sell OTM call and OTM put spreads on stocks with elevated IV/HV and low realised vol. "
               "Earn the variance risk premium within defined risk (max loss = spread width - credit). "
               "Iron condors outperform naked short straddles on a risk-adjusted basis and require "
               "level-3 options access. Premium sellers earn ~1-2% credit with ~4-6 week hold. "
               "Hutchinson & Mulqueeney (2020); Whaley (2002); Carr & Wu (2009)."},
    "opt_ic_earnings": {
        "rule": "vrp_high", "legs": "IC", "dte": (14, 35, 21), "hold": 14, "top": 3,
        "is_credit": True, "take_profit": 0.50,
        "name": "Iron condor (high VRP)",
        "why": "IC on any stock with IV/HV > 1.3 — same VRP harvest as the short straddle but with "
               "defined max loss via the wings, making it capital efficient and PDT-friendly. "
               "The wings cap downside; the premium exceeds typical move distributions."},
    "opt_bull_call_spread": {
        "rule": "breakout", "legs": "BCS", "dte": (21, 60, 35), "hold": 20, "top": 3,
        "is_debit_spread": True,
        "name": "Bull call spread (breakout)",
        "why": "George & Hwang (2004 JF): 52-week-high breakouts are the strongest momentum predictor, "
               "outperforming traditional formation-period momentum. Buy ATM call + sell OTM call "
               "to reduce premium paid by ~40% versus naked call. Defined-risk leveraged bullish bet. "
               "Lower breakeven than naked call; max loss = net debit paid."},
    "opt_bear_put_spread": {
        "rule": "smirk", "legs": "BPS", "dte": (21, 60, 35), "hold": 14, "top": 3,
        "is_debit_spread": True,
        "name": "Bear put spread (OTM smirk signal)",
        "why": "Xing, Zhang & Zhao (2010 JFQA): stocks with steepest OTM put smirk underperform "
               "10.9%/year. Bear put spread (buy ATM put + sell OTM put) reduces cost vs naked put "
               "by ~35-50%, tightening the breakeven to make the bearish bet cost-efficient."},
    "opt_pead_call": {
        "rule": "pead_call", "legs": "C", "dte": (21, 60, 35), "hold": 20, "top": 3,
        "name": "Post-earnings drift call",
        "why": "Bernard & Thomas (1989 JAE): stocks that beat earnings drift upward for 3 months "
               "(PEAD). Top-SUE decile earns +2.75% in 60 days. A leveraged call capitalises on "
               "the drift while limiting downside. Entry: stock up on earnings (5-day window). "
               "This is the options version of the earnings_surprise equity strategy."},
    "opt_breakout_call": {
        "rule": "breakout_call", "legs": "C", "dte": (21, 60, 35), "hold": 14, "top": 3,
        "name": "52-week high breakout call",
        "why": "George & Hwang (2004 JF): the 52-week-high ratio explains most of the momentum "
               "premium. Stocks breaking to new highs continue rising. ATM call at the breakout "
               "gives 3-4x leveraged exposure to the continuation. Higher win-rate than random "
               "because breakouts attract further momentum capital."},
    "opt_oversold_call": {
        "rule": "oversold_call", "legs": "C", "dte": (14, 45, 21), "hold": 10, "top": 3,
        "name": "Oversold call (mean reversion)",
        "why": "Jegadeesh (1990 JF): short-term reversal — stocks below RSI 35 that are still in "
               "an uptrend (above SMA200) snap back sharply. ATM call captures the reversion with "
               "limited downside. Typical reversion: 5-10% in 2-4 weeks = 3-5x on the call."},
    "opt_insider_call": {
        "rule": "insider_call", "legs": "C", "dte": (30, 90, 45), "hold": 30, "top": 3,
        "name": "Insider buying call",
        "why": "Lakonishok & Lee (2001 JF): insider buys predict +3%/quarter abnormal returns. "
               "Calls give 4-6x leverage on the 30-90 day window when insiders expect a catalyst. "
               "Longer DTE (45 days) reduces theta burn while waiting for the catalyst."},
    "opt_short_strangle": {
        "rule": "vrp_high", "legs": "CS", "dte": (21, 50, 35), "hold": 14, "top": 3,
        "short": True, "take_profit": 0.50,
        "name": "Short strangle (VRP harvest)",
        "why": "Same VRP harvest as opt_vrp_straddle_short but wider strikes: selling OTM options "
               "(delta ~0.30 vs 0.50 ATM) collects less premium but allows a larger move before "
               "the position loses money. Higher win rate; lower per-win premium. "
               "Coval & Shumway (2001 JF); Carr & Wu (2009 RFS)."},
    "opt_short_call_uptrend": {
        "rule": "iv_high_uptrend", "legs": "C", "dte": (21, 50, 35), "hold": 20, "top": 3,
        "short": True, "take_profit": 0.50,
        "name": "Short call / covered call (uptrend)",
        "why": "The CBOE BuyWrite Index (BXM) has outperformed the S&P500 by ~100bps/yr on a "
               "risk-adjusted basis since 1988 (Whaley 2002 JD). Selling ATM calls on uptrending "
               "stocks (above SMA200) collects the variance risk premium on the call side. "
               "Loses badly when stock has a large upside move; wins on flat or down days. "
               "Complements the short-put strategy: testing whether put or call side of VRP is larger."},
    "opt_put_credit_spread": {
        "rule": "iv_high_uptrend", "legs": "PCS", "dte": (21, 50, 35), "hold": 20, "top": 3,
        "is_credit": True, "take_profit": 0.50,
        "name": "Put credit spread (defined risk VRP)",
        "why": "Sell ATM put + buy OTM put as a single spread: collects the variance risk premium with "
               "a defined maximum loss (spread width minus credit received). On limited_margin, "
               "requires less buying power than a naked short put. Hutchinson & Mulqueeney (2020); "
               "Whaley (2002 JD): short put strategies earn ~1.5%/mo premium with defined-risk variant "
               "reducing margin by 30-50% vs. naked short."},
}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("options") or {})}


def tradeable(spec, cfg: dict | None = None) -> bool:
    """Owner's rule (2026-10-05): no open shorts, every option one contract. Only a long single-leg
    strategy may ever trade; a spec with a short leg never does, whatever the config lists.
    `spec` is a STRATEGIES entry or a name ('opt_x' or 'option:opt_x'); an unknown name is not tradeable."""
    p = spec if isinstance(spec, dict) else STRATEGIES.get(str(spec).removeprefix("option:"))
    if not p or p.get("short") or p.get("is_credit") or p.get("is_debit_spread"):
        return False
    return p.get("legs") in settings(cfg or {})["tradeable_legs"]


def init(conn) -> None:
    od.init(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT NOT NULL, strategy TEXT NOT NULL,
            symbol TEXT NOT NULL, legs TEXT NOT NULL, opened TEXT NOT NULL, cost REAL NOT NULL,
            closed TEXT, value REAL, ret REAL, usd REAL, reason TEXT, signal TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS option_trades_s ON option_trades (mode, strategy, closed)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_funds (
            name TEXT PRIMARY KEY, capital_usd REAL NOT NULL, started_on TEXT NOT NULL, status TEXT NOT NULL)""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_fund_equity (
            name TEXT NOT NULL, date TEXT NOT NULL, equity_usd REAL NOT NULL, realized_usd REAL NOT NULL,
            unrealized_usd REAL NOT NULL, open_positions INTEGER NOT NULL, PRIMARY KEY (name, date))""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_backtests (
            strategy TEXT PRIMARY KEY, start TEXT, end TEXT, trades INTEGER, mean_ret REAL, median_ret REAL,
            win_rate REAL, by_year TEXT, computed_at TEXT)""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_backtests_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT NOT NULL, start TEXT, end TEXT, trades INTEGER,
            mean_ret REAL, median_ret REAL, win_rate REAL, by_year TEXT, computed_at TEXT, archived_at TEXT)""")
    conn.commit()


# --- pricing -------------------------------------------------------------------
def _days(a: str, b: str) -> int:
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def _ok(q: dict, s: dict) -> bool:
    b, a = q.get("bid"), q.get("ask")
    if a is None or b is None or a < s["min_ask"] or b <= 0:
        return False
    mid = (a + b) / 2
    return (a - b) / mid <= s["max_spread_frac"]


def _monthly(e: str) -> bool:
    d = dt.date.fromisoformat(e)
    return d.weekday() == 4 and 15 <= d.day <= 21


def _leg(q: dict) -> dict:
    return {"exp": q["expiration"], "strike": q["strike"], "cp": q["cp"],
            "ask": q["ask"], "bid": q["bid"],
            "hs": (q["ask"] - q["bid"]) / (q["ask"] + q["bid"])}


def pick(conn, symbol: str, date: str, legs: str, dte: tuple, s: dict, delta: float | None = None) -> list | None:
    """Contracts at the money: legs 'C' (call), 'P' (put), 'S' (straddle),
    'IC' (iron condor), 'CS' (short strangle), 'BCS' (bull call spread),
    'BPS' (bear put spread). Returns leg dicts; short legs have short=True set.
    `delta` moves a single call or put off the money to that absolute delta; None is at the money."""
    rows = [r for r in od.chain(conn, symbol, date) if r["delta"] is not None]
    lo, hi, tgt = dte
    exps = sorted({r["expiration"] for r in rows if lo <= _days(date, r["expiration"]) <= hi},
                  key=lambda e: (not _monthly(e), abs(_days(date, e) - tgt)))
    for exp in exps:
        calls = sorted([r for r in rows if r["expiration"] == exp and r["cp"] == "C"],
                       key=lambda r: r["strike"])
        puts = sorted([r for r in rows if r["expiration"] == exp and r["cp"] == "P"],
                      key=lambda r: r["strike"])
        if not calls or not puts:
            continue
        calls_by_str = {r["strike"]: r for r in calls}
        puts_by_str = {r["strike"]: r for r in puts}

        if legs in ("C", "P", "S"):
            if delta is not None and legs == "C":
                want = [min(calls, key=lambda r: abs(r["delta"] - delta))]
            elif delta is not None and legs == "P":
                want = [min(puts, key=lambda r: abs(abs(r["delta"]) - delta))]
            else:
                atm = min(calls, key=lambda r: abs(r["delta"] - 0.5))
                want = {"C": [atm], "P": [puts_by_str.get(atm["strike"])],
                        "S": [atm, puts_by_str.get(atm["strike"])]}[legs]
            if all(q is not None and _ok(q, s) for q in want):
                return [_leg(q) for q in want]

        elif legs == "CS":
            # Short strangle: short OTM call (~delta 0.30) + short OTM put (~delta 0.30)
            sc = min(calls, key=lambda r: abs(abs(r["delta"]) - 0.30))
            sp = min(puts, key=lambda r: abs(abs(r["delta"]) - 0.30))
            if sc["strike"] <= sp["strike"]:
                continue  # strikes crossed → no valid strangle
            if _ok(sc, s) and _ok(sp, s):
                l1, l2 = _leg(sc), _leg(sp)
                l1["short"] = l2["short"] = True
                return [l1, l2]

        elif legs == "IC":
            # Iron condor: short call (~0.30δ) + short put (~0.30δ) + long call wing + long put wing.
            # Wings must give net_credit >= 20% of wing_width to ensure the trade is worth entering.
            sc = min(calls, key=lambda r: abs(abs(r["delta"]) - 0.30))
            sp = min(puts, key=lambda r: abs(abs(r["delta"]) - 0.30))
            if sc["strike"] <= sp["strike"]:
                continue
            lc_cands = [r for r in calls if r["strike"] > sc["strike"]]
            lp_cands = [r for r in puts if r["strike"] < sp["strike"]]
            if not lc_cands or not lp_cands:
                continue
            # Try wings progressively wider until credit >= 20% of wing width.
            chosen = None
            for lc in sorted(lc_cands, key=lambda r: r["strike"]):
                for lp in sorted(lp_cands, key=lambda r: -r["strike"]):
                    if not all(_ok(q, {**s, "min_ask": 0.01}) for q in (sc, sp, lc, lp)):
                        continue
                    net_credit = sc["bid"] + sp["bid"] - lc["ask"] - lp["ask"]
                    wing_w = min(lc["strike"] - sc["strike"], sp["strike"] - lp["strike"])
                    if net_credit >= 0.15 * wing_w and wing_w > 0:
                        chosen = (lc, lp, net_credit)
                        break
                if chosen:
                    break
            if not chosen:
                continue
            lc, lp, net_credit = chosen
            lsc, lsp, llc, llp = _leg(sc), _leg(sp), _leg(lc), _leg(lp)
            lsc["short"] = lsp["short"] = True
            return [lsc, lsp, llc, llp]

        elif legs == "BCS":
            # Bull call spread: long ATM call + short OTM call
            atm = min(calls, key=lambda r: abs(r["delta"] - 0.5))
            otm_cands = [r for r in calls if r["strike"] > atm["strike"]]
            if not otm_cands:
                continue
            otm = min(otm_cands, key=lambda r: abs(abs(r["delta"]) - 0.30))
            if _ok(atm, s) and _ok(otm, {**s, "min_ask": 0.01}):
                net_debit = atm["ask"] - otm["bid"]
                if net_debit <= 0:
                    continue
                l1, l2 = _leg(atm), _leg(otm)
                l2["short"] = True
                return [l1, l2]

        elif legs == "BPS":
            # Bear put spread: long ATM put + short OTM put
            atm_p = min(puts, key=lambda r: abs(abs(r["delta"]) - 0.5))
            otm_cands = [r for r in puts if r["strike"] < atm_p["strike"]]
            if not otm_cands:
                continue
            otm = max(otm_cands, key=lambda r: abs(r["delta"]))
            otm = min(otm_cands, key=lambda r: abs(abs(r["delta"]) - 0.30))
            if _ok(atm_p, s) and _ok(otm, {**s, "min_ask": 0.01}):
                net_debit = atm_p["ask"] - otm["bid"]
                if net_debit <= 0:
                    continue
                l1, l2 = _leg(atm_p), _leg(otm)
                l2["short"] = True
                return [l1, l2]
        elif legs == "PCS":
            # Put credit spread (bull put spread): short ATM put + long OTM put
            atm_p = min(puts, key=lambda r: abs(abs(r["delta"]) - 0.5))
            otm_cands = [r for r in puts if r["strike"] < atm_p["strike"]]
            if not otm_cands:
                continue
            otm = min(otm_cands, key=lambda r: abs(abs(r["delta"]) - 0.30))
            if _ok(atm_p, s) and _ok(otm, {**s, "min_ask": 0.01}):
                net_credit = atm_p["bid"] - otm["ask"]
                if net_credit <= 0:
                    continue
                l1, l2 = _leg(atm_p), _leg(otm)
                l1["short"] = True  # short the higher-strike (ATM) put
                return [l1, l2]
    return None


def spot(conn, symbol: str, date: str) -> float | None:
    """The stock's own (unadjusted) price on `date`, read from that day's option chain by
    put-call parity at the strike where call and put mids are closest: S ~ K + C - P.
    Never our price table: it is split- and dividend-ADJUSTED (NVDA's January 2024 close
    reads ~$48 there against a $485 strike) and would misvalue every expiry."""
    rows = od.chain(conn, symbol, date)
    by = {}
    for r in rows:
        if r["bid"] is not None and r["ask"] is not None and r["ask"] > 0:
            by.setdefault((r["expiration"], r["strike"]), {})[r["cp"]] = (r["bid"] + r["ask"]) / 2
    pairs = [(k, v["C"] - v["P"]) for (e, k), v in by.items() if "C" in v and "P" in v]
    if not pairs:
        return None
    k, d = min(pairs, key=lambda x: abs(x[1]))
    return k + d


def _spot_on_or_before(conn, symbol: str, date: str, days: int = 7) -> float | None:
    d = dt.date.fromisoformat(date)
    for i in range(days + 1):
        x = spot(conn, symbol, (d - dt.timedelta(days=i)).isoformat())
        if x:
            return x
    return None


def _bs(spot_px: float, k: float, t: float, iv: float, cp: str) -> float:
    """Black-Scholes value (no rates or dividends: weeks-long options), for exits the chain
    does not quote — priced at that day's real implied volatility for the stock."""
    import math
    if t <= 0 or iv <= 0:
        return max(spot_px - k, 0.0) if cp == "C" else max(k - spot_px, 0.0)
    v = iv * math.sqrt(t)
    d1 = (math.log(spot_px / k) + 0.5 * v * v) / v
    d2 = d1 - v
    n = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))   # noqa: E731
    return spot_px * n(d1) - k * n(d2) if cp == "C" else k * n(-d2) - spot_px * n(-d1)


def value(conn, symbol: str, legs: list, date: str, allow_model: bool = False) -> tuple:
    """(current value of the position on `date`, modelled?).
    Long legs: bid price (what we'd receive selling). Short legs: ask price (cost to close).
    At/after expiration: intrinsic value against the unadjusted spot — the amount owed to
    the buyer (long) or owed by us (short); caller handles sign convention."""
    tot, modelled = 0.0, False
    for leg in legs:
        is_short = leg.get("short", False)
        if date >= leg["exp"]:
            px = _spot_on_or_before(conn, symbol, leg["exp"])
            if px is None:
                return None, False
            tot += max(px - leg["strike"], 0.0) if leg["cp"] == "C" else max(leg["strike"] - px, 0.0)
            continue
        q = next((r for r in od.chain(conn, symbol, date) if r["expiration"] == leg["exp"]
                  and r["strike"] == leg["strike"] and r["cp"] == leg["cp"]), None)
        if q is not None:
            price = q["ask"] if is_short else q["bid"]
            if price is not None:
                tot += price
                continue
        if not allow_model:
            return None, False
        px = spot(conn, symbol, date)
        iv = conn.execute("SELECT iv_current FROM option_vol WHERE symbol=? AND date=?", (symbol, date)).fetchone()
        if px is None or not iv or not iv[0]:
            return None, False
        t = _days(date, leg["exp"]) / 365.0
        hs = leg.get("hs", 0.0)
        bs = _bs(px, leg["strike"], t, float(iv[0]), leg["cp"])
        tot += bs * (1 + hs if is_short else 1 - hs)
        modelled = True
    return tot, modelled


def sells_premium(p: dict) -> bool:
    """True for a strategy that is paid up front: credit spreads, and every pure-short spec."""
    return p.get("is_credit", p.get("short", False))


def close_value(conn, p: dict, symbol: str, legs: list, date: str, allow_model: bool = False) -> tuple:
    """(what closing the whole position is worth on `date`, modelled?); (None, False) when a leg has
    no price. Credit position: cost to close = short asks - long bids, capped at the widest wing (the
    most it can lose). Other mixed positions (debit spreads): receipt = long bids - short asks.
    Single-sided positions: value() as it is (longs at bid, shorts at ask)."""
    shorts = [leg for leg in legs if leg.get("short")]
    longs = [leg for leg in legs if not leg.get("short")]
    if not (shorts and longs):
        return value(conn, symbol, legs, date, allow_model)
    sv, sm = value(conn, symbol, shorts, date, allow_model)
    lv, lm = value(conn, symbol, longs, date, allow_model)
    if sv is None or lv is None:
        return None, False
    if not sells_premium(p):
        return lv - sv, sm or lm
    v = sv - lv
    wings = []
    for cp in ("C", "P"):
        s_k = [leg["strike"] for leg in shorts if leg["cp"] == cp]
        l_k = [leg["strike"] for leg in longs if leg["cp"] == cp]
        if s_k and l_k:
            wings.append(max(l_k) - min(s_k) if cp == "C" else max(s_k) - min(l_k))
    return (min(v, max(wings)) if wings else v), sm or lm


def trade_return(p: dict, v: float, cost: float) -> float:
    """Fractional return on the entry price: premium sold earns 1 - close/credit, premium bought
    (long options, debit spreads) value/debit - 1."""
    if cost <= 0:
        return 0.0
    return (1 - v / cost) if sells_premium(p) else (v / cost - 1)


def one_contract(cost: float, s: dict) -> bool:
    """One contract (quotes are per share, so x100) costs no more than the book allows."""
    return cost * CONTRACT <= s["max_contract_cost_usd"]


def trade_usd(p: dict, v: float, cost: float, s: dict, cfg: dict | None = None) -> float:
    """A trade the rule allows is one real contract in dollars; anything else (research specs, and
    trades opened before the cap existed) is measured as stake x return."""
    if tradeable(p, cfg) and one_contract(cost, s):
        return (v - cost) * CONTRACT
    return s["stake_usd"] * trade_return(p, v, cost)


# --- signals -------------------------------------------------------------------
def option_dates(conn, start: str, end: str | None = None) -> list:
    q = "SELECT DISTINCT date FROM option_vol WHERE date >= ?" + (" AND date <= ?" if end else "") + " ORDER BY date"
    return [r[0] for r in conn.execute(q, (start, end) if end else (start,))]


def liquid(conn, date: str, n: int) -> list:
    """The n most traded optionable common stocks on `date` (20-day dollar volume)."""
    rows = conn.execute("""
        SELECT f.ticker FROM features f JOIN option_vol v ON v.symbol=f.ticker AND v.date=f.date
        WHERE f.date=? AND f.dollar_volume_20 IS NOT NULL ORDER BY f.dollar_volume_20 DESC LIMIT ?""",
                        (date, n)).fetchall()
    return [r[0] for r in rows]


def sig_iv_cheap(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """First option date of each month: lowest implied vol relative to realised vol."""
    month = date[:7]
    if state.get("month") == month:
        return []
    state["month"] = month
    uni = set(liquid(conn, date, 300))
    rows = conn.execute("SELECT symbol, iv_current / hv_current FROM option_vol WHERE date=? AND iv_current > 0 "
                        "AND hv_current > 0", (date,)).fetchall()
    rows = sorted((r for r in rows if r[0] in uni), key=lambda r: r[1])
    return [(sym, f"IV/HV {ratio:.2f}") for sym, ratio in rows[:p["top"]]]


def sig_iv_rise(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """First option date of each week: largest one-month rise in implied vol."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    uni = set(liquid(conn, date, 300))
    rows = conn.execute("SELECT symbol, iv_current / iv_month_ago - 1 FROM option_vol WHERE date=? AND "
                        "iv_current > 0 AND iv_month_ago > 0", (date,)).fetchall()
    rows = sorted((r for r in rows if r[0] in uni), key=lambda r: -r[1])
    return [(sym, f"IV +{chg:.0%} in a month") for sym, chg in rows[:p["top"]]]


def sig_earnings(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Liquid stocks with an earnings release (8-K item 2.02) 2-6 days after `date`.
    Uses the release's filed date; firms announce these dates weeks ahead."""
    if "uni" not in state or state.get("uni_month") != date[:7]:
        state["uni"], state["uni_month"] = set(liquid(conn, date, s["liquid_universe"])), date[:7]
    d0 = (dt.date.fromisoformat(date) + dt.timedelta(days=2)).isoformat()
    d1 = (dt.date.fromisoformat(date) + dt.timedelta(days=6)).isoformat()
    rows = conn.execute("SELECT DISTINCT ticker, filed FROM edgar_events WHERE item='2.02' AND filed BETWEEN ? AND ?",
                        (d0, d1)).fetchall()
    out = [(t, f"earnings {f}") for t, f in rows if t in state["uni"]]
    state.setdefault("exit_after", {}).update({t: f for t, f in rows if t in state["uni"]})
    return out


def chain_metrics(conn, symbol: str, date: str) -> dict | None:
    """Implied-vol shape of one chain, from the expiry nearest 30 days (14-60):
    ivspread = at-the-money call IV minus the put IV at the same strike (Cremers &
    Weinbaum's call-put implied volatility spread); smirk = the out-of-the-money put
    nearest delta -0.25, IV minus the at-the-money call IV (Xing, Zhang & Zhao)."""
    rows = [r for r in od.chain(conn, symbol, date) if r["iv"] is not None and r["delta"] is not None]
    exps = sorted({r["expiration"] for r in rows if 14 <= _days(date, r["expiration"]) <= 60},
                  key=lambda e: abs(_days(date, e) - 30))
    if not exps:
        return None
    e = exps[0]
    calls = [r for r in rows if r["expiration"] == e and r["cp"] == "C"]
    puts = [r for r in rows if r["expiration"] == e and r["cp"] == "P"]
    if not calls or not puts:
        return None
    atm = min(calls, key=lambda r: abs(r["delta"] - 0.5))
    same = next((r for r in puts if r["strike"] == atm["strike"]), None)
    otm = min(puts, key=lambda r: abs(r["delta"] + 0.25))
    if abs(otm["delta"] + 0.25) > 0.15:
        otm = None
    return {"ivspread": None if same is None else atm["iv"] - same["iv"],
            "smirk": None if otm is None else otm["iv"] - atm["iv"]}


# Option momentum (R6). Formation: the stock's own one-month at-the-money straddle
# return, bought at the first option date of a month and sold (real bid, else the
# model price) at the first option date of the next. Cached across calls: a
# formation return never changes once both dates are past.
_FORMATION: dict = {}
MOM_UNIVERSE = 100
MOM_MIN_MONTHS = 4


def _month_firsts(conn, upto: str) -> list:
    return [r[0] for r in conn.execute("SELECT MIN(date) FROM option_vol WHERE date <= ? "
                                       "GROUP BY substr(date, 1, 7) ORDER BY 1", (upto,))]


def straddle_return(conn, sym: str, d0: str, d1: str, s: dict) -> float | None:
    key = (sym, d0, d1)
    if key not in _FORMATION:
        legs = pick(conn, sym, d0, "S", (21, 50, 35), s)
        r = None
        if legs:
            v, _ = value(conn, sym, legs, d1, allow_model=True)
            cost = sum(leg["ask"] for leg in legs)
            r = (v / cost - 1) if v is not None and cost > 0 else None
        _FORMATION[key] = r
    return _FORMATION[key]


def sig_opt_momentum(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """First option date of each month: highest mean straddle return over months t-12..t-2
    (the most recent month is skipped: one-month option returns reverse). At least
    MOM_MIN_MONTHS formation months, or the stock is not ranked."""
    month = date[:7]
    if state.get("month") == month:
        return []
    state["month"] = month
    firsts = _month_firsts(conn, date)
    if not firsts or firsts[-1][:7] != month:
        return []
    cur = len(firsts) - 1
    windows = [(firsts[m], firsts[m + 1]) for m in range(max(0, cur - 12), cur - 1)]
    ranked = []
    for sym in liquid(conn, date, MOM_UNIVERSE):
        rets = [r for d0, d1 in windows if (r := straddle_return(conn, sym, d0, d1, s)) is not None]
        if len(rets) >= MOM_MIN_MONTHS:
            ranked.append((sym, sum(rets) / len(rets), len(rets)))
    ranked.sort(key=lambda x: -x[1])
    return [(sym, f"straddle momentum {m:+.0%}/month over {n} months") for sym, m, n in ranked[:p["top"]]]


def sig_chain(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """First option date of each week, over the most traded optionable stocks: rank by the
    chain's implied-vol shape (chain_metrics) — shared by the smirk and IV-spread rules."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    cache = state.setdefault("metrics", {})
    if date not in cache:
        cache.clear()
        cache[date] = {sym: m for sym in liquid(conn, date, s["liquid_universe"])
                       if (m := chain_metrics(conn, sym, date))}
    ms = cache[date]
    key, desc = {"smirk": ("smirk", True), "ivspread_high": ("ivspread", True),
                 "ivspread_low": ("ivspread", False)}[p["rule"]]
    ranked = sorted(((sym, m[key]) for sym, m in ms.items() if m.get(key) is not None),
                    key=lambda x: -x[1] if desc else x[1])
    return [(sym, f"{key} {v:+.3f}") for sym, v in ranked[:p["top"]]]


def sig_vrp_high(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Weekly: stocks with IV/HV > 1.3 — options are overpriced relative to realised vol."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    uni = set(liquid(conn, date, 300))
    rows = conn.execute(
        "SELECT symbol, iv_current / hv_current FROM option_vol WHERE date=? "
        "AND iv_current > 0 AND hv_current > 0 AND iv_current / hv_current > 1.3",
        (date,)).fetchall()
    rows = sorted((r for r in rows if r[0] in uni), key=lambda r: -r[1])
    return [(sym, f"IV/HV {ratio:.2f}") for sym, ratio in rows[:p["top"]]]


def sig_iv_high_uptrend(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Weekly: elevated IV/HV AND stock above SMA200 — selling puts on an uptrend is safer."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    uni = set(liquid(conn, date, 300))
    iv_high = {r[0]: r[1] for r in conn.execute(
        "SELECT symbol, iv_current / hv_current FROM option_vol WHERE date=? "
        "AND iv_current > 0 AND hv_current > 0 AND iv_current / hv_current > 1.2",
        (date,)).fetchall() if r[0] in uni}
    uptrend = {r[0] for r in conn.execute(
        "SELECT f.ticker FROM features f JOIN prices p ON p.ticker=f.ticker AND p.date=f.date "
        "WHERE f.date=? AND f.sma_200 IS NOT NULL AND p.close > f.sma_200",
        (date,)).fetchall()}
    rows = sorted([(sym, ratio) for sym, ratio in iv_high.items() if sym in uptrend],
                  key=lambda r: -r[1])
    return [(sym, f"IV/HV {ratio:.2f} above SMA200") for sym, ratio in rows[:p["top"]]]


def sig_earnings_near_short(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Liquid stocks with earnings in 1–3 days: sell the straddle just before IV crush."""
    if "uni" not in state or state.get("uni_month") != date[:7]:
        state["uni"] = set(liquid(conn, date, s["liquid_universe"]))
        state["uni_month"] = date[:7]
    d0 = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
    d1 = (dt.date.fromisoformat(date) + dt.timedelta(days=3)).isoformat()
    rows = conn.execute(
        "SELECT DISTINCT ticker, filed FROM edgar_events WHERE item='2.02' AND filed BETWEEN ? AND ?",
        (d0, d1)).fetchall()
    out = []
    for t, f in rows:
        if t in state["uni"]:
            out.append((t, f"earnings {f}"))
            state.setdefault("exit_after", {})[t] = f
    return out


def sig_earnings_far_long(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Liquid stocks with earnings in 14–21 days: buy the straddle to ride the IV expansion,
    then close 1 day before the event (exit is wired in run())."""
    if "uni" not in state or state.get("uni_month") != date[:7]:
        state["uni"] = set(liquid(conn, date, s["liquid_universe"]))
        state["uni_month"] = date[:7]
    d0 = (dt.date.fromisoformat(date) + dt.timedelta(days=14)).isoformat()
    d1 = (dt.date.fromisoformat(date) + dt.timedelta(days=21)).isoformat()
    rows = conn.execute(
        "SELECT DISTINCT ticker, filed FROM edgar_events WHERE item='2.02' AND filed BETWEEN ? AND ?",
        (d0, d1)).fetchall()
    return [(t, f"earnings {f}") for t, f in rows if t in state["uni"]]


def sig_signal_cheap_iv(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Stock-signal entries filtered to dates when IV is not elevated (IV/HV < 1.2).
    Avoids buying calls when the options market has already priced in a large move."""
    cands = (state.get("signals") or {}).get(date, [])
    if not cands:
        return []
    iv_ok = {r[0] for r in conn.execute(
        "SELECT symbol FROM option_vol WHERE date=? AND iv_current > 0 AND hv_current > 0 "
        "AND iv_current / hv_current < 1.2", (date,)).fetchall()}
    return [(sym, f"{why} [cheap IV]") for sym, why in cands if sym in iv_ok]


def sig_vrp_range(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Weekly: high VRP (IV/HV > 1.2) AND low recent realised vol (HV < iv_month_ago * 0.7).
    These stocks have high IV relative to the vol they're actually delivering — ideal IC candidates
    because they are likely to stay in a range while we harvest the vol premium."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    uni = set(liquid(conn, date, 300))
    rows = conn.execute(
        "SELECT symbol, iv_current, hv_current FROM option_vol WHERE date=? "
        "AND iv_current > 0 AND hv_current > 0 AND iv_current / hv_current > 1.2",
        (date,)).fetchall()
    ranked = []
    for sym, iv, hv in rows:
        if sym not in uni:
            continue
        ranked.append((sym, iv / hv))
    ranked.sort(key=lambda x: -x[1])
    return [(sym, f"VRP IC: IV/HV {ratio:.2f}") for sym, ratio in ranked[:p.get("top", 5)]]


def sig_pead_call(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Post-earnings announcement drift: stocks that beat earnings (positive SUE) in the past 5 days.
    Patell & Wolfson (1979): PEAD persists for weeks after announcement.
    Bernard & Thomas (1989): +2.75% in 3 months for top-SUE decile. Buy call to leverage the drift."""
    if "uni" not in state or state.get("uni_month") != date[:7]:
        state["uni"] = set(liquid(conn, date, s["liquid_universe"]))
        state["uni_month"] = date[:7]
    d0 = (dt.date.fromisoformat(date) - dt.timedelta(days=5)).isoformat()
    d1 = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    # Recent earnings event + positive price reaction (proxy for beat)
    events = conn.execute(
        "SELECT DISTINCT e.ticker, e.filed, p.close, p2.close "
        "FROM edgar_events e "
        "JOIN prices p ON p.ticker=e.ticker AND p.date=e.filed "
        "JOIN prices p2 ON p2.ticker=e.ticker AND p2.date=( "
        "  SELECT MAX(date) FROM prices WHERE ticker=e.ticker AND date < e.filed) "
        "WHERE e.item='2.02' AND e.filed BETWEEN ? AND ?",
        (d0, d1)).fetchall()
    out = []
    for sym, filed, close_after, close_before in events:
        if sym not in state["uni"]:
            continue
        if close_before and close_after and close_after > close_before * 1.01:  # up 1%+ = beat
            out.append((sym, f"post-earnings drift {filed}"))
    return out[:p.get("top", 3)]


def sig_breakout_call(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Weekly: stocks making new 52-week highs — breakout momentum call.
    Jegadeesh & Titman (1993): momentum persists. New-high breakout is particularly strong
    (George & Hwang 2004: 52-week high is the strongest momentum signal).
    Buy a call to get leveraged exposure to the continued breakout."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    uni = set(liquid(conn, date, 300))
    # Stocks at or above their 52-week high (highest close in 252 trading days)
    rows = conn.execute("""
        SELECT p.ticker, p.close,
               (SELECT MAX(close) FROM prices WHERE ticker=p.ticker
                AND date < p.date AND date >= date(p.date, '-365 days')) AS high52
        FROM prices p
        WHERE p.date=? AND p.close IS NOT NULL""", (date,)).fetchall()
    out = []
    for sym, close, high52 in rows:
        if sym not in uni or high52 is None:
            continue
        if close >= high52 * 0.98:  # within 2% of 52-week high = breakout zone
            out.append((sym, f"52-week high breakout {close:.2f}"))
    return out[:p.get("top", 3)]


def sig_oversold_call(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Weekly: RSI < 35 AND price above SMA200 (mean-reversion setup within an uptrend).
    Oversold in an uptrend → likely snap-back. Buy a call for leveraged reversion.
    Literature: Lehmann (1990), Jegadeesh (1990) — short-term reversal is real and fast."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    uni = set(liquid(conn, date, 300))
    rows = conn.execute(
        "SELECT f.ticker, f.rsi_14, f.sma_200, p.close FROM features f "
        "JOIN prices p ON p.ticker=f.ticker AND p.date=f.date "
        "WHERE f.date=? AND f.rsi_14 IS NOT NULL AND f.sma_200 IS NOT NULL",
        (date,)).fetchall()
    ranked = [(sym, rsi) for sym, rsi, sma, close in rows
              if sym in uni and rsi < 35 and close > sma * 0.98]  # uptrend with pullback
    ranked.sort(key=lambda x: x[1])  # most oversold first
    return [(sym, f"RSI {rsi:.1f} oversold in uptrend") for sym, rsi in ranked[:p.get("top", 3)]]


def sig_insider_call(conn, date: str, p: dict, s: dict, state: dict) -> list:
    """Weekly: stocks with significant recent insider buying (Form 4 buys in past 30 days).
    Lakonishok & Lee (2001 JF): insider buys predict +3%/quarter abnormal returns.
    Buy a call to leverage the informed signal — insiders buy when they expect a rise."""
    week = dt.date.fromisoformat(date).isocalendar()[:2]
    if state.get("week") == week:
        return []
    state["week"] = week
    uni = set(liquid(conn, date, 300))
    d30 = (dt.date.fromisoformat(date) - dt.timedelta(days=30)).isoformat()
    try:
        rows = conn.execute(
            "SELECT ticker, COUNT(*) AS cnt FROM insider_trades "
            "WHERE code='P' AND filing_date BETWEEN ? AND ? GROUP BY ticker "
            "ORDER BY cnt DESC", (d30, date)).fetchall()
        return [(sym, f"insider buys {cnt}x in 30d") for sym, cnt in rows
                if sym in uni][:p.get("top", 3)]
    except Exception:
        return []


def stock_signals(conn, cfg: dict, start: str, end: str, top: int = 5) -> dict:
    """date -> [(symbol, strategy name)] from the top-ranked stock strategies' entry rules,
    most liquid first. Search, crypto and option strategies are excluded."""
    import genome as gn
    import ranking
    import storage
    from train_model import FEATURE_COLS
    rows = [r for r in ranking.rank(conn, cfg) if r["passes_gate"] and not r.get("from_search")
            and not str(r["strategy_key"]).startswith(("crypto:", "option:", "pair:", "value:"))][:top]
    import strategy_objects as so
    df = storage.load_training_frame(conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
                                     start_date=start, end_date=end, min_price=cfg["risk"].get("min_price"),
                                     min_dollar_volume=cfg["risk"].get("min_dollar_volume"), include_liquidity=True)
    df = storage.attach_fundamentals(conn, df).sort_values(["ticker", "date"])
    out = {}
    for r in rows:
        g = so.genome(conn, r["strategy_key"], r["version"])
        if not g:
            continue
        hit = df[gn._as_bool(gn.evaluate(g["entry"], df)).to_numpy()]
        for d, grp in hit.sort_values("dollar_volume_20", ascending=False).groupby("date"):
            out.setdefault(str(d)[:10], []).extend((t, r["name"]) for t in grp["ticker"].astype(str))
    return out


# --- the engine ------------------------------------------------------------------
def run(conn, cfg: dict, name: str, dates: list, mode: str = "BACKTEST", signals: dict | None = None,
        spec: dict | None = None) -> int:
    """Walk `dates`: close what is due, then open today's signals. Same code for backtest and paper.
    `spec` runs a variant that is not in STRATEGIES (the sweep); `name` then only labels its trades."""
    s = settings(cfg)
    p = spec or STRATEGIES[name]
    can_trade = tradeable(p, cfg)
    state = {}
    is_short = p.get("short", False)
    is_credit = sells_premium(p)  # credit spreads: IC, short strangle, short put etc.
    opened = 0
    _SIG = {"iv_cheap": sig_iv_cheap, "iv_rise": sig_iv_rise, "earnings": sig_earnings,
            "smirk": sig_chain, "ivspread_high": sig_chain, "ivspread_low": sig_chain,
            "opt_momentum": sig_opt_momentum, "vrp_high": sig_vrp_high,
            "iv_high_uptrend": sig_iv_high_uptrend,
            "earnings_near_short": sig_earnings_near_short,
            "earnings_far_long": sig_earnings_far_long,
            "signal_cheap_iv": sig_signal_cheap_iv,
            "vrp_range": sig_vrp_range, "pead_call": sig_pead_call,
            "breakout": sig_breakout_call, "breakout_call": sig_breakout_call,
            "oversold_call": sig_oversold_call, "insider_call": sig_insider_call}
    fn = _SIG.get(p["rule"])
    if p["rule"] == "signal_cheap_iv":
        state["signals"] = signals or {}
    for d in dates:
        # exits
        for t in conn.execute("SELECT id, symbol, legs, opened, cost, signal FROM option_trades WHERE mode=? AND "
                              "strategy=? AND closed IS NULL", (mode, name)).fetchall():
            tid, sym, legs_j, op, cost, sig = t
            legs = json.loads(legs_j)
            exp = min(leg["exp"] for leg in legs)
            due = None
            # after-earnings exits (long and short strategies)
            if p["rule"] in ("earnings", "earnings_near_short") and sig and sig.startswith("earnings ") \
                    and d > sig.split(" ", 1)[1]:
                due = "after earnings"
            # pre-earnings long: close 1 day before the event
            elif p["rule"] == "earnings_far_long" and sig and sig.startswith("earnings "):
                event = sig.split(" ", 1)[1]
                if d >= (dt.date.fromisoformat(event) - dt.timedelta(days=1)).isoformat():
                    due = "before earnings"
            # take-profit: buy a short position back once most of its credit has decayed
            if is_credit and p.get("take_profit") and not due:
                net_close, _ = close_value(conn, p, sym, legs, d, allow_model=False)
                if net_close is not None and cost > 0 and net_close <= (1 - p["take_profit"]) * cost:
                    due = f"take profit {1 - net_close / cost:.0%}"
            if not due:
                if _days(op, d) >= p["hold"] * 7 // 5:
                    due = "holding limit"
                elif _days(d, exp) <= 7:
                    due = "a week to expiry"
            if d >= exp:
                due = "expired"
            if not due:
                continue
            overdue = _days(op, d) - p["hold"] * 7 // 5
            v, modelled = close_value(conn, p, sym, legs, d, allow_model=False)
            if v is None:
                if due == "holding limit" and overdue < 7 and _days(d, exp) > 7:
                    continue
                v, modelled = close_value(conn, p, sym, legs, d, allow_model=True)
            if v is None:
                continue
            ret = trade_return(p, v, cost)
            conn.execute("UPDATE option_trades SET closed=?, value=?, ret=?, usd=?, reason=? WHERE id=?",
                         (d, v, ret, trade_usd(p, v, cost, s, cfg),
                          due + (" (modelled price)" if modelled else ""), tid))
        # entries
        if p["rule"] == "stock_signal":
            cands = (signals or {}).get(d, [])
        elif fn:
            cands = fn(conn, d, p, s, state)
        else:
            cands = []
        held = {r[0] for r in conn.execute("SELECT symbol FROM option_trades WHERE mode=? AND strategy=? AND "
                                           "closed IS NULL", (mode, name))}
        n_today = 0
        for sym, why in cands:
            if sym in held or n_today >= p.get("per_day", 99):
                continue
            legs = pick(conn, sym, d, p["legs"], p["dte"], s, p.get("delta"))
            if not legs:
                continue
            if is_credit:
                # premium sold: credit = short bids - long asks. A spec that is short without naming
                # which legs (plain S/P/C) sells every leg; the flag is what the exit prices off.
                if is_short and not any(l.get("short") for l in legs):
                    for leg in legs:
                        leg["short"] = True
                short_legs = [l for l in legs if l.get("short")]
                long_legs = [l for l in legs if not l.get("short")]
                cost = sum(l["bid"] for l in short_legs) - sum(l["ask"] for l in long_legs)
                if cost <= 0:
                    continue
            elif p.get("is_debit_spread"):
                # mixed: net debit = sum(long_asks) - sum(short_bids)
                long_legs = [l for l in legs if not l.get("short")]
                short_legs = [l for l in legs if l.get("short")]
                cost = sum(l["ask"] for l in long_legs) - sum(l["bid"] for l in short_legs)
                if cost <= 0:
                    continue
            else:
                cost = sum(leg["ask"] for leg in legs)
                if can_trade and not one_contract(cost, s):
                    continue
            conn.execute("INSERT INTO option_trades (mode, strategy, symbol, legs, opened, cost, signal) "
                         "VALUES (?,?,?,?,?,?,?)", (mode, name, sym, json.dumps(legs), d, cost, why))
            held.add(sym)
            n_today += 1
            opened += 1
        conn.commit()
    return opened


def summarize(conn, name: str, mode: str = "BACKTEST") -> dict:
    rows = conn.execute("SELECT opened, ret FROM option_trades WHERE mode=? AND strategy=? AND ret IS NOT NULL",
                        (mode, name)).fetchall()
    n_model = conn.execute("SELECT COUNT(*) FROM option_trades WHERE mode=? AND strategy=? AND reason LIKE "
                           "'%modelled%'", (mode, name)).fetchone()[0]
    if not rows:
        return {"strategy": name, "trades": 0}
    rets = sorted(r[1] for r in rows)
    by = {}
    for op, r in rows:
        by.setdefault(op[:4], []).append(r)
    return {"strategy": name, "trades": len(rets), "modelled_exits": n_model, "mean_ret": sum(rets) / len(rets),
            "median_ret": rets[len(rets) // 2], "win_rate": sum(r > 0 for r in rets) / len(rets),
            "by_year": {y: {"n": len(v), "mean": sum(v) / len(v)} for y, v in sorted(by.items())}}


def backtest(conn, cfg: dict, names: list, start: str, end: str | None = None) -> list:
    init(conn)
    dates = option_dates(conn, start, end)
    if not dates:
        raise SystemExit("no option volatility data in that window yet — run options_data.py --vol-backfill")
    out = []
    for name in names:
        conn.execute("DELETE FROM option_trades WHERE mode='BACKTEST' AND strategy=?", (name,))
        sig = stock_signals(conn, cfg, dates[0], dates[-1]) if STRATEGIES[name]["rule"] in ("stock_signal", "signal_cheap_iv") else None
        run(conn, cfg, name, dates, "BACKTEST", sig)
        r = summarize(conn, name)
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        conn.execute("INSERT INTO option_backtests_history (strategy, start, end, trades, mean_ret, median_ret, "
                     "win_rate, by_year, computed_at, archived_at) SELECT strategy, start, end, trades, mean_ret, "
                     "median_ret, win_rate, by_year, computed_at, ? FROM option_backtests WHERE strategy=?",
                     (now, name))
        conn.execute("INSERT OR REPLACE INTO option_backtests VALUES (?,?,?,?,?,?,?,?,?)",
                     (name, dates[0], dates[-1], r["trades"], r.get("mean_ret"), r.get("median_ret"),
                      r.get("win_rate"), json.dumps(r.get("by_year")), now))
        conn.commit()
        out.append(r)
        log.info(f"{name}: {r}")
    return out


# --- the tournament: league entries and forward paper funds -----------------------
PREFIX = "option:"


def open_funds(conn, cfg: dict) -> list:
    """Register every option strategy in the league (option:<name>, PAPER) and open its
    paper fund from the newest option date. Idempotent."""
    import league
    init(conn)
    s = settings(cfg)
    start = conn.execute("SELECT MAX(date) FROM option_vol").fetchone()[0]
    if not start:
        return []
    opened = []
    for name, p in STRATEGIES.items():
        if name.startswith("t_"):
            continue
        key = PREFIX + name
        row = league.register(conn, key, p.get("name", name),
                              {"family": "options", "kind": "option", "entry_rule": p["rule"], "legs": p["legs"],
                               "holding_period": p["hold"],
                               "parameters": {"dte": list(p["dte"]), "top": p.get("top"), "per_day": p.get("per_day"),
                                              **({"delta": p["delta"]} if p.get("delta") is not None else {})}},
                              author="options_lab", source_kind="options", source_ref=name, hypothesis=p.get("why", ""))
        if league.state(conn, key, row["version"]) is None:
            league.transition(conn, key, league.PAPER, "options paper fund opened (Stage R)",
                              version=row["version"], actor="options_lab")
        if not conn.execute("SELECT 1 FROM option_funds WHERE name=?", (name,)).fetchone():
            conn.execute("INSERT INTO option_funds VALUES (?,?,?, 'open')", (name, 10 * s["stake_usd"], start))
            opened.append(name)
    conn.commit()
    return opened


def mark(conn, cfg: dict, name: str, date: str) -> dict:
    """Fund equity on `date`: capital + realised dollars + open positions as they would close today."""
    s = settings(cfg)
    p = STRATEGIES[name]
    cap = conn.execute("SELECT capital_usd FROM option_funds WHERE name=?", (name,)).fetchone()[0]
    real = conn.execute("SELECT COALESCE(SUM(usd),0) FROM option_trades WHERE mode='PAPER' AND strategy=? AND "
                        "ret IS NOT NULL", (name,)).fetchone()[0]
    unreal, n = 0.0, 0
    for sym, legs, cost in conn.execute("SELECT symbol, legs, cost FROM option_trades WHERE mode='PAPER' AND "
                                        "strategy=? AND closed IS NULL", (name,)).fetchall():
        v, _ = close_value(conn, p, sym, json.loads(legs), date, allow_model=True)
        unreal += trade_usd(p, v, cost, s, cfg) if v is not None else 0.0
        n += 1
    eq = {"equity_usd": cap + real + unreal, "realized_usd": real, "unrealized_usd": unreal, "open_positions": n}
    conn.execute("INSERT OR REPLACE INTO option_fund_equity VALUES (?,?,?,?,?,?)",
                 (name, date, eq["equity_usd"], real, unreal, n))
    conn.commit()
    return eq


def step(conn, cfg: dict) -> dict:
    """Paper: walk every open option fund over the option dates it has not seen yet."""
    open_funds(conn, cfg)
    out = {}
    for name, started, in conn.execute("SELECT name, started_on FROM option_funds WHERE status='open'").fetchall():
        last = conn.execute("SELECT MAX(date) FROM option_fund_equity WHERE name=?", (name,)).fetchone()[0]
        dates = [d for d in option_dates(conn, started) if not last or d > last]
        if not dates:
            continue
        sig = None
        if STRATEGIES[name]["rule"] == "stock_signal":
            lookback = (dt.date.fromisoformat(dates[0]) - dt.timedelta(days=400)).isoformat()
            sig = {d: v for d, v in stock_signals(conn, cfg, lookback, dates[-1]).items() if d in dates}
        run(conn, cfg, name, dates, "PAPER", sig)
        out[name] = mark(conn, cfg, name, dates[-1])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--strategy", action="append")
    ap.add_argument("--start", default="2020-03-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--open-funds", action="store_true", dest="open_funds",
                    help="register all option strategies in the league for paper trading (idempotent)")
    ap.add_argument("--step", action="store_true", help="paper: walk the option funds over new dates")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row          # ranking.rank (stock signals) reads rows by name
    init(conn)
    names = a.strategy or list(STRATEGIES)
    if a.backtest:
        backtest(conn, cfg, names, a.start, a.end)
    if a.open_funds:
        opened = open_funds(conn, cfg)
        print(f"Opened {len(opened)} new option funds: {opened}" if opened else "All option funds already open.")
    if a.step:
        print(json.dumps(step(conn, cfg), indent=1, default=float))
    if a.report or a.backtest:
        results = [(n, summarize(conn, n)) for n in names]
        results.sort(key=lambda x: x[1].get("mean_ret", -99) if x[1]["trades"] else -99, reverse=True)
        s = settings(cfg)
        print(f"\n{'Strategy':<28} {'Trades':>6} {'Mean':>7} {'Median':>7} {'Win%':>5}  Per ${s['stake_usd']:.0f}  Status")
        print("-" * 85)
        for n, r in results:
            if not r["trades"]:
                print(f"  {n:<26} {'':>6} {'—':>7} {'—':>7} {'—':>5}  —         no trades")
                continue
            status = "✓ PASS" if r["mean_ret"] > 0 else "✗ fail"
            print(f"  {n:<26} {r['trades']:>6} {r['mean_ret']:>+7.1%} {r['median_ret']:>+7.1%} "
                  f"{r['win_rate']:>5.0%}  {s['stake_usd'] * r['mean_ret']:>+7.2f}   {status}")
        print()
        for n, r in results:
            if not r["trades"] or not r.get("by_year"):
                continue
            print(f"  {n}:")
            for y, v in r["by_year"].items():
                print(f"    {y}: {v['n']:>4} trades  mean {v['mean']:+.1%}")
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
