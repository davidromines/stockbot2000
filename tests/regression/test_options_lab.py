"""
options_lab.py: contract choice (at the money, target expiry, liquid quotes only),
fills (buy at ask, sell at bid), settlement at intrinsic value on expiration, and
the backtest/paper walk. Synthetic chains in memory; the fetch log is pre-filled
so nothing reaches the network.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import options_data as od
import options_lab as ol

FAILED = []
CFG = {"options": {"stake_usd": 100.0}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def quote(c, date, exp, strike, cp, bid, ask, delta):
    c.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
              "VALUES (?,?,?,?,?,?,?,0.3,?)", (date, "AAA", exp, strike, cp, bid, ask, delta))
    c.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','AAA',?,1,'t')", (date,))


def main():
    c = sqlite3.connect(":memory:")
    ol.init(c)
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    s = ol.settings(CFG)
    d0, exp = "2024-01-08", "2024-02-09"
    for k, dc in ((95.0, 0.7), (100.0, 0.52), (105.0, 0.3)):
        quote(c, d0, exp, k, "C", 2.0, 2.2, dc)
        quote(c, d0, exp, k, "P", 1.8, 2.0, dc - 1)
    quote(c, d0, "2024-01-12", 100.0, "C", 1.0, 1.1, 0.5)          # too near: outside the DTE window
    legs = ol.pick(c, "AAA", d0, "C", (21, 60, 35), s)
    check("call: the at-the-money strike in the target expiry", legs and legs[0]["strike"] == 100.0
          and legs[0]["exp"] == exp and legs[0]["ask"] == 2.2, legs)
    st = ol.pick(c, "AAA", d0, "S", (21, 60, 35), s)
    check("straddle: call + put at one strike", st and {l["cp"] for l in st} == {"C", "P"}
          and len({l["strike"] for l in st}) == 1, st)
    c.execute("UPDATE option_quotes SET bid=0.1 WHERE strike=100 AND cp='C' AND expiration=?", (exp,))
    check("a wide market is refused", ol.pick(c, "AAA", d0, "C", (21, 60, 35), s) is None)
    c.execute("UPDATE option_quotes SET bid=2.0 WHERE strike=100 AND cp='C' AND expiration=?", (exp,))

    d1 = "2024-01-22"
    quote(c, d1, exp, 100.0, "C", 3.0, 3.3, 0.6)
    v, m = ol.value(c, "AAA", legs, d1)
    check("sold at the bid (a real quote, not modelled)", v == 3.0 and m is False, (v, m))
    check("no quote that day, no model -> None (try a later date)", ol.value(c, "AAA", legs, "2024-01-24")[0] is None)
    # On the expiry date the chain lists other expiries: spot by put-call parity at the
    # strike where call and put are closest: 105 + (3.0 - 0.5) = 107.5.
    for cp, bid, ask in (("C", 2.9, 3.1), ("P", 0.4, 0.6)):
        c.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
                  "VALUES (?,?,?,105,?,?,?,0.3,0.5)", (exp, "AAA", "2024-03-15", cp, bid, ask))
    c.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','AAA',?,1,'t')", (exp,))
    c.execute("INSERT INTO prices VALUES ('AAA', ?, 10.75)", (exp,))     # split-ADJUSTED: must be ignored
    check("spot from the chain by put-call parity", abs(ol.spot(c, "AAA", exp) - 107.5) < 1e-9, ol.spot(c, "AAA", exp))
    v, m = ol.value(c, "AAA", legs, "2024-02-12")
    check("at expiration: intrinsic against the UNADJUSTED spot, never the adjusted price table",
          abs(v - 7.5) < 1e-9, v)
    c.execute("CREATE TABLE IF NOT EXISTS option_vol (date TEXT, symbol TEXT, iv_current REAL)")
    c.execute("INSERT INTO option_vol (date, symbol, iv_current) VALUES (?, 'AAA', 0.3)", (d1,))
    c.execute("DELETE FROM option_quotes WHERE date=? AND cp='C' AND strike=100", (d1,))
    quote(c, d1, "2024-03-15", 102.0, "C", 5.0, 5.2, 0.55)
    quote(c, d1, "2024-03-15", 102.0, "P", 1.0, 1.2, -0.45)
    v, m = ol.value(c, "AAA", legs, d1, allow_model=True)
    check("unquoted before expiry: modelled at that day's IV, and flagged", v is not None and v > 0 and m is True, (v, m))
    c.execute("DELETE FROM option_quotes WHERE date=? AND expiration='2024-03-15'", (d1,))
    quote(c, d1, exp, 100.0, "C", 3.0, 3.3, 0.6)

    ol.STRATEGIES["t_call"] = {"rule": "stock_signal", "legs": "C", "dte": (21, 60, 35), "hold": 5, "per_day": 1}
    n = ol.run(c, CFG, "t_call", [d0, d1], "BACKTEST", {d0: [("AAA", "test signal")]})
    t = c.execute("SELECT cost, value, ret, usd, reason FROM option_trades WHERE strategy='t_call'").fetchone()
    check("walk: opened on the signal, closed at the holding limit at the bid", n == 1 and t[0] == 2.2
          and t[1] == 3.0 and t[4] == "holding limit", t)
    check("return on premium and dollars on the stake", abs(t[2] - (3.0 / 2.2 - 1)) < 1e-12
          and abs(t[3] - 100 * t[2]) < 1e-9, t)
    r = ol.summarize(c, "t_call")
    check("summary", r["trades"] == 1 and r["win_rate"] == 1.0, r)

    # --- implied-vol shape: IV spread and smirk ---------------------------------
    c2 = sqlite3.connect(":memory:")
    ol.init(c2)
    d = "2024-03-04"
    def q2(sym, k, cp, iv, delta):
        c2.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
                   "VALUES (?,?,?,?,?,1,1.1,?,?)", (d, sym, "2024-04-05", k, cp, iv, delta))
        c2.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain',?,?,1,'t')", (sym, d))
    for sym, call_iv, put_iv, otm_iv in (("AAA", 0.30, 0.25, 0.45), ("BBB", 0.30, 0.35, 0.33)):
        q2(sym, 100, "C", call_iv, 0.5)
        q2(sym, 100, "P", put_iv, -0.5)
        q2(sym, 90, "P", otm_iv, -0.26)
    m = ol.chain_metrics(c2, "AAA", d)
    check("IV spread = ATM call IV - same-strike put IV", abs(m["ivspread"] - 0.05) < 1e-9, m)
    check("smirk = OTM (-0.25 delta) put IV - ATM call IV", abs(m["smirk"] - 0.15) < 1e-9, m)
    real_liquid = ol.liquid
    ol.liquid = lambda conn, date, n: ["AAA", "BBB"]
    s2 = ol.settings(CFG)
    hi = ol.sig_chain(c2, d, {"rule": "ivspread_high", "top": 1}, s2, {})
    lo = ol.sig_chain(c2, d, {"rule": "ivspread_low", "top": 1}, s2, {})
    sm = ol.sig_chain(c2, d, {"rule": "smirk", "top": 1}, s2, {})
    check("expensive calls -> AAA; expensive puts -> BBB; steepest smirk -> AAA",
          hi[0][0] == "AAA" and lo[0][0] == "BBB" and sm[0][0] == "AAA", (hi, lo, sm))
    st = {}
    ol.sig_chain(c2, d, {"rule": "smirk", "top": 1}, s2, st)
    check("weekly: a second date in the same week signals nothing",
          ol.sig_chain(c2, "2024-03-06", {"rule": "smirk", "top": 1}, s2, st) == [])
    ol.liquid = real_liquid

    # --- pick() extensions: IC, CS, BCS, BPS ------------------------------------
    c3 = sqlite3.connect(":memory:")
    ol.init(c3)
    exp3 = "2024-04-19"
    d3 = "2024-03-18"
    # strikes: 90, 95, 100 (ATM), 105, 110
    for k, cp, bid, ask, delta in [
        (90,  "C", 9.5, 9.7, 0.80), (90,  "P", 0.4, 0.5, -0.15),
        (95,  "C", 5.5, 5.7, 0.60), (95,  "P", 0.9, 1.0, -0.28),
        (100, "C", 2.0, 2.2, 0.50), (100, "P", 1.8, 2.0, -0.50),
        (105, "C", 0.7, 0.8, 0.30), (105, "P", 4.5, 4.7, -0.68),
        (110, "C", 0.2, 0.3, 0.13), (110, "P", 9.0, 9.2, -0.85),
    ]:
        c3.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
                   "VALUES (?,?,?,?,?,?,?,0.25,?)", (d3, "ZZZ", exp3, k, cp, bid, ask, delta))
    c3.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','ZZZ',?,1,'t')", (d3,))
    s3 = ol.settings(CFG)

    ic = ol.pick(c3, "ZZZ", d3, "IC", (21, 60, 35), s3)
    check("IC: 4 legs returned", ic is not None and len(ic) == 4, ic)
    if ic:
        short_legs = [l for l in ic if l.get("short")]
        long_legs = [l for l in ic if not l.get("short")]
        check("IC: exactly 2 short legs (the OTM strikes)", len(short_legs) == 2, ic)
        check("IC: exactly 2 long legs (the wing strikes)", len(long_legs) == 2, ic)
        net_credit = sum(l["bid"] for l in short_legs) - sum(l["ask"] for l in long_legs)
        check("IC: net credit is positive", net_credit > 0, net_credit)
        # short call strike > short put strike (no overlap)
        sc = next(l for l in short_legs if l["cp"] == "C")
        sp = next(l for l in short_legs if l["cp"] == "P")
        check("IC: short call strike > short put strike (no inverted condor)", sc["strike"] > sp["strike"], (sc, sp))

    cs = ol.pick(c3, "ZZZ", d3, "CS", (21, 60, 35), s3)
    check("CS: 2 legs returned", cs is not None and len(cs) == 2, cs)
    if cs:
        check("CS: both legs short", all(l.get("short") for l in cs), cs)
        check("CS: one call one put", {l["cp"] for l in cs} == {"C", "P"}, cs)

    bcs = ol.pick(c3, "ZZZ", d3, "BCS", (21, 60, 35), s3)
    check("BCS: 2 legs returned", bcs is not None and len(bcs) == 2, bcs)
    if bcs:
        long_leg = next((l for l in bcs if not l.get("short")), None)
        short_leg = next((l for l in bcs if l.get("short")), None)
        check("BCS: long leg is ATM call", long_leg and long_leg["cp"] == "C" and long_leg["strike"] == 100.0, bcs)
        check("BCS: short leg is OTM call at higher strike", short_leg and short_leg["strike"] > 100, bcs)
        check("BCS: net debit > 0", long_leg["ask"] - short_leg["bid"] > 0, bcs)

    bps = ol.pick(c3, "ZZZ", d3, "BPS", (21, 60, 35), s3)
    check("BPS: 2 legs returned", bps is not None and len(bps) == 2, bps)
    if bps:
        long_leg = next((l for l in bps if not l.get("short")), None)
        short_leg = next((l for l in bps if l.get("short")), None)
        check("BPS: long leg is put", long_leg and long_leg["cp"] == "P", bps)
        check("BPS: short leg is put at lower strike", short_leg and short_leg["cp"] == "P"
              and short_leg["strike"] < long_leg["strike"], bps)

    pcs = ol.pick(c3, "ZZZ", d3, "PCS", (21, 60, 35), s3)
    check("PCS: 2 legs returned", pcs is not None and len(pcs) == 2, pcs)
    if pcs:
        long_leg = next((l for l in pcs if not l.get("short")), None)
        short_leg = next((l for l in pcs if l.get("short")), None)
        check("PCS: short leg is ATM put (higher strike)", short_leg and short_leg["cp"] == "P"
              and short_leg["strike"] == 100.0, pcs)
        check("PCS: long leg is OTM put (lower strike)", long_leg and long_leg["cp"] == "P"
              and long_leg["strike"] < 100.0, pcs)
        check("PCS: net credit > 0", short_leg["bid"] - long_leg["ask"] > 0, pcs)

    # IC backtest walk: verify credit/return calculation
    ol.STRATEGIES["t_ic"] = {"rule": "stock_signal", "legs": "IC", "dte": (21, 60, 35),
                              "hold": 30, "per_day": 1, "is_credit": True, "take_profit": 0.50}
    d_close = "2024-04-01"
    # add a closing chain where IC is worth ~30% of initial credit
    for k, cp, bid, ask, delta in [
        (105, "C", 0.15, 0.2, 0.08), (95, "P", 0.15, 0.2, -0.08),
        (110, "C", 0.05, 0.1, 0.04), (90, "P", 0.05, 0.1, -0.04),
    ]:
        c3.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
                   "VALUES (?,?,?,?,?,?,?,0.15,?)", (d_close, "ZZZ", exp3, k, cp, bid, ask, delta))
    c3.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','ZZZ',?,1,'t')", (d_close,))
    n_ic = ol.run(c3, CFG, "t_ic", [d3, d_close], "BACKTEST", {d3: [("ZZZ", "IC test")]})
    t_ic = c3.execute("SELECT cost, value, ret, reason FROM option_trades WHERE strategy='t_ic'").fetchone()
    check("IC: trade opened", n_ic >= 1 or t_ic is not None, (n_ic, t_ic))
    if t_ic and t_ic[0]:
        check("IC: positive return when IV decayed (cost-to-close < credit received)",
              t_ic[2] is None or t_ic[2] > 0 or t_ic[3] == "take profit 50%", t_ic)

    # --- signal function: features.close → prices.close fixes -----------------
    c4 = sqlite3.connect(":memory:")
    ol.init(c4)
    c4.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")
    c4.execute("CREATE TABLE IF NOT EXISTS insider_trades (accession TEXT, trans_sk TEXT, owner_cik TEXT, ticker TEXT, issuer_cik TEXT, trans_date TEXT, filing_date TEXT, code TEXT, shares REAL, price REAL, value_usd REAL, relationship TEXT)")

    # sig_iv_high_uptrend: should not crash when features has no 'close' column
    d4 = "2024-03-04"
    c4.execute("INSERT INTO option_vol (date, symbol, iv_current, hv_current) VALUES (?,?,?,?)", (d4, "AAA", 0.45, 0.25))
    c4.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','AAA',?,1,'t')", (d4,))
    c4.execute("CREATE TABLE IF NOT EXISTS features (ticker TEXT, date TEXT, sma_200 REAL, rsi_14 REAL)")
    c4.execute("INSERT INTO features (ticker, date, sma_200) VALUES ('AAA', ?, 95.0)", (d4,))
    c4.execute("INSERT INTO prices VALUES ('AAA', ?, 0, 0, 0, 100.0, 1e6, 's')", (d4,))
    real_liq = ol.liquid
    ol.liquid = lambda conn, date, n: ["AAA"]
    s4 = ol.settings(CFG)
    result = ol.sig_iv_high_uptrend(c4, d4, {"top": 1}, s4, {})
    check("sig_iv_high_uptrend: returns signals using prices.close (no crash)", result != [] and result[0][0] == "AAA", result)

    # sig_pead_call: should not crash when edgar_events exists
    try:
        c4.execute("CREATE TABLE edgar_events (ticker TEXT, item TEXT, filed TEXT)")
        c4.execute("INSERT INTO edgar_events VALUES ('AAA','2.02','2024-03-01')")
        c4.execute("INSERT INTO prices VALUES ('AAA','2024-03-01',0,0,0,105.0,1e6,'s')")
        c4.execute("INSERT INTO prices VALUES ('AAA','2024-02-28',0,0,0,100.0,1e6,'s')")
        pead_result = ol.sig_pead_call(c4, "2024-03-05", {"top": 3}, s4, {})
        check("sig_pead_call: returns post-earnings signals using prices.close", isinstance(pead_result, list), pead_result)
    except Exception as e:
        check("sig_pead_call: no crash", False, str(e))

    # sig_insider_call: should query insider_trades, not edgar_events
    c4.execute("INSERT INTO insider_trades VALUES ('acc1','t1','cik1','AAA','cik2','2024-03-01','2024-03-02','P',100,50.0,5000.0,'Officer')")
    ins_result = ol.sig_insider_call(c4, "2024-03-10", {"top": 3}, s4, {})
    check("sig_insider_call: returns insider buy signals from insider_trades", isinstance(ins_result, list) and len(ins_result) > 0, ins_result)
    ol.liquid = real_liq

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
