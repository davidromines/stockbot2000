"""
The Strategy Factory. Phase 13 §4-6, §21, §31; Addendum B §B16.

Every family is an economic hypothesis first and a rule second: it names why
it might work (§31), what data it needs, which league judges it (§16), and a
SMALL fixed parameter grid. Templates, not search — the frozen evolutionary
search stays frozen (B16), and a grid of at most a handful of points per
family is what keeps combinations from exploding (§4B).

**The freeze boundary.** Template generation is a separate governed path, not
an exemption from the freeze: `search.mode: FROZEN` governs evolve.py, and
lifting it stays a human edit to config.yaml. No factory output may enter the
evolutionary population — evolve.py, genome.py's seeding, seeds.py and
lab_loop.sh read nothing from strategy_meta, research_queue or this module.
If that ever changes, the freeze applies at that boundary.
tests/regression/test_freeze_boundary.py fails the gate if any of them
starts referencing the factory.

A family whose data does not exist point-in-time here is still generated as a
fully specified object, marked `data_available: False` with the reason. The
pipeline records DATA_PROBLEM for it instead of dropping it, so the gap stays
visible and the family is tested the day the data lands.

Genome grammar is genome.py's: comparisons (gt, lt, crosses_above/below),
logic (and, or, not), per-date `rank`, per-ticker `lag`/`delta`/`pct_change`/
`zscore` with `n`. Features are train_model.FEATURE_COLS; fundamental columns
are daily_fundamentals', already lagged to the first tradeable session.

    python strategy_factory.py --list
    python strategy_factory.py --generate [--family NAME] [--dry-run]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import itertools
import logging
import sqlite3

import storage
import strategy_objects as so
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("factory")

FUNDAMENTAL_COLS = ("piotroski_f", "book_to_market", "gross_profitability",
                    "chs_distress", "asset_growth", "accruals", "roa",
                    "earnings_yield", "net_share_issuance", "debt_to_equity",
                    "cash_to_assets", "altman_z")

# --- grammar helpers --------------------------------------------------------
def col(c):            return {"col": c}
def k(v):              return {"const": float(v)}
def gt(a, b):          return {"op": "gt", "args": [a, b]}
def lt(a, b):          return {"op": "lt", "args": [a, b]}
def and_(*xs):
    out = xs[0]
    for x in xs[1:]:
        out = {"op": "and", "args": [out, x]}
    return out
def rank(a):           return {"op": "rank", "args": [a]}
def pct(a, n):         return {"op": "pct_change", "args": [a], "n": int(n)}
def delta(a, n):       return {"op": "delta", "args": [a], "n": int(n)}
def z(a, n):           return {"op": "zscore", "args": [a], "n": int(n)}
def xabove(a, b):      return {"op": "crosses_above", "args": [a, b]}
NEVER = lt(col("close"), k(0))          # exit only by stop or holding period


def G(entry, exit_=None, stop=2.5, hold=20):
    return {"entry": entry, "exit": exit_ or NEVER,
            "risk": {"stop_atr_multiple": float(stop), "max_hold_days": int(hold)}}


# --- the families -----------------------------------------------------------
# Each: league, rationale, data, grid {param: [values]}, build(p) -> genome.
F = {}


def family(name, league, rationale, grid, build, data=("features",),
           available=True, missing=None, combo=False):
    F[name] = {"name": name, "league": league, "rationale": rationale,
               "grid": grid, "build": build, "data": list(data),
               "data_available": available, "missing": missing, "combo": combo}


# Classical — price
family("xs_momentum", "momentum",
       "Behavioural underreaction: winners keep winning over weeks as news diffuses.",
       {"q": [0.8, 0.9], "hold": [10, 20], "stop": [2.0, 3.0]},
       lambda p: G(and_(gt(rank(col("roc_10")), k(p["q"])), gt(col("price_above_sma200"), k(0.5))),
                   lt(col("price_above_sma50"), k(0.5)), p["stop"], p["hold"]))
family("ts_momentum", "momentum",
       "Time-series momentum: a rising long trend persists (Moskowitz, Ooi & Pedersen).",
       {"slope": [0.01, 0.02], "hold": [20, 40], "stop": [2.5, 4.0]},
       lambda p: G(gt(pct(col("sma_200"), 5), k(p["slope"])), lt(col("price_above_sma200"), k(0.5)),
                   p["stop"], p["hold"]))
family("trend_following", "momentum",
       "Trend persistence: price above both moving averages with a golden cross in force.",
       {"hold": [20, 40], "stop": [2.5, 3.5]},
       lambda p: G(and_(gt(col("price_above_sma50"), k(0.5)), gt(col("golden_cross"), k(0.5)),
                        gt(col("adx_14"), k(25))), lt(col("price_above_sma50"), k(0.5)),
                   p["stop"], p["hold"]))
family("breakout_52w", "momentum",
       "52-week-high anchoring: investors under-react near the high (George & Hwang 2004).",
       {"near": [0.97, 0.99], "hold": [10, 20], "stop": [2.0, 3.0]},
       lambda p: G(and_(gt(col("pct_of_52w_high"), k(p["near"])), gt(col("vol_ratio"), k(1.2))),
                   None, p["stop"], p["hold"]))
family("ma_cross", "tactical",
       "Moving-average crossover: a new trend becomes visible when the fast average crosses.",
       {"hold": [10, 20], "stop": [2.0, 3.0]},
       lambda p: G(xabove(col("sma_50"), col("sma_200")), None, p["stop"], p["hold"]))
family("rsi_reversion", "mean_reversion",
       "Temporary dislocation: oversold names inside an uptrend revert toward the mean.",
       {"rsi": [25, 30], "hold": [5, 10], "stop": [2.0, 3.0]},
       lambda p: G(and_(lt(col("rsi_14"), k(p["rsi"])), gt(col("price_above_sma200"), k(0.5))),
                   gt(col("rsi_14"), k(55)), p["stop"], p["hold"]))
family("bollinger_reversion", "mean_reversion",
       "Price below the lower band is a short-lived liquidity shock more often than news.",
       {"band": [0.0, 0.05], "hold": [5, 10], "stop": [2.0, 3.0]},
       lambda p: G(and_(lt(col("bb_pct"), k(p["band"])), gt(col("price_above_sma200"), k(0.5))),
                   gt(col("bb_pct"), k(0.5)), p["stop"], p["hold"]))
family("macd_cross", "tactical",
       "Momentum acceleration: MACD crossing its signal marks a turn in short-term trend.",
       {"hold": [5, 10, 20], "stop": [2.0, 3.0]},
       lambda p: G(and_(xabove(col("macd"), col("macd_signal")), gt(col("price_above_sma50"), k(0.5))),
                   lt(col("macd_hist"), k(0)), p["stop"], p["hold"]))
family("volatility_breakout", "tactical",
       "Information arrival: a volume surge with a positive move signals new information.",
       {"vr": [1.5, 2.0], "hold": [5, 10], "stop": [2.0, 3.0]},
       lambda p: G(and_(gt(col("vol_ratio"), k(p["vr"])), gt(col("roc_10"), k(0))), None,
                   p["stop"], p["hold"]))
family("volatility_contraction", "tactical",
       "Coiled spring: range compression before expansion, taken with the prevailing trend.",
       {"zc": [-1.0, -1.5], "hold": [10, 20], "stop": [2.0, 3.0]},
       lambda p: G(and_(lt(z(col("atr_14"), 20), k(p["zc"])), gt(col("price_above_sma50"), k(0.5))),
                   None, p["stop"], p["hold"]))
family("relative_strength", "momentum",
       "Relative strength: the strongest names by distance to their high keep leading.",
       {"q": [0.85, 0.95], "hold": [20, 40], "stop": [2.5, 3.5]},
       lambda p: G(gt(rank(col("pct_of_52w_high")), k(p["q"])), lt(col("price_above_sma50"), k(0.5)),
                   p["stop"], p["hold"]))
for nm, lg, why in (("low_volatility", "fundamental",
                     "Low-volatility anomaly: leverage constraints make safe stocks underpriced."),
                    ("high_volatility", "tactical",
                     "Lottery demand: high-volatility names are overpriced — tested as a control.")):
    family(nm, lg, why, {"q": [0.2]},
           lambda p: G(lt(rank(col("atr_14")), k(p["q"]))), data=("features", "realized_volatility"),
           available=False,
           missing="needs a scale-free realized volatility; atr_14 is in dollars and ranks price, "
                   "not risk. risk_metrics holds monthly idiosyncratic vol but is not on the panel.")

# Classical — fundamentals (point-in-time, daily_fundamentals)
FUNDS = ("features", "daily_fundamentals")
family("value_book", "fundamental",
       "Value: cheap on book value mean-reverts as mispricing corrects (Fama-French HML).",
       {"q": [0.8, 0.9], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(and_(gt(rank(col("book_to_market")), k(p["q"])), gt(col("altman_z"), k(1.8))),
                   lt(rank(col("book_to_market")), k(0.5)), p["stop"], p["hold"]), data=FUNDS)
family("earnings_yield", "fundamental",
       "Earnings yield: paying less per dollar of earnings is compensated (Basu).",
       {"q": [0.8, 0.9], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(gt(rank(col("earnings_yield")), k(p["q"])), lt(rank(col("earnings_yield")), k(0.5)),
                   p["stop"], p["hold"]), data=FUNDS)
family("profitability", "fundamental",
       "Profitability: high gross profits to assets predict returns (Novy-Marx 2013).",
       {"q": [0.8, 0.9], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(gt(rank(col("gross_profitability")), k(p["q"])),
                   lt(rank(col("gross_profitability")), k(0.5)), p["stop"], p["hold"]), data=FUNDS)
family("quality_piotroski", "fundamental",
       "Quality: financially improving firms outperform among cheap stocks (Piotroski 2000).",
       {"f": [7, 8], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(gt(col("piotroski_f"), k(p["f"] - 0.5)), lt(col("piotroski_f"), k(4.5)),
                   p["stop"], p["hold"]), data=FUNDS)
family("quality_roa", "fundamental",
       "Persistent profitability: high return on assets is sticky and under-priced.",
       {"q": [0.8, 0.9], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(gt(rank(col("roa")), k(p["q"])), lt(rank(col("roa")), k(0.5)), p["stop"], p["hold"]),
       data=FUNDS)
family("buyback", "fundamental",
       "Buybacks: net share reduction signals management believes shares are cheap (Ikenberry).",
       {"iss": [-0.01, -0.03], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(and_(lt(col("net_share_issuance"), k(p["iss"])), gt(col("altman_z"), k(1.8))),
                   gt(col("net_share_issuance"), k(0)), p["stop"], p["hold"]), data=FUNDS)
family("low_accruals", "fundamental",
       "Earnings quality: cash-backed earnings persist, accrual-heavy ones reverse (Sloan 1996).",
       {"q": [0.2, 0.1], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(lt(rank(col("accruals")), k(p["q"])), gt(rank(col("accruals")), k(0.5)),
                   p["stop"], p["hold"]), data=FUNDS)
family("low_investment", "fundamental",
       "Investment factor: firms growing assets slowly outperform aggressive investors (CMA).",
       {"q": [0.2, 0.1], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(lt(rank(col("asset_growth")), k(p["q"])), gt(rank(col("asset_growth")), k(0.5)),
                   p["stop"], p["hold"]), data=FUNDS)
family("balance_sheet", "fundamental",
       "Balance-sheet strength: low leverage and high cash cushion avoid distress losses.",
       {"q": [0.2, 0.3], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(and_(lt(rank(col("debt_to_equity")), k(p["q"])), gt(col("altman_z"), k(3.0))),
                   None, p["stop"], p["hold"]), data=FUNDS)
family("fundamental_momentum", "fundamental",
       "Changing business expectations: improving ROA leads price (fundamental momentum).",
       {"n": [63, 126], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(and_(gt(delta(col("roa"), p["n"]), k(0)),
                        gt(delta(col("gross_profitability"), p["n"]), k(0))),
                   lt(delta(col("roa"), p["n"]), k(0)), p["stop"], p["hold"]), data=FUNDS)
family("debt_reduction", "fundamental",
       "Deleveraging: falling debt-to-equity lowers distress risk before the market re-rates it.",
       {"n": [63, 126], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(and_(lt(delta(col("debt_to_equity"), p["n"]), k(-0.05)), gt(col("altman_z"), k(1.8))),
                   None, p["stop"], p["hold"]), data=FUNDS)
for nm, why, need in (
        ("fcf_yield", "Cash-flow yield: free cash flow is harder to manage than earnings.", "free cash flow"),
        ("roic", "Return on invested capital: durable ROIC signals a moat (Greenblatt).", "invested capital"),
        ("dividend", "Dividend yield and dividend initiation signal durable cash generation.", "dividends"),
        ("revenue_growth", "Revenue acceleration: changing business expectations lead price.", "revenue"),
        ("eps_growth", "Earnings acceleration: accelerating EPS growth is under-anticipated.", "EPS series"),
        ("earnings_revision", "Analyst revisions drift (Chan, Jegadeesh & Lakonishok).", "estimates")):
    family(nm, "fundamental", why, {"q": [0.8]},
           lambda p: G(gt(rank(col("earnings_yield")), k(p["q"]))),
           data=FUNDS + (need,), available=False,
           missing=f"{need} is not projected into daily_fundamentals (statements.py holds it per "
                   f"filing); the family is specified and waits for the daily projection")

# Combinations — predefined templates only (§4B)
family("value_momentum", "fundamental",
       "Value and momentum are negatively correlated; together they diversify (Asness et al.).",
       {"q": [0.7, 0.8], "hold": [20, 40], "stop": [3.0, 4.0]},
       lambda p: G(and_(gt(rank(col("book_to_market")), k(p["q"])), gt(rank(col("roc_10")), k(p["q"]))),
                   lt(col("price_above_sma50"), k(0.5)), p["stop"], p["hold"]), data=FUNDS, combo=True)
family("value_quality", "fundamental",
       "Cheap and good: value without the value-trap tail (Greenblatt, Novy-Marx).",
       {"q": [0.7, 0.8], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(and_(gt(rank(col("earnings_yield")), k(p["q"])),
                        gt(rank(col("gross_profitability")), k(p["q"]))), None, p["stop"], p["hold"]),
       data=FUNDS, combo=True)
family("quality_momentum", "momentum",
       "Momentum among profitable firms avoids junk rallies.",
       {"q": [0.7, 0.8], "hold": [20, 40], "stop": [2.5, 3.5]},
       lambda p: G(and_(gt(rank(col("roa")), k(p["q"])), gt(rank(col("roc_10")), k(p["q"])),
                        gt(col("price_above_sma200"), k(0.5))),
                   lt(col("price_above_sma50"), k(0.5)), p["stop"], p["hold"]), data=FUNDS, combo=True)
family("value_quality_momentum", "fundamental",
       "Three independent return sources combined; each filters the others' failure mode.",
       {"q": [0.6, 0.7], "hold": [20, 40], "stop": [3.0, 4.0]},
       lambda p: G(and_(gt(rank(col("earnings_yield")), k(p["q"])),
                        gt(rank(col("gross_profitability")), k(p["q"])),
                        gt(rank(col("roc_10")), k(p["q"]))), None, p["stop"], p["hold"]),
       data=FUNDS, combo=True)
family("momentum_volume", "momentum",
       "Momentum confirmed by participation: rising OBV separates real trends from drift.",
       {"q": [0.8, 0.9], "hold": [10, 20], "stop": [2.0, 3.0]},
       lambda p: G(and_(gt(rank(col("roc_10")), k(p["q"])), gt(col("obv_rising"), k(0.5))),
                   lt(col("price_above_sma50"), k(0.5)), p["stop"], p["hold"]), combo=True)
family("fundamental_price_momentum", "momentum",
       "Improving fundamentals plus rising price: expectations and trend agree.",
       {"n": [63], "q": [0.7, 0.8], "hold": [20, 40], "stop": [3.0]},
       lambda p: G(and_(gt(delta(col("roa"), p["n"]), k(0)), gt(rank(col("roc_10")), k(p["q"]))),
                   None, p["stop"], p["hold"]), data=FUNDS, combo=True)
family("growth_valuation", "fundamental",
       "Growth at a reasonable price: growing assets without paying up for them.",
       {"q": [0.6, 0.7], "hold": [40, 60], "stop": [3.0, 5.0]},
       lambda p: G(and_(gt(rank(col("asset_growth")), k(p["q"])), gt(rank(col("earnings_yield")), k(p["q"])),
                        gt(col("altman_z"), k(1.8))), None, p["stop"], p["hold"]),
       data=FUNDS, combo=True)
for nm, why, need in (("quality_low_volatility", "Profitable, stable firms: two defensive premia.", "realized_volatility"),
                      ("fcf_quality", "Free cash flow among quality firms.", "free cash flow"),
                      ("roic_valuation", "High ROIC bought cheaply (Magic Formula shape).", "invested capital")):
    family(nm, "fundamental", why, {"q": [0.8]},
           lambda p: G(gt(rank(col("roa")), k(p["q"]))), data=FUNDS + (need,), available=False,
           missing=f"{need} is not on the daily panel", combo=True)


# --- generation -------------------------------------------------------------
def grid_points(fam: dict, limit: int) -> list:
    keys = sorted(fam["grid"])
    pts = [dict(zip(keys, vals)) for vals in itertools.product(*(fam["grid"][x] for x in keys))]
    return pts[:limit]


def build_objects(fam_name: str, limit: int) -> list:
    fam = F[fam_name]
    out = []
    for p in grid_points(fam, limit):
        g = fam["build"](p)
        out.append({
            "strategy_key": so.key_for(fam_name, p), "family": fam_name,
            "name": f"{fam_name.replace('_', ' ').title()} " +
                    " ".join(f"{a}={b:g}" for a, b in sorted(p.items())),
            "league": fam["league"], "genome": g, "parameters": p,
            "hypothesis": fam["rationale"], "economic_rationale": fam["rationale"],
            "data_requirements": fam["data"], "universe": "tradeable common stock",
            "position_sizing": "one slot's capital per position (config)",
            "holding_period": g["risk"]["max_hold_days"],
            "source": "factory_template", "source_ref": fam_name,
            "features": sorted({n["col"] for n in _nodes(g["entry"]) if "col" in n}),
            "intraday": False,
            "data_available": fam["data_available"], "missing": fam["missing"]})
    return out


def _nodes(n):
    yield n
    for a in n.get("args", []):
        yield from _nodes(a)


def generate(conn, cfg, only: str | None = None, dry_run: bool = False) -> dict:
    fcfg = cfg.get("factory", {}) or {}
    per_family = int(fcfg.get("max_variants_per_family", 8))
    made = {"new": 0, "existing": 0, "data_problem": 0, "families": 0}
    for name in sorted(F):
        if only and name != only:
            continue
        made["families"] += 1
        for obj in build_objects(name, per_family):
            if dry_run:
                continue
            r = so.register(conn, obj)
            made["new" if r["new"] else "existing"] += 1
            if r["new"] and not obj["data_available"]:
                so.decide(conn, r["strategy_key"], r["version"], "DATA_PROBLEM",
                          obj["missing"], evidence={"data": obj["data_requirements"]})
                made["data_problem"] += 1
    return made


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--family")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    if a.list:
        for n, f in sorted(F.items()):
            pts = len(grid_points(f, 999))
            print(f"  {n:<28}{f['league']:<15}{pts:>3} pts  "
                  f"{'COMBO ' if f['combo'] else ''}{'' if f['data_available'] else 'DATA_PROBLEM'}")
        print(f"\n  {len(F)} families")
        return 0
    conn = storage.connect(cfg["database"]["market_data_path"])
    conn.row_factory = sqlite3.Row
    print(generate(conn, cfg, a.family, a.dry_run))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
