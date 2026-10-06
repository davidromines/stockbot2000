"""
options_lab.py, strategies that SELL premium (plain short straddle / put / call, short strangle,
credit spreads): sold at the BID with every sold leg flagged short, bought back at the ASK, profit
taken only once the buy-back price has decayed to (1 - take_profit) of the credit, return
1 - buy-back / credit, and the same sign when a paper fund is marked.

Regression guard: a spec with short=True but no is_credit was entered at the ASK with its legs
unflagged, so take-profit fired on day one and 88-90% of the trades "won" 17x-19x% in about a week.
Synthetic chains in memory; the fetch log is pre-filled so nothing reaches the network.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import options_lab as ol

FAILED = []
CFG = {"options": {"stake_usd": 100.0, "max_contract_cost_usd": 1000.0}}
D0, D1, D2, EXP = "2024-01-08", "2024-01-10", "2024-01-16", "2024-02-09"


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def near(a, b, tol=1e-9):
    return a is not None and abs(a - b) < tol


def quote(c, date, strike, cp, bid, ask, delta=0.5, exp=EXP):
    c.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
              "VALUES (?,?,?,?,?,?,?,0.3,?)", (date, "AAA", exp, strike, cp, bid, ask, delta))
    c.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','AAA',?,1,'t')", (date,))


def new_db():
    """Entry day: calls 2.0 / 2.2 and puts 1.8 / 2.0 at 95, 100 and 105 — the 100 strike is at the money."""
    c = sqlite3.connect(":memory:")
    ol.init(c)
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    for k, dc in ((95.0, 0.7), (100.0, 0.52), (105.0, 0.3)):
        quote(c, D0, k, "C", 2.0, 2.2, dc)
        quote(c, D0, k, "P", 1.8, 2.0, dc - 1)
    return c


def later(c, date, call=None, put=None):
    """Quotes on a later day for the 100 strike: call=(bid, ask), put=(bid, ask)."""
    if call:
        quote(c, date, 100.0, "C", call[0], call[1])
    if put:
        quote(c, date, 100.0, "P", put[0], put[1])


def spec(legs, **kw):
    return {"rule": "stock_signal", "legs": legs, "dte": (21, 60, 35), "hold": 5, "per_day": 1, **kw}


def walk(c, name, p, dates, mode="BACKTEST"):
    ol.STRATEGIES[name] = p
    ol.run(c, CFG, name, dates, mode, {D0: [("AAA", "test signal")]})
    return c.execute("SELECT cost, closed, value, ret, usd, reason, legs FROM option_trades WHERE strategy=?",
                     (name,)).fetchone()


def main():
    import json

    # --- which specs sell premium ---------------------------------------------------
    sold = ["opt_vrp_straddle_short", "opt_short_put_uptrend", "opt_earnings_iv_crush", "opt_short_strangle",
            "opt_short_call_uptrend", "opt_iron_condor", "opt_ic_earnings", "opt_put_credit_spread"]
    bought = [n for n in ol.STRATEGIES if n not in sold and not n.startswith("t_")]
    check("every registered short / credit strategy is classified as selling premium",
          all(ol.sells_premium(ol.STRATEGIES[n]) for n in sold),
          [n for n in sold if not ol.sells_premium(ol.STRATEGIES[n])])
    check("long options and debit spreads are not",
          not any(ol.sells_premium(ol.STRATEGIES[n]) for n in bought),
          [n for n in bought if ol.sells_premium(ol.STRATEGIES[n])])

    # --- short straddle: entry at the bid, both legs short ------------------------------
    c = new_db()
    later(c, D1, (2.0, 2.2), (1.8, 2.0))
    t = walk(c, "t_short_straddle", spec("S", short=True, take_profit=0.50), [D0, D1])
    check("short straddle: opened on the signal", t is not None, t)
    legs = json.loads(t[6])
    check("short straddle: entered at the BIDS (a credit of 2.0 + 1.8), not the asks",
          near(t[0], 3.8), t[0])
    check("short straddle: every sold leg is flagged short", len(legs) == 2 and all(l.get("short") for l in legs), legs)
    check("short straddle: no take-profit on day one at unchanged quotes (still open)", t[1] is None, t)

    # --- unchanged quotes through the holding limit: the round trip is a small loss -------------
    c = new_db()
    later(c, D1, (2.0, 2.2), (1.8, 2.0))
    later(c, D2, (2.0, 2.2), (1.8, 2.0))
    t = walk(c, "t_short_straddle", spec("S", short=True, take_profit=0.50), [D0, D1, D2])
    check("unchanged quotes: closed at the holding limit, bought back at the asks (2.2 + 2.0)",
          t[1] == D2 and t[5] == "holding limit" and near(t[2], 4.2), t)
    check("unchanged quotes: return is 1 - buy-back / credit, a small loss, never a windfall",
          near(t[3], 1 - 4.2 / 3.8) and t[3] < 0 and near(t[4], 100 * t[3]), t)

    # --- decayed quotes through the holding limit: a gain, still no take-profit -------------------
    c = new_db()
    later(c, D1, (1.8, 2.0), (1.6, 1.8))
    later(c, D2, (1.5, 1.6), (1.4, 1.5))
    t = walk(c, "t_short_straddle", spec("S", short=True, take_profit=0.50), [D0, D1, D2])
    check("buy-back 3.1 against a 3.8 credit (above the 1.9 target): holding-limit exit, not take-profit",
          t[1] == D2 and t[5] == "holding limit" and near(t[2], 3.1), t)
    check("return is 1 - 3.1 / 3.8, positive", near(t[3], 1 - 3.1 / 3.8) and t[3] > 0, t)

    # --- take-profit: fires at (1 - tp) x credit and not a cent earlier ------------------------------
    c = new_db()
    later(c, D1, (0.8, 0.9), (0.7, 0.9))
    t = walk(c, "t_short_straddle", spec("S", short=True, take_profit=0.50), [D0, D1])
    check("buy-back 1.8 <= 0.5 x 3.8: take-profit fires the day it is reached",
          t[1] == D1 and t[5].startswith("take profit") and near(t[2], 1.8), t)
    check("take-profit return is 1 - 1.8 / 3.8", near(t[3], 1 - 1.8 / 3.8), t)
    c = new_db()
    later(c, D1, (0.8, 0.95), (0.7, 1.0))
    t = walk(c, "t_short_straddle", spec("S", short=True, take_profit=0.50), [D0, D1])
    check("buy-back 1.95 > 1.9: take-profit does not fire", t[1] is None, t)

    # --- single-sided shorts ------------------------------------------------------------------------------
    c = new_db()
    later(c, D1, put=(1.0, 1.1))
    later(c, D2, put=(0.9, 1.0))
    t = walk(c, "t_short_put", spec("P", short=True, take_profit=0.50), [D0, D1, D2])
    check("short put: entered at the put bid 1.8 with the leg flagged short",
          near(t[0], 1.8) and all(l.get("short") for l in json.loads(t[6])), t)
    check("short put: bought back at the ask 1.0 and earns 1 - 1.0 / 1.8",
          t[1] in (D1, D2) and near(t[3], 1 - t[2] / 1.8) and t[3] > 0, t)
    c = new_db()
    later(c, D1, call=(2.0, 2.2))
    t = walk(c, "t_short_call", spec("C", short=True, take_profit=0.50), [D0, D1])
    check("short call: entered at the call bid 2.0 with the leg flagged short, open at unchanged quotes",
          near(t[0], 2.0) and all(l.get("short") for l in json.loads(t[6])) and t[1] is None, t)

    # --- short strangle (both legs already flagged short by pick) --------------------------------------------
    c = new_db()
    d_far = "2024-01-12"
    later(c, d_far)
    quote(c, d_far, 105.0, "C", 1.0, 1.1, 0.3)
    quote(c, d_far, 95.0, "P", 0.8, 0.9, -0.3)
    t = walk(c, "t_short_strangle", spec("CS", short=True, take_profit=0.50), [D0, d_far])
    # 105 call and 95 put: the 0.30-delta strikes of the fixture; entered at their bids 2.0 + 1.8.
    check("short strangle: entered at the bids (a credit), both legs short",
          t is not None and near(t[0], 3.8) and all(l.get("short") for l in json.loads(t[6])), t)

    # --- a paper fund is marked with the same sign ------------------------------------------------------------
    c = new_db()
    c.execute("INSERT INTO option_funds VALUES ('t_short_straddle', 1000.0, ?, 'open')", (D0,))
    later(c, D1, (1.7, 1.8), (1.5, 1.6))
    ol.STRATEGIES["t_short_straddle"] = spec("S", short=True, take_profit=0.50)
    ol.run(c, CFG, "t_short_straddle", [D0, D1], "PAPER", {D0: [("AAA", "test signal")]})
    eq = ol.mark(c, CFG, "t_short_straddle", D1)
    check("mark: an open short is in profit when the buy-back price has fallen (1 - 3.4 / 3.8)",
          eq["open_positions"] == 1 and near(eq["unrealized_usd"], 100 * (1 - 3.4 / 3.8)) and eq["unrealized_usd"] > 0, eq)
    check("mark: equity = capital + unrealised", near(eq["equity_usd"], 1000.0 + eq["unrealized_usd"]), eq)
    c.execute("INSERT INTO option_funds VALUES ('t_call', 1000.0, ?, 'open')", (D0,))
    ol.STRATEGIES["t_call"] = spec("C")
    ol.run(c, CFG, "t_call", [D0, D1], "PAPER", {D0: [("AAA", "test signal")]})
    eq = ol.mark(c, CFG, "t_call", D1)
    # bought at the ask 2.2, worth the bid 1.7 -> a loss on the one real contract (x100 shares)
    check("mark: an open long is marked per contract ((1.7 - 2.2) x 100)", near(eq["unrealized_usd"], 100 * (1.7 - 2.2)), eq)

    # --- mixed positions ------------------------------------------------------------------------------------------
    c = new_db()
    for k, bid, ask, d in ((100.0, 3.0, 3.2, 0.5), (95.0, 1.0, 1.2, -0.3)):
        quote(c, D1, k, "P", bid, ask, d)
    c.execute("DELETE FROM option_quotes WHERE date=? AND strike=100 AND cp='P'", (D0,))
    quote(c, D0, 100.0, "P", 3.0, 3.2, -0.48)
    c.execute("DELETE FROM option_quotes WHERE date=? AND strike=95 AND cp='P'", (D0,))
    quote(c, D0, 95.0, "P", 1.0, 1.2, -0.3)
    pcs = ol.pick(c, "AAA", D0, "PCS", (21, 60, 35), ol.settings(CFG))
    check("PCS: short ATM put 100 (bid 3.0) + long put 95 (ask 1.2) = a 1.8 credit",
          pcs and pcs[0].get("short") and near(pcs[0]["bid"] - pcs[1]["ask"], 1.8), pcs)
    # buy-back: short 100 put ask 3.2 less long 95 put bid 1.0 = 2.2, inside the 5.0 wing
    v, m = ol.close_value(c, {"is_credit": True}, "AAA", pcs, D1)
    check("credit spread: cost to close = short ask - long bid", near(v, 3.2 - 1.0) and m is False, (v, m))
    c.execute("UPDATE option_quotes SET bid=6.8, ask=7.0 WHERE date=? AND strike=100 AND cp='P'", (D1,))
    v, m = ol.close_value(c, {"is_credit": True}, "AAA", pcs, D1)
    check("credit spread: capped at the widest wing (100 - 95 = 5.0), the most it can lose",
          near(v, 5.0), v)
    bcs_legs = [{"exp": EXP, "strike": 100.0, "cp": "C", "ask": 2.2, "bid": 2.0},
                {"exp": EXP, "strike": 105.0, "cp": "C", "ask": 1.2, "bid": 1.0, "short": True}]
    quote(c, D1, 100.0, "C", 3.0, 3.2)
    quote(c, D1, 105.0, "C", 0.9, 1.0, 0.3)
    v, m = ol.close_value(c, {"is_debit_spread": True}, "AAA", bcs_legs, D1)
    check("debit spread: receipt = long bid - short ask (3.0 - 1.0), uncapped", near(v, 2.0), v)
    check("debit spread return is value / debit - 1", near(ol.trade_return({"is_debit_spread": True}, 2.0, 1.2), 2.0 / 1.2 - 1))
    v, m = ol.close_value(c, {}, "AAA", bcs_legs[:1], D1)
    check("long call: closed at the bid", near(v, 3.0), v)
    check("no quote for a leg: None, never a made-up price",
          ol.close_value(c, {"is_credit": True}, "AAA", pcs, "2024-01-11")[0] is None)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
