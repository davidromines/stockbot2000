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
DEFAULTS = {"stake_usd": 100.0, "max_spread_frac": 0.5, "min_ask": 0.05, "liquid_universe": 50}

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
}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("options") or {})}


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


def pick(conn, symbol: str, date: str, legs: str, dte: tuple, s: dict) -> list | None:
    """Contracts to buy: legs 'C' (call), 'P' (put) or 'S' (straddle: call + put, same strike).
    The expiry nearest the target days-to-expiry within [min, max]; the strike whose call
    delta is nearest 0.5 (at the money). None when the chain cannot fill it."""
    rows = [r for r in od.chain(conn, symbol, date) if r["delta"] is not None]
    lo, hi, tgt = dte
    # Monthly expiries (the third Friday) first: the public chains keep listing them for
    # weeks, so the exit finds a real quote; a weekly contract drops out within days.
    exps = sorted({r["expiration"] for r in rows if lo <= _days(date, r["expiration"]) <= hi},
                  key=lambda e: (not _monthly(e), abs(_days(date, e) - tgt)))
    for exp in exps:
        calls = [r for r in rows if r["expiration"] == exp and r["cp"] == "C"]
        puts = {r["strike"]: r for r in rows if r["expiration"] == exp and r["cp"] == "P"}
        for c in sorted(calls, key=lambda r: abs(r["delta"] - 0.5)):
            want = {"C": [c], "P": [puts.get(c["strike"])], "S": [c, puts.get(c["strike"])]}[legs]
            if all(q is not None and _ok(q, s) for q in want):
                return [{"exp": q["expiration"], "strike": q["strike"], "cp": q["cp"], "ask": q["ask"],
                         "hs": (q["ask"] - q["bid"]) / (q["ask"] + q["bid"])} for q in want]
            break                    # only the at-the-money strike of each expiry
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
    """(what the position sells for on `date`, modelled?). Each leg: its real bid if the chain
    quotes it; at or after expiration, intrinsic value against the stock's unadjusted price;
    otherwise, with allow_model, Black-Scholes at that day's real implied vol less the half
    spread paid at entry. (None, False) when it cannot be valued that day."""
    tot, modelled = 0.0, False
    for leg in legs:
        if date >= leg["exp"]:
            px = _spot_on_or_before(conn, symbol, leg["exp"])
            if px is None:
                return None, False
            tot += max(px - leg["strike"], 0.0) if leg["cp"] == "C" else max(leg["strike"] - px, 0.0)
            continue
        q = next((r for r in od.chain(conn, symbol, date) if r["expiration"] == leg["exp"]
                  and r["strike"] == leg["strike"] and r["cp"] == leg["cp"]), None)
        if q is not None and q["bid"] is not None:
            tot += q["bid"]
            continue
        if not allow_model:
            return None, False
        px = spot(conn, symbol, date)
        iv = conn.execute("SELECT iv_current FROM option_vol WHERE symbol=? AND date=?", (symbol, date)).fetchone()
        if px is None or not iv or not iv[0]:
            return None, False
        t = _days(date, leg["exp"]) / 365.0
        tot += _bs(px, leg["strike"], t, float(iv[0]), leg["cp"]) * (1 - leg.get("hs", 0.0))
        modelled = True
    return tot, modelled


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
def run(conn, cfg: dict, name: str, dates: list, mode: str = "BACKTEST", signals: dict | None = None) -> int:
    """Walk `dates`: close what is due, then open today's signals. Same code for backtest and paper."""
    s = settings(cfg)
    p = STRATEGIES[name]
    state = {}
    opened = 0
    fn = {"iv_cheap": sig_iv_cheap, "iv_rise": sig_iv_rise, "earnings": sig_earnings,
          "smirk": sig_chain, "ivspread_high": sig_chain, "ivspread_low": sig_chain}.get(p["rule"])
    for d in dates:
        # exits: holding limit, a week before expiration, or the day after an earnings release
        for t in conn.execute("SELECT id, symbol, legs, opened, cost, signal FROM option_trades WHERE mode=? AND "
                              "strategy=? AND closed IS NULL", (mode, name)).fetchall():
            tid, sym, legs, op, cost, sig = t
            legs = json.loads(legs)
            exp = min(leg["exp"] for leg in legs)
            due = None
            if p["rule"] == "earnings" and sig and sig.startswith("earnings ") and d > sig.split(" ", 1)[1]:
                due = "after earnings"
            elif _days(op, d) >= p["hold"] * 7 // 5:
                due = "holding limit"
            elif _days(d, exp) <= 7:
                due = "a week to expiry"
            if d >= exp:
                due = "expired"
            if not due:
                continue
            # A real quote first: up to a week past the due date, unless expiry is near.
            overdue = _days(op, d) - p["hold"] * 7 // 5
            v, modelled = value(conn, sym, legs, d, allow_model=False)
            if v is None:
                if due == "holding limit" and overdue < 7 and _days(d, exp) > 7:
                    continue
                v, modelled = value(conn, sym, legs, d, allow_model=True)
            if v is None:
                continue                          # cannot be valued today: try the next date
            ret = v / cost - 1
            conn.execute("UPDATE option_trades SET closed=?, value=?, ret=?, usd=?, reason=? WHERE id=?",
                         (d, v, ret, s["stake_usd"] * ret, due + (" (modelled price)" if modelled else ""), tid))
        # entries
        if p["rule"] == "stock_signal":
            cands = (signals or {}).get(d, [])
        else:
            cands = fn(conn, d, p, s, state)
        held = {r[0] for r in conn.execute("SELECT symbol FROM option_trades WHERE mode=? AND strategy=? AND "
                                           "closed IS NULL", (mode, name))}
        n_today = 0
        for sym, why in cands:
            if sym in held or n_today >= p.get("per_day", 99):
                continue
            legs = pick(conn, sym, d, p["legs"], p["dte"], s)
            if not legs:
                continue
            cost = sum(leg["ask"] for leg in legs)
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
        sig = stock_signals(conn, cfg, dates[0], dates[-1]) if STRATEGIES[name]["rule"] == "stock_signal" else None
        run(conn, cfg, name, dates, "BACKTEST", sig)
        r = summarize(conn, name)
        conn.execute("INSERT OR REPLACE INTO option_backtests VALUES (?,?,?,?,?,?,?,?,?)",
                     (name, dates[0], dates[-1], r["trades"], r.get("mean_ret"), r.get("median_ret"),
                      r.get("win_rate"), json.dumps(r.get("by_year")),
                      dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
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
                               "holding_period": p["hold"], "parameters": {"dte": list(p["dte"]),
                                                                          "top": p.get("top"), "per_day": p.get("per_day")}},
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
    """Fund equity on `date`: capital + realised dollars + open positions at today's bid."""
    s = settings(cfg)
    cap = conn.execute("SELECT capital_usd FROM option_funds WHERE name=?", (name,)).fetchone()[0]
    real = conn.execute("SELECT COALESCE(SUM(usd),0) FROM option_trades WHERE mode='PAPER' AND strategy=? AND "
                        "ret IS NOT NULL", (name,)).fetchone()[0]
    unreal, n = 0.0, 0
    for sym, legs, cost in conn.execute("SELECT symbol, legs, cost FROM option_trades WHERE mode='PAPER' AND "
                                        "strategy=? AND closed IS NULL", (name,)).fetchall():
        v, _ = value(conn, sym, json.loads(legs), date, allow_model=True)
        unreal += s["stake_usd"] * ((v if v is not None else cost) / cost - 1)
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
    if a.step:
        print(json.dumps(step(conn, cfg), indent=1, default=float))
    if a.report or a.backtest:
        for n in names:
            r = summarize(conn, n)
            if not r["trades"]:
                print(f"  {n:<24} no trades")
                continue
            print(f"  {n:<24} {r['trades']:>5} trades  mean {r['mean_ret']:+.1%}  median {r['median_ret']:+.1%}  "
                  f"won {r['win_rate']:.0%}  ${settings(cfg)['stake_usd'] * r['mean_ret']:+.2f} per "
                  f"${settings(cfg)['stake_usd']:.0f}  ({r['modelled_exits']} exits modelled)")
            for y, v in r["by_year"].items():
                print(f"      {y}: {v['n']:>4} trades  mean {v['mean']:+.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
