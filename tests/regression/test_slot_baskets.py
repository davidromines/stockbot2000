"""
Basket slots and the book beta cap (Stage AD2.1 / AD3.1 / AD3.4; owner H6, H7a, H7b, 2026-10-19), through the REAL
ExecutionEngine, RiskEngine and kill switches in SIMULATION.

Pinned: a basket-mode slot buys up to k names, split by inverse volatility, summing to the slot's capital; a stopped
name's vacancy is refilled on the next pass; reconciliation and P&L count every basket member; a mode NOT listed keeps
the original one-position-per-slot path; the beta cap refuses a purchase that would lift the book's beta above the cap.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paper_trading as pt
import quotes as qt
import slot_trader as st
import slots

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


GENOME = {"entry": {"op": "gt"}, "exit": {"op": "lt"}, "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20}}
NAMES = {"AAA": (50.0, 1.0), "BBB": (20.0, 1.2), "CCC": (40.0, 4.0), "DDD": (10.0, 0.2), "EEE": (30.0, 0.9)}   # price, ATR
BETAS = {"AAA": 1.0, "BBB": 1.2, "CCC": 2.8, "DDD": 0.8, "EEE": 1.1}


def fixture():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    c.execute("CREATE TABLE risk_metrics (ticker TEXT, date TEXT, beta REAL, ivol REAL, alpha REAL)")
    for d in ("2026-09-22", "2026-09-23"):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
    for t, (px, atr) in NAMES.items():
        c.execute("INSERT INTO features VALUES (?, '2026-09-23', ?, 5e7)", (t, atr))
        c.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', 5e9)", (t,))
        c.execute("INSERT INTO risk_metrics VALUES (?, '2026-09-30', ?, 0.3, 0)", (t, BETAS[t]))
    st.init(c)
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason) "
              "VALUES ('2026-09-23T00:00:00', 1, 'ASSIGN', 'fx_test', 1, 20.0, 'SIMULATION', 't')")
    c.commit()
    return c


slots.genome_for = lambda conn, k, v: GENOME
pt._genome_signals = lambda conn, cfg, g: (pd.DataFrame({"ticker": ["AAA", "BBB", "CCC", "DDD", "EEE"]}), set())
quotes = {t: px for t, (px, _a) in NAMES.items()}
BASKET = {"slots": {"basket": {"k": 4, "weighting": "inverse_vol", "min_dollars": 1.0, "modes": ["SIMULATION"]}}}

# --- a basket slot -----------------------------------------------------------------------------------------------
c = fixture()
r = st.trade(c, BASKET, "SIMULATION", qt.FixedQuotes(quotes, conn=c))
buys = [x for x in r if x["action"] == "BUY" and x["status"] == "filled"]
check("a basket slot buys k = 4 names in one pass", [b["symbol"] for b in buys] == ["AAA", "BBB", "CCC", "DDD"], r)
pos = st.positions_list(c, "SIMULATION")
dollars = {p["symbol"]: float(p["quantity"]) * float(p["price"]) for p in pos}
check("the basket spends the slot's $20", abs(sum(dollars.values()) - 20.0) < 0.05, dollars)
inv = {t: NAMES[t][0] / NAMES[t][1] for t in dollars}
exp = {t: 20.0 * v / sum(inv.values()) for t, v in inv.items()}
check("weights are inverse to volatility (ATR/price)", all(abs(dollars[t] - exp[t]) < 0.05 for t in dollars), (dollars, exp))
check("the most volatile name gets the fewest dollars", min(dollars, key=dollars.get) == "CCC")
check("the original view (one per slot) still answers, the basket view holds all four",
      len(st.open_positions(c, "SIMULATION")) == 1 and len(st._positions(c, BASKET, "SIMULATION")) == 4)
broker, _ = st._build(c, BASKET, "SIMULATION", qt.FixedQuotes(quotes, conn=c))
ok, diffs = st.reconcile(c, broker, "SIMULATION", BASKET)
check("reconciliation counts every basket member", ok, diffs)
check("P&L pairs trades by slot and symbol", st.pnl(c, BASKET, "SIMULATION")["open_positions"] == 4)
r2 = st.trade(c, BASKET, "SIMULATION", qt.FixedQuotes(quotes, conn=c))
check("a full basket buys nothing more", not [x for x in r2 if x["action"] == "BUY"], r2)

# a name stops out -> the vacancy is refilled from the next candidate
low = {**quotes, "BBB": 15.0}                 # BBB: entry 20, ATR 1.2 x 2 -> stop 17.6; 15 breaches it
r3 = st.monitor(c, BASKET, "SIMULATION", qt.FixedQuotes(low, conn=c))
check("a basket member's own stop closes only that member", [x["symbol"] for x in r3 if x["action"] == "CLOSE"] == ["BBB"], r3)
r4 = st.trade(c, BASKET, "SIMULATION", qt.FixedQuotes(low, conn=c))
refill = [x["symbol"] for x in r4 if x["action"] == "BUY" and x["status"] == "filled"]
check("the vacancy is refilled with the next candidate not held", refill == ["EEE"], r4)
check("...up to the slot's remaining capital", sum(float(p["quantity"]) * float(p["price"])
                                                for p in st.positions_list(c, "SIMULATION")) <= 20.05)

# --- a mode that is not listed keeps the original path ----------------------------------------------------------------
c2 = fixture()
r5 = st.trade(c2, BASKET, "SHADOW", qt.FixedQuotes(quotes, conn=c2))
check("SHADOW is not a basket mode here: the original path decides one name", st.basket_cfg(BASKET, "SHADOW") is None
      and [x["symbol"] for x in r5 if x["action"] == "BUY"][:1] == ["AAA"], r5)
check("LIVE is never a basket mode unless listed", st.basket_cfg(BASKET, "LIVE") is None)

# --- the book beta cap ---------------------------------------------------------------------------------------------
CAP = {"slots": {"book": {"beta_cap": 1.3}}}
c3 = fixture()
held = [{"symbol": "AAA", "quantity": 0.4, "price": 50.0, "strategy_key": "fx_a"}]   # $20 at beta 1.0
check("a calm addition passes the cap", st.beta_block(c3, CAP, held, "DDD", 20.0) is None)
why = st.beta_block(c3, CAP, held, "CCC", 20.0)
check("a high-beta addition that lifts the book above 1.3 is refused, with the number", why and "1.90" in why, why)
check("intraday positions are not part of the medium-term book",
      st.beta_block(c3, CAP, [{"symbol": "CCC", "quantity": 1, "price": 40, "strategy_key": "intraday:momentum_runner"}],
                    "AAA", 20.0) is None)
check("an unknown beta is assumed 1.5, not calm", st.beta_block(c3, CAP, [], "ZZZ", 20.0) is not None)
check("no cap configured: nothing is refused", st.beta_block(c3, {}, held, "CCC", 20.0) is None)
c4 = fixture()
pt._genome_signals = lambda conn, cfg, g: (pd.DataFrame({"ticker": ["CCC", "AAA"]}), set())
r6 = st.trade(c4, CAP, "SIMULATION", qt.FixedQuotes(quotes, conn=c4))
check("on the original path the cap skips the high-beta pick for the next candidate",
      [x["symbol"] for x in r6 if x["action"] == "BUY"] == ["AAA"]
      and any("beta" in str(x.get("reason")) and x.get("symbol") == "CCC" for x in r6), r6)

# --- the entry-timing experiment (AD2.5): off unless switched on; delays entries only, on even sessions --------------
from datetime import datetime
ON = {"slots": {"entry_timing": {"experiment": True, "delay_until": "10:00"}}}
even, odd = datetime(2026, 10, 21, 9, 35, tzinfo=qt.NY), datetime(2026, 10, 20, 9, 35, tzinfo=qt.NY)
check("timing experiment off by default: never waits", st.entry_wait({}, even) is None)
check("on an even session entries wait until 10:00 ET; odd sessions and after 10:00 do not",
      st.entry_wait(ON, even) and st.entry_wait(ON, odd) is None and st.entry_wait(ON, even.replace(hour=10, minute=1)) is None)
c5 = fixture()
pt._genome_signals = lambda conn, cfg, g: (pd.DataFrame({"ticker": ["AAA", "BBB"]}), set())
st._ny_now = lambda: even
r7 = st.trade(c5, ON, "SIMULATION", qt.FixedQuotes(quotes, conn=c5))
check("a waiting entry pass buys nothing and says why", not [x for x in r7 if x["action"] == "BUY"]
      and any(x.get("status") == "waiting" for x in r7), r7)

print()
print("  ALL PASS" if not FAILED else f"  {len(FAILED)} FAILED: {FAILED}")
sys.exit(1 if FAILED else 0)
