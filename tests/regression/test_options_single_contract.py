"""
Owner's options rule, 2026-10-05: "I am not doing open shorts. No. All options must be a single
contract cost." Only a long single-leg strategy (one call or one put bought) may ever trade; a spec
with a short leg or several legs stays research (backtest + paper record) and never takes a slot.

Guards the classification, whatever the config lists: a short spec is never tradeable.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import options_lab as ol
from universe import load_config

FAILED = []

LONG_SINGLE = {"opt_signal_call", "opt_iv_rise_call", "opt_smirk_put", "opt_ivspread_call", "opt_ivspread_put",
               "opt_signal_call_cheapiv", "opt_pead_call", "opt_breakout_call", "opt_oversold_call",
               "opt_insider_call"}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main() -> int:
    got = {n for n, p in ol.STRATEGIES.items() if ol.tradeable(p)}
    check("tradeable = exactly the long single-leg specs", got == LONG_SINGLE, sorted(got ^ LONG_SINGLE))
    check("a name works as well as a spec", ol.tradeable("opt_insider_call") and ol.tradeable("option:opt_insider_call"))
    check("an unknown name is not tradeable (fails closed)", not ol.tradeable("opt_nope") and not ol.tradeable("option:sw_x"))

    shorts = [n for n, p in ol.STRATEGIES.items() if p.get("short") or p.get("is_credit")]
    check("there are short specs to guard", len(shorts) >= 8, len(shorts))
    check("no short or credit spec is tradeable", not any(ol.tradeable(n) for n in shorts),
          [n for n in shorts if ol.tradeable(n)])
    spreads = [n for n, p in ol.STRATEGIES.items() if p.get("is_debit_spread")]
    check("no debit spread is tradeable (it holds a short leg)", spreads and not any(ol.tradeable(n) for n in spreads))
    multi = [n for n, p in ol.STRATEGIES.items() if p["legs"] not in ("C", "P")]
    check("no multi-leg spec is tradeable under the shipped config", not any(ol.tradeable(n) for n in multi),
          [n for n in multi if ol.tradeable(n)])

    wide = {"options": {"tradeable_legs": ["C", "P", "S", "CS", "IC", "BCS", "BPS", "PCS"]}}
    check("listing every leg shape in the config still never trades a short spec",
          not any(ol.tradeable(n, wide) for n in shorts), [n for n in shorts if ol.tradeable(n, wide)])
    check("...nor a debit spread", not any(ol.tradeable(n, wide) for n in spreads))
    check("only a long single-leg spec when the config lists only C",
          {n for n in ol.STRATEGIES if ol.tradeable(n, {"options": {"tradeable_legs": ["C"]}})}
          == {n for n in LONG_SINGLE if ol.STRATEGIES[n]["legs"] == "C"})

    cfg = load_config()
    s = ol.settings(cfg)
    check("the shipped config sets a per-contract cost cap", float(s["max_contract_cost_usd"]) > 0,
          s["max_contract_cost_usd"])
    check("the shipped config trades long calls and puts only", sorted(s["tradeable_legs"]) == ["C", "P"],
          s["tradeable_legs"])
    check("the default needs no config at all", ol.settings({})["max_contract_cost_usd"] == 100.0
          and tuple(ol.settings({})["tradeable_legs"]) == ("C", "P"))

    slots_section()
    engine_section()

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


def slots_section():
    import sqlite3
    import ranking
    import slots

    def row(name):
        return {"strategy_key": f"option:{name}", "version": 1, "passes_gate": True, "gate": "", "score": 0.05}

    names = ["opt_insider_call", "opt_short_put_uptrend", "opt_iv_cheap_straddle", "opt_bull_call_spread"]
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    real_rank, real_armed = ranking.rank, slots._options_armed
    ranking.rank = lambda conn, cfg: [row(n) for n in names]
    try:
        slots._options_armed = lambda: True
        out = {r["strategy_key"].split(":")[1]: r for r in slots.assess(c, {})}
        check("armed: a long single-leg option is eligible", out["opt_insider_call"]["eligible"],
              out["opt_insider_call"]["reasons"])
        for n in names[1:]:
            check(f"armed: {n} is still not eligible (research only)", not out[n]["eligible"]
                  and any("research only" in x for x in out[n]["reasons"]), out[n]["reasons"])
        slots._options_armed = lambda: False
        out = {r["strategy_key"].split(":")[1]: r for r in slots.assess(c, {})}
        check("not armed: the long call is blocked by the switch, not by the rule",
              not out["opt_insider_call"]["eligible"]
              and not any("research only" in x for x in out["opt_insider_call"]["reasons"]),
              out["opt_insider_call"]["reasons"])
    finally:
        ranking.rank, slots._options_armed = real_rank, real_armed


def engine_section():
    import json
    import sqlite3
    import league

    d0, d1, exp = "2024-01-08", "2024-01-22", "2024-02-09"
    dte = (21, 60, 35)
    call = {"rule": "stock_signal", "legs": "C", "dte": dte, "hold": 5, "per_day": 1}
    straddle = {**call, "legs": "S"}
    sig = {d0: [("AAA", "test signal")]}
    wide = {"options": {"max_contract_cost_usd": 300.0}}

    def quote(c, date, strike, cp, bid, ask, delta):
        c.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
                  "VALUES (?,?,?,?,?,?,?,0.3,?)", (date, "AAA", exp, strike, cp, bid, ask, delta))
        c.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','AAA',?,1,'t')", (date,))

    def book(exit_quote=False):
        c = sqlite3.connect(":memory:")
        ol.init(c)
        c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
        for k, dc in ((95.0, 0.7), (100.0, 0.52), (105.0, 0.3)):
            quote(c, d0, k, "C", 2.0, 2.2, dc)
            quote(c, d0, k, "P", 1.8, 2.0, dc - 1)
        if exit_quote:
            quote(c, d1, 100.0, "C", 3.0, 3.3, 0.6)
        return c

    def trade(c, name):
        return c.execute("SELECT cost, ret, usd FROM option_trades WHERE strategy=?", (name,)).fetchone()

    # --- delta: a single call or put can be bought off the money -----------------
    c, s = book(), ol.settings({})
    check("delta 0.3 call is the 105 strike", ol.pick(c, "AAA", d0, "C", dte, s, 0.3)[0]["strike"] == 105.0)
    check("delta 0.3 put is the 95 strike (put deltas are negative)",
          ol.pick(c, "AAA", d0, "P", dte, s, 0.3)[0]["strike"] == 95.0)
    check("no delta keeps the at-the-money pick", ol.pick(c, "AAA", d0, "C", dte, s)[0]["strike"] == 100.0)

    # --- one contract: ask x 100 must fit the cap ---------------------------------
    c = book()
    n = ol.run(c, {}, "t_cap", [d0], "BACKTEST", sig, spec=call)
    check("default cap: a $220 contract is not bought, and nothing cheaper is substituted",
          n == 0 and trade(c, "t_cap") is None, n)
    c = book()
    n = ol.run(c, {}, "t_straddle", [d0], "BACKTEST", sig, spec=straddle)
    t = trade(c, "t_straddle")
    check("a research long straddle is not capped (it can never trade)", n == 1 and t and abs(t[0] - 4.2) < 1e-9, (n, t))
    c = book()
    n = ol.run(c, wide, "t_wide", [d0], "BACKTEST", sig, spec=call)
    check("a larger cap in the config lets the $220 contract in", n == 1, n)

    # --- dollars: a contract in dollars, research as stake x return --------------
    check("a long call inside the cap is (value - cost) x 100 shares",
          abs(ol.trade_usd(call, 1.4, 0.9, s) - 50.0) < 1e-9)
    check("a research straddle stays stake x return",
          abs(ol.trade_usd(straddle, 1.8, 1.7, s) - 100 * (1.8 / 1.7 - 1)) < 1e-9)
    c = book(exit_quote=True)
    ol.run(c, wide, "t_in", [d0, d1], "BACKTEST", sig, spec=call)
    t = trade(c, "t_in")
    check("walk under the cap: dollars on one real contract", t and abs(t[2] - 80.0) < 1e-9, t)
    c = book(exit_quote=True)
    ol.run(c, wide, "t_pre", [d0], "BACKTEST", sig, spec=call)
    ol.run(c, {}, "t_pre", [d1], "BACKTEST", None, spec=call)
    t = trade(c, "t_pre")
    check("a trade opened before the cap existed is measured as stake x return, not as a contract",
          t and abs(t[2] - 100 * (3.0 / 2.2 - 1)) < 1e-9, t)

    # --- a re-run backtest archives what it replaces ---------------------------------
    real_signals = ol.stock_signals
    ol.STRATEGIES["t_bt"] = dict(call)
    try:
        runs = []
        ol.stock_signals = lambda conn, cfg, start, end, top=5: runs.append(1) or (sig if len(runs) == 1 else {})
        c = book(exit_quote=True)
        for d in (d0, d1):
            c.execute("INSERT INTO option_vol (date, symbol, iv_current) VALUES (?, 'AAA', 0.3)", (d,))
        ol.backtest(c, wide, ["t_bt"], "2024-01-01")
        first = c.execute("SELECT trades, mean_ret FROM option_backtests WHERE strategy='t_bt'").fetchone()
        none_yet = c.execute("SELECT COUNT(*) FROM option_backtests_history").fetchone()[0]
        ol.backtest(c, wide, ["t_bt"], "2024-01-01")
        kept = c.execute("SELECT trades, mean_ret FROM option_backtests_history WHERE strategy='t_bt'").fetchall()
        now = c.execute("SELECT trades FROM option_backtests WHERE strategy='t_bt'").fetchone()
        check("the first backtest has nothing to archive", first[0] == 1 and none_yet == 0, (first, none_yet))
        check("the second backtest archives the first and replaces it",
              len(kept) == 1 and kept[0][0] == 1 and abs(kept[0][1] - (3.0 / 2.2 - 1)) < 1e-9 and now[0] == 0,
              (kept, now))
    finally:
        ol.stock_signals = real_signals
        ol.STRATEGIES.pop("t_bt", None)

    # --- the league entry: delta registered only when set; the cap is not part of the definition ----
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ol.init(c)
    c.execute("INSERT INTO option_vol (date, symbol, iv_current) VALUES (?, 'AAA', 0.3)", (d0,))
    ol.STRATEGIES["opt_t_plain"] = dict(call)
    ol.STRATEGIES["opt_t_delta"] = {**call, "delta": 0.3}
    try:
        ol.open_funds(c, {})
        ol.open_funds(c, wide)
        plain = league.versions(c, "option:opt_t_plain")
        deltaed = league.versions(c, "option:opt_t_delta")
        check("a spec without delta registers the parameters it always did (hash unchanged)",
              json.loads(plain[0]["parameters"]) == {"dte": [21, 60, 35], "per_day": 1, "top": None},
              plain[0]["parameters"])
        check("a spec with delta registers it", json.loads(deltaed[0]["parameters"]).get("delta") == 0.3,
              deltaed[0]["parameters"])
        check("changing the cap mints no new league version", len(plain) == 1 and len(deltaed) == 1,
              (len(plain), len(deltaed)))
    finally:
        ol.STRATEGIES.pop("opt_t_plain", None)
        ol.STRATEGIES.pop("opt_t_delta", None)


if __name__ == "__main__":
    sys.exit(main())
