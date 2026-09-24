"""
Robustness. Phase 13 §28, §21 (Phase 6 regime analysis). Step H10.

The objective is not to manufacture confidence; it is to find strategies
whose results collapse under small changes. Each test returns a number and a
pass/fail against a stated rule, and the verdict counts failures:

    bootstrap        share of 1,000 trade resamples with positive net >= 60%
    trade order      95th-percentile drawdown over 1,000 shuffles (reported)
    cost stress      net stays positive with spread x2 and slippage x2
    slippage stress  net stays positive with slippage x3
    entry delay      net stays positive entering one session later
    exit delay       net stays positive holding one session longer
    parameters       >= half of +/-10% constant perturbations stay positive
    holding period   net stays positive at half and 1.5x the hold
    universe         >= half of random 80% ticker subsamples stay positive
    start / end      net stays positive with 6 months trimmed off either end
    regimes          net by bull/bear, high/low volatility, crisis (reported;
                     a regime with >= 20 trades and negative net is flagged)

Regimes are defined in advance from SPY, never chosen after results (§21):
bull = SPY above its 200-day average; high_vol = SPY 20-day realised
volatility above its median over the window; crisis = SPY more than 20%
below its 52-week high; high_rate = 3-month T-bill at or above
regimes.high_rate_pct (regimes.py). Without a rates series the rate regimes
are reported as unavailable, not guessed.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import copy
import random

import numpy as np
import pandas as pd

import costs as costs_mod
import genome as gn
import simulator

RULES = {"bootstrap_min_share": 0.6, "param_min_share": 0.5, "universe_min_share": 0.5,
         "regime_min_trades": 20, "max_failures": 1}


def _net(r: dict) -> float:
    return float(r.get("net_pnl_usd") or 0.0)


def _perturb(node, f: float):
    node = copy.deepcopy(node)

    def walk(n):
        if "const" in n and n["const"] not in (0, 0.0, 0.5):   # 0.5 marks boolean features
            n["const"] = float(n["const"]) * f
        for a in n.get("args", []):
            walk(a)
    walk(node)
    return node


def regime_labels(conn, start: str, end: str) -> pd.DataFrame:
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' AND date BETWEEN ? AND ? "
                            "ORDER BY date", conn, params=(str(pd.Timestamp(start) - pd.Timedelta(days=400))[:10], end))
    if spy.empty:
        return pd.DataFrame(columns=["date", "bull", "high_vol", "crisis"])
    spy["sma200"] = spy["close"].rolling(200, min_periods=150).mean()
    spy["vol20"] = spy["close"].pct_change().rolling(20).std()
    spy["hi52"] = spy["close"].rolling(252, min_periods=150).max()
    spy = spy[spy["date"] >= start].copy()
    spy["bull"] = spy["close"] > spy["sma200"]
    spy["high_vol"] = spy["vol20"] > spy["vol20"].median()
    spy["crisis"] = spy["close"] < 0.8 * spy["hi52"]
    return spy[["date", "bull", "high_vol", "crisis"]]


def analyse(conn, g: dict, panel, cm, size: float, max_entries: int, base: dict,
            cfg: dict, rng_seed: int = 20260924, window=None, rules: dict | None = None) -> dict:
    rules = {**RULES, **(rules or {})}
    rng = np.random.default_rng(rng_seed)
    pnl = np.asarray(base.get("pnl_series", []), dtype=float)
    out, fails = {}, []

    def sim(gg, cmx=None, pnl_panel=None):
        return simulator.simulate(gg, pnl_panel or panel, cmx or cm, size, max_entries=max_entries)

    def check(name, ok, **kw):
        out[name] = {"pass": bool(ok), **kw}
        if not ok:
            fails.append(name)

    if len(pnl) == 0:
        return {"verdict": "INSUFFICIENT_SAMPLE", "failures": ["no trades"], "tests": {}}

    boots = rng.choice(pnl, size=(1000, len(pnl)), replace=True).sum(axis=1)
    check("bootstrap", (boots > 0).mean() >= rules["bootstrap_min_share"],
          share_positive=round(float((boots > 0).mean()), 3))

    dds = []
    for _ in range(1000):
        eq = np.cumsum(rng.permutation(pnl))
        dds.append(float(np.max(np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq)))
    out["trade_order"] = {"pass": True, "dd_p95_usd": round(float(np.percentile(dds, 95)), 2),
                          "dd_median_usd": round(float(np.median(dds)), 2)}

    c2 = dict(cfg)
    base_costs = dict(cfg.get("costs", {}))
    c2["costs"] = {**base_costs, "spread_multiplier": float(base_costs.get("spread_multiplier", 1.0)) * 2,
                   "slippage_pct_per_side": float(base_costs.get("slippage_pct_per_side", 0.05)) * 2}
    r = sim(g, costs_mod.CostModel(c2))
    check("cost_stress", _net(r) > 0, net_usd=round(_net(r), 2))
    c3 = dict(cfg)
    c3["costs"] = {**base_costs, "slippage_pct_per_side": float(base_costs.get("slippage_pct_per_side", 0.05)) * 3}
    r = sim(g, costs_mod.CostModel(c3))
    check("slippage_stress", _net(r) > 0, net_usd=round(_net(r), 2))

    gd = copy.deepcopy(g)
    gd["entry"] = {"op": "lag", "args": [g["entry"]], "n": 1}
    r = sim(gd)
    check("entry_delay", _net(r) > 0, net_usd=round(_net(r), 2))
    ge = copy.deepcopy(g)
    ge["risk"]["max_hold_days"] = int(g["risk"]["max_hold_days"]) + 1
    r = sim(ge)
    check("exit_delay", _net(r) > 0, net_usd=round(_net(r), 2))

    nets = []
    for f in (0.9, 1.1):
        gp = copy.deepcopy(g)
        gp["entry"] = _perturb(g["entry"], f)
        nets.append(_net(sim(gp)))
        gs = copy.deepcopy(g)
        gs["risk"]["stop_atr_multiple"] = float(g["risk"]["stop_atr_multiple"]) * f
        nets.append(_net(sim(gs)))
    check("parameters", np.mean([n > 0 for n in nets]) >= rules["param_min_share"],
          nets=[round(n, 2) for n in nets])

    hn = []
    for f in (0.5, 1.5):
        gh = copy.deepcopy(g)
        gh["risk"]["max_hold_days"] = max(1, int(round(int(g["risk"]["max_hold_days"]) * f)))
        hn.append(_net(sim(gh)))
    check("holding_period", all(n > 0 for n in hn), nets=[round(n, 2) for n in hn])

    tick = panel.df["ticker"].astype(str).unique().tolist()
    un = []
    for s in (1, 2):
        keep = set(random.Random(rng_seed + s).sample(tick, int(len(tick) * 0.8)))
        mask = panel.df["ticker"].astype(str).isin(keep).to_numpy()
        # Re-scoring the same panel with the excluded tickers' signals masked
        # is equivalent to a smaller universe and costs no second panel.
        gu = copy.deepcopy(g)
        panel.df["_in_universe"] = mask.astype(float)
        gu["entry"] = {"op": "and", "args": [g["entry"], {"op": "gt", "args": [{"col": "_in_universe"}, {"const": 0.5}]}]}
        un.append(_net(sim(gu)))
    panel.df.drop(columns=["_in_universe"], inplace=True, errors="ignore")
    check("universe", np.mean([n > 0 for n in un]) >= rules["universe_min_share"],
          nets=[round(n, 2) for n in un])

    rows = np.asarray(base.get("entry_rows", []), dtype=int)
    dates = pd.to_datetime(panel.df["date"].to_numpy()[rows]) if len(rows) else pd.to_datetime([])
    if len(dates):
        lo, hi = dates.min(), dates.max()
        s_trim = pnl[dates >= lo + pd.DateOffset(months=6)].sum()
        e_trim = pnl[dates <= hi - pd.DateOffset(months=6)].sum()
        check("start_date", s_trim > 0, net_usd=round(float(s_trim), 2))
        check("end_date", e_trim > 0, net_usd=round(float(e_trim), 2))

        import regimes
        reg = regimes.labels(conn, str(lo.date()), str(hi.date()), cfg)
        if not reg.empty:
            lab = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "pnl": pnl})
            lab = lab.merge(reg, on="date", how="left")
            by = {}
            for col, (yes, no) in (("bull", ("bull", "bear")), ("high_vol", ("high_vol", "low_vol")),
                                   ("crisis", ("crisis", "normal")), ("high_rate", ("rates_high", "rates_low"))):
                if col not in lab or lab[col].isna().all():
                    by[yes] = by[no] = {"unavailable": "no rates series in this database (regimes.py --load-rates)"}
                    continue
                for flag, name in ((True, yes), (False, no)):
                    sub = lab[lab[col] == flag]["pnl"]
                    by[name] = {"trades": int(len(sub)), "net_usd": round(float(sub.sum()), 2)}
            bad = [k for k, v in by.items() if isinstance(v, dict) and v.get("trades", 0) >= rules["regime_min_trades"]
                   and v.get("net_usd", 0) < 0]
            out["regimes"] = {"pass": True, "by_regime": by, "negative_regimes": bad}

    verdict = "ROBUST" if len(fails) <= rules["max_failures"] else "FRAGILE"
    return {"verdict": verdict, "failures": fails, "tests": out, "rules": rules}
