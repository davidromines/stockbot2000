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

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
