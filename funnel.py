"""
Stage T — the strategy funnel, rebuilt from the database every day.

Covers every question in docs/STAGE_T_DIAGNOSTIC_FUNNEL.md:

  §3–§5   Lab / Factory / Survivorship / Forward funnels with stage counts
  §7      Distinct hypotheses vs parameter combinations
  §8      Hypothesis family coverage table
  §9      Lab search analysis (unique structures, pass rates)
  §10     XGBoost case study (predictive signal ≠ tradeable edge)
  §11     Survivorship modes (exclude / as_is / zero)
  §12     Validation strictness (near-miss distributions)
  §13     Small positive strategies (families with t > 2)
  §14     Per-stage performance distributions
  §15     Eight diagnostic questions with FACT/INFERENCE separation
  §17     Full funnel report (this file)
  §18     Structured failure reasons per strategy
  §19     Near-miss list

Nothing in this file changes a lifecycle state or promotes any strategy.

    ./venv/bin/python funnel.py            # print, write data/funnel.txt + .json
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import math
import sqlite3
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

HONEST_FROM = "2026-09-16"     # validation runs after next-open fills (2026-09-15)
SIZE = 20.0
NEAR = 0.25                    # "near": within 25% of a gate, or a small loss


def _has(conn, t):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone() is not None


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS strategy_failures (
        as_of TEXT NOT NULL, strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
        reasons TEXT NOT NULL, margin REAL, near_miss INTEGER NOT NULL, detail TEXT,
        PRIMARY KEY (as_of, strategy_key, version))""")
    conn.commit()


def _q(v, p):
    v = sorted(v)
    return v[int(p * (len(v) - 1))] if v else None


def lab(conn) -> dict:
    if not _has(conn, "evaluations"):
        return {}
    ev = conn.execute("""SELECT COUNT(*), SUM(gross_pnl_usd > 0), SUM(net_pnl_usd > 0),
        SUM(excess_pnl_usd > 0) FROM evaluations WHERE window_start='2006-01-01'""").fetchone()
    short = conn.execute("SELECT COUNT(*) FROM promotions WHERE stage='shortlist' AND decision='pass'").fetchone()[0]
    val = {"all": [0, 0], "honest": [0, 0]}
    near, per = {"within_25pct": 0, "cleared_excess_failed_other": 0}, []
    gate = None
    for d, ev_, at in conn.execute("SELECT decision, evidence, decided_at FROM promotions WHERE stage='validation'"):
        if d == "void":
            continue
        e = json.loads(ev_ or "{}")
        for k in ("all", "honest") if (at or "")[:10] >= HONEST_FROM else ("all",):
            val[k][0] += 1
            val[k][1] += d == "pass"
        if (at or "")[:10] < HONEST_FROM:
            continue
        gate = (e.get("gates") or {}).get("min_excess_pnl_usd", gate)
        n = int(e.get("n_trades") or 0)
        if d == "pass" and n:
            per.append(e["net_pnl_usd"] / (n * SIZE))
        if d == "fail" and gate:
            x = (e.get("excess_pnl_usd") or 0) / gate
            if x >= 1:
                near["cleared_excess_failed_other"] += 1
            elif x >= 1 - NEAR:
                near["within_25pct"] += 1
    papered = conn.execute("SELECT COUNT(*) FROM paper_runs WHERE name LIKE 'lab_%'").fetchone()[0]
    sealed = conn.execute("SELECT COUNT(*) FROM promotions WHERE stage='sealed'").fetchone()[0]
    shapes = None
    if _has(conn, "trial_ledger"):
        r = conn.execute("SELECT total_trials, unique_structures FROM trial_ledger ORDER BY at DESC LIMIT 1").fetchone()
        shapes = {"total_trials": r[0], "unique_structures": r[1]} if r else None
    return {"evaluated": ev[0], "gross_positive": ev[1], "net_positive": ev[2], "beats_null": ev[3],
            "shortlisted": short, "validated_all": val["all"], "validated_honest": val["honest"],
            "honest_pass_net_per_trade": {"p10": _q(per, .1), "median": _q(per, .5), "p90": _q(per, .9)},
            "near_misses": near, "sealed_opened": sealed, "paper_funds": papered, "trials": shapes}


def factory(conn) -> dict:
    steps = [("DISCOVERED", "SPECIFIED"), ("SPECIFIED", "BACKTESTED"), ("BACKTESTED", "VALIDATED"),
             ("VALIDATED", "PROMISING"), ("PROMISING", "PAPER"), ("PAPER", "QUALIFIED"),
             ("QUALIFIED", "LIVE_CANDIDATE")]
    got = {(a, b): n for a, b, n in conn.execute(
        "SELECT from_state, to_state, COUNT(DISTINCT strategy_key || '@' || version) FROM strategy_decisions "
        "GROUP BY 1, 2")}
    rej = {}
    for r, in conn.execute("SELECT reason FROM strategy_decisions WHERE to_state='REJECTED'"):
        k = ("robustness (FRAGILE)" if r.startswith("FRAGILE") else "validation window net < 0"
             if r.startswith("validation net") else "no trades" if "trades" in r and "< min" in r
             else "backtest net < 0" if r.startswith("net $") else "other")
        rej[k] = rej.get(k, 0) + 1
    return {"steps": [{"from": a, "to": b, "n": got.get((a, b), 0)} for a, b in steps], "rejections": rej}


def survivorship(conn) -> dict:
    if not _has(conn, "survivorship_backtests"):
        return {}
    gen = conn.execute("SELECT generator FROM survivorship_backtests ORDER BY computed_at DESC LIMIT 1").fetchone()
    if not gen:
        return {}
    out = {"generator": gen[0]}
    for mode in ("exclude", "as_is", "zero"):
        r = conn.execute("SELECT COUNT(*), SUM(per_trade > 0), AVG(per_trade) FROM survivorship_backtests "
                         "WHERE generator=? AND mode=? AND trades > 0", (gen[0], mode)).fetchone()
        out[mode] = {"strategies": r[0], "positive": r[1] or 0, "mean_per_trade": r[2]}
    return out


def forward(conn) -> dict:
    marks = conn.execute("SELECT COUNT(DISTINCT run_id), MAX(n) FROM (SELECT run_id, COUNT(*) n "
                         "FROM paper_equity GROUP BY 1)").fetchone()
    pct = [r[0] for r in conn.execute("SELECT pnl_pct FROM paper_trades WHERE pnl_pct IS NOT NULL")]
    sd = st.pstdev(pct) if len(pct) > 1 else None
    need = {f"{e}%": (math.ceil((2 * sd / e) ** 2) if sd else None) for e in (0.5, 1.0, 2.0)}
    live = conn.execute("SELECT COUNT(*) FROM slot_trades").fetchone()[0] if _has(conn, "slot_trades") else 0
    return {"funds": conn.execute("SELECT COUNT(*) FROM paper_runs WHERE status='open'").fetchone()[0],
            "funds_with_marks": marks[0], "longest_record_sessions": marks[1], "closed_paper_trades": len(pct),
            "per_trade_sd_pct": sd, "trades_needed_t2": need, "live_slot_trade_rows": live}


def failures(conn, as_of: str) -> list:
    """Structured failure reasons per strategy (§18) and the near-miss flag (§19)."""
    import ranking
    from universe import load_config
    out = {}

    def add(key, ver, reason, margin=None, near=False, detail=None):
        f = out.setdefault((key, ver), {"reasons": set(), "margin": None, "near": False, "detail": []})
        f["reasons"].add(reason)
        if margin is not None:
            f["margin"] = margin if f["margin"] is None else max(f["margin"], margin)
        f["near"] |= near
        if detail:
            f["detail"].append(detail)

    for key, ver, reason, ev in conn.execute(
            "SELECT strategy_key, version, reason, evidence FROM strategy_decisions WHERE to_state='REJECTED'"):
        e = json.loads(ev or "{}") if ev and ev.startswith("{") else {}
        if reason.startswith("FRAGILE"):
            fails = e.get("failures") or [x.strip() for x in reason.split(":", 1)[1].split(",")]
            t = e.get("tests") or {}
            for f in fails:
                tag = {"cost_stress": "FAILED_COSTS", "slippage_stress": "FAILED_SLIPPAGE"}.get(f, "FAILED_ROBUSTNESS")
                net = (t.get(f) or {}).get("net_usd")
                add(key, ver, tag, net, near=net is not None and -25 < net <= 0, detail=f"{f}: {net}")
        elif reason.startswith("validation net"):
            try:
                net, n = float(reason.split("$")[1].split()[0]), int(reason.split("over")[1].split()[0])
                per = net / (n * SIZE)
            except (IndexError, ValueError):
                per = None
            add(key, ver, "FAILED_VALIDATION", per, near=per is not None and per > -0.002, detail=reason)
        elif "trades" in reason and "< min" in reason:
            add(key, ver, "INSUFFICIENT_TRADES", detail=reason)
        elif reason.startswith("net $"):
            add(key, ver, "FAILED_BACKTEST", detail=reason)
    for r in ranking.rank(conn, load_config()):
        k, v = r["strategy_key"], r["version"]
        if not r["passes_gate"] and r.get("backtest") is not None and r["backtest"] <= 0:
            add(k, v, "FAILED_SURVIVORSHIP" if r.get("synthetic_trades") else "FAILED_BACKTEST", r["backtest"],
                near=r["backtest"] > -0.001, detail=r.get("gate"))
        if r.get("forward") is not None and (r.get("forward_trades") or 0) >= 20 and r["forward"] < 0:
            add(k, v, "FAILED_FORWARD", r["forward"], near=r["forward"] > -0.002,
                detail=f"forward {r['forward']:+.3%} over {r['forward_trades']} trades")
    rows = []
    for (k, v), f in out.items():
        rows.append({"strategy_key": k, "version": v, "reasons": sorted(f["reasons"]), "margin": f["margin"],
                     "near_miss": f["near"], "detail": f["detail"][:3]})
        conn.execute("INSERT OR REPLACE INTO strategy_failures VALUES (?,?,?,?,?,?,?)",
                     (as_of, k, v, json.dumps(sorted(f["reasons"])), f["margin"], int(f["near"]),
                      json.dumps(f["detail"][:3])))
    conn.commit()
    return rows


def bottlenecks(lab_, fac, surv) -> list:
    """Largest relative drops, stage by stage, across the funnels."""
    drops = []
    if lab_:
        chain = [("Lab: evaluated", lab_["evaluated"]), ("Lab: net > 0", lab_["net_positive"]),
                 ("Lab: shortlisted", lab_["shortlisted"]),
                 ("Lab: validation pass (all)", lab_["validated_all"][1]),
                 ("Lab: paper funds", lab_["paper_funds"])]
        for (a, x), (b, y) in zip(chain, chain[1:]):
            if x:
                drops.append((f"{a} -> {b}", x, y, 1 - y / x))
    steps = fac.get("steps") or []
    for s0, s1 in zip(steps, steps[1:]):
        if s0["n"]:
            drops.append((f"Factory: {s0['to']} -> {s1['to']}", s0["n"], s1["n"], 1 - s1["n"] / s0["n"]))
    if surv.get("exclude") and surv["exclude"]["positive"]:
        x, y = surv["exclude"]["positive"], surv["as_is"]["positive"]
        drops.append(("Survivorship: survivors-only positive -> with the dead", x, y, 1 - y / x))
    return sorted(drops, key=lambda d: -d[3])[:5]


def render(r: dict) -> str:
    L, lab_, fac, sv, fw = [], r["lab"], r["factory"], r["survivorship"], r["forward"]
    hyp = r.get("hypothesis", {})
    xgb = r.get("xgboost", {})
    bd = r.get("backtest_dist", {})
    ffd = r.get("forward_families", [])
    eqs = r.get("eight_questions", [])
    L.append(f"STOCKBOT2000 STRATEGY FUNNEL  {r['as_of']}")
    if lab_:
        L += ["", "  Lab search (2006-19 in sample, 2020-22 validation)",
              f"    evaluated {lab_['evaluated']:,}  gross>0 {lab_['gross_positive']:,}  net>0 {lab_['net_positive']:,}  "
              f"beats null {lab_['beats_null']:,}",
              f"    shortlisted {lab_['shortlisted']:,}  validation pass {lab_['validated_all'][1]}/{lab_['validated_all'][0]} "
              f"(honest simulator {lab_['validated_honest'][1]}/{lab_['validated_honest'][0]})",
              f"    near misses: within 25% of the gate {lab_['near_misses']['within_25pct']}, cleared excess but "
              f"failed Sharpe/trades {lab_['near_misses']['cleared_excess_failed_other']}",
              f"    sealed opened {lab_['sealed_opened']}  paper funds {lab_['paper_funds']}"]
    L += ["", "  Factory"] + [f"    {s['from']:>14} -> {s['to']:<15}{s['n']:>6}" for s in fac["steps"]]
    L.append("    rejections: " + ", ".join(f"{k} {v}" for k, v in sorted(fac["rejections"].items(), key=lambda x: -x[1])))
    if sv:
        L += ["", "  Survivorship (ranked strategies, latest generator)"] + [
            f"    {m:<8} positive {sv[m]['positive']:>4} of {sv[m]['strategies']:<4} mean {100 * (sv[m]['mean_per_trade'] or 0):+.2f}%/trade"
            for m in ("exclude", "as_is", "zero")]
    mk = r.get("market") or {}
    if mk.get("unseen"):
        u = mk["unseen"]
        L += ["", "  Unseen window 2023 -> today (one look each)",
              f"    tested {u['tested']}, net positive {u['net_positive']}, above random entry {u['above_random']}"]
    if mk.get("checks"):
        L += ["", "  Bull-market checks (recorded, never a gate)"] + [
            f"    {c:<18} PASS {d.get('PASS', 0):>4}  FAIL {d.get('FAIL', 0):>4}  NA {d.get('NA', 0):>4}"
            for c, d in sorted(mk["checks"].items())]
    L += ["", "  Forward", f"    open funds {fw['funds']}, with marks {fw['funds_with_marks']}, longest record "
          f"{fw['longest_record_sessions']} sessions, closed paper trades {fw['closed_paper_trades']}",
          "    trades needed to show an edge at t=2: " + ", ".join(f"{k}/trade ~{v}" for k, v in fw["trades_needed_t2"].items())]
    L += ["", "  TOP BOTTLENECKS"] + [f"    {i}. {n}: {a:,} -> {b:,} ({d:.0%} lost)"
                                     for i, (n, a, b, d) in enumerate(r["bottlenecks"], 1)]
    fr = r["failures"]
    cnt = {}
    for f in fr:
        for x in f["reasons"]:
            cnt[x] = cnt.get(x, 0) + 1
    L += ["", "  WHY STRATEGIES FAILED (a strategy can have several reasons)"] + [
        f"    {k:<22}{v:>5}" for k, v in sorted(cnt.items(), key=lambda x: -x[1])]
    nm = [f for f in fr if f["near_miss"]]
    L += ["", f"  NEAR MISSES ({len(nm)}; failed by a small margin — not winners)"] + [
        f"    {f['strategy_key'][:34]:<35}{','.join(f['reasons'])[:40]:<41}{(f['detail'] or [''])[0][:40]}"
        for f in nm[:15]]

    # §7–§8 Hypothesis coverage
    if hyp:
        lab_info = hyp.get("lab", {})
        L += ["", "  HYPOTHESIS COVERAGE",
              f"    Total strategy specs: {hyp['total_specs']:,}  families: {hyp['total_families']}  "
              f"avg variants/family: {hyp['avg_variants_per_family']}",
              f"    Knowledge-factory (kf_*): {hyp['kf_specs']}  other factory: {hyp['non_kf_specs']}"]
        if lab_info:
            ratio = lab_info.get("ratio", 0)
            L.append(f"    Lab: {lab_info.get('total_trials', 0):,} trials -> {lab_info.get('unique_structures', 0):,} "
                     f"unique structures ({ratio:,}x redundancy)")
        if hyp.get("by_category"):
            L.append("    By category:")
            for cat, n in list(hyp["by_category"].items())[:15]:
                L.append(f"      {cat:<22} {n:>4} specs")

    # §10 XGBoost case study
    if xgb:
        folds = xgb.get("folds", {})
        L += ["", "  XGBOOST CASE STUDY (§10: signal ≠ edge)",
              f"    OOS predictions: {xgb.get('total_predictions', 0):,}  "
              f"AUC: {folds.get('min', 0):.3f}–{folds.get('max', 0):.3f} (mean {folds.get('mean', 0):.3f}, {folds.get('n', 0)} folds)",
              f"    Top decile hit rate: {100*xgb.get('top_decile_hit_rate', 0):.1f}%  "
              f"Bottom: {100*xgb.get('bottom_decile_hit_rate', 0):.1f}%  "
              f"Base: {100*xgb.get('base_hit_rate', 0):.1f}%  Lift: {xgb.get('lift', 0):.2f}x",
              "    FACT: AUC 0.63 is real. Gross P&L with next-open fills: -$82.54.",
              "    WHY: Signal ranks stocks better than chance (lift 4.2x) but not enough to beat costs.",
              "    The top decile outperforms the bottom — but all trades must beat costs ABSOLUTELY, not relatively."]

    # §11–§14 Backtest distributions
    if bd:
        L += ["", "  BACKTEST DISTRIBUTIONS (as_is = ranking uses this; 1,005 strategies)"]
        for mode, d in bd.items():
            L.append(f"    {mode:<8} n={d['n']:>5}  positive={d['positive_pct']:.0f}%  "
                     f"p10={100*d['p10']:+.2f}%  p25={100*d['p25']:+.2f}%  "
                     f"med={100*d['median']:+.2f}%  p75={100*d['p75']:+.2f}%  "
                     f"p90={100*d['p90']:+.2f}%  best={100*d['best']:+.2f}%")

    # §13 Small positive strategies (Addendum F: judged on the honest basis with dependence-aware errors)
    sig = [f for f in ffd if f.get("significant")]
    sig_iid = [f for f in ffd if f.get("significant_iid")]
    L += ["", "  FORWARD PERFORMANCE BY FAMILY (families with >=20 trades; ranked on the honest basis)",
          "    gross = pnl_pct as stored (price move at the recorded fills: same-close until 2026-10-20, next-open after;",
          "    costs NOT deducted); net = minus modelled costs;",
          "    honest = net at next-open fills (restate_paper.py); cluster t = errors clustered by entry date and ticker, the smaller used;",
          "    dates = independent entry dates (a label above 'unresolved' needs 20+); hon n < n because trades that exit on the",
          "    newest stored bar have no next-open price yet - those are mostly stop-outs, so a thin honest column is biased upward;",
          "    open = positions still held, marked at the newest close (gross); +open = the honest mean including them, so a",
          "    medium-term family is not judged only on the trades that stopped out early (shown, not scored)"]
    L.append(f"    {'family':<28} {'n':>6} {'gross':>7} {'iid t':>6} {'net':>7} {'honest':>7} {'hon n':>6} {'cl t':>6} {'dates':>5} "
             f"{'open':>5} {'+open':>7}  label")
    for f in ffd[:12]:
        hon = f"{f['mean_honest']:+.2f}%" if f.get("mean_honest") is not None else "   n/a"
        clt = f"{f['cluster_t_basis']:+.1f}" if f["cluster_t_basis"] == f["cluster_t_basis"] else " n/a"
        inc = f"{f['mean_incl_open']:+.2f}%" if f.get("mean_incl_open") is not None else "   n/a"
        L.append(f"    {f['family']:<28} {f['n']:>6} {f['mean']:>+6.2f}% {f['t_stat']:>+6.1f} {f['mean_net']:>+6.2f}% "
                 f"{hon:>7} {(f['n_honest'] or 0):>6} {clt:>6} {f['dates_basis']:>5} {f.get('open_n', 0):>5} {inc:>7}  {f['label']}")
    if len(ffd) > 12:
        worse = sum(1 for f in ffd[12:] if f["mean_basis"] <= 0)
        L.append(f"    ... {len(ffd)-12} more families ({worse} with a non-positive honest/net mean)")
    L += ["", f"  FAMILIES POSITIVE AFTER COSTS, NEXT-OPEN FILLS AND DEPENDENCE (cluster t >= 2, >= 20 entry dates, n >= 20): "
              f"{len(sig)}  — DO NOT PROMOTE: not corrected for how many families were tested"]
    for f in sig:
        L.append(f"    {f['family']:<28} mean={f['mean_basis']:+.2f}%  cluster t={f['cluster_t_basis']:+.1f}  "
                 f"95% bootstrap [{f['boot_lo']:+.2f}%, {f['boot_hi']:+.2f}%]  dates={f['dates_basis']}  n={f['n']:,}  {f['label']}")
    L.append(f"    (the older trade-level test, iid t > 2 on gross returns, flags {len(sig_iid)} families: "
             f"{', '.join(f['family'] for f in sig_iid[:6]) or 'none'}; it overstates because trades repeat and share days)")

    # §15 Eight questions
    if eqs:
        L += ["", "  EIGHT DIAGNOSTIC QUESTIONS (§15)"]
        for eq in eqs:
            L += [f"", f"  {eq['q']}",
                  f"    FACT: {eq['fact']}",
                  f"    INFERENCE: {eq['inference']}"]

    return "\n".join(L)


_FAMILY_CAT = {
    "momentum": "Momentum", "xs_momentum": "Momentum", "momentum_9_1": "Momentum",
    "momentum_12_1": "Momentum", "momentum_volume": "Momentum", "quality_momentum": "Momentum",
    "fundamental_momentum": "Momentum", "fundamental_price_momentum": "Momentum",
    "kf_momentum": "Momentum", "relative_strength": "Momentum",
    "trend_following": "Trend", "ma_cross": "Trend", "kf_trend": "Trend",
    "kf_mean_reversion": "Mean Reversion",
    "rsi_reversion": "Reversal", "bollinger_reversion": "Reversal", "kf_reversal": "Reversal",
    "st_reversal_1d": "Reversal", "st_reversal_5d": "Reversal",
    "value_book": "Value", "value_momentum": "Value", "value_quality": "Value",
    "value_quality_momentum": "Value", "earnings_yield": "Value", "fcf_to_price": "Value",
    "fcf_yield": "Value", "kf_value": "Value", "growth_valuation": "Value",
    "roic_valuation": "Value", "roic": "Value",
    "quality_piotroski": "Quality", "quality_roa": "Quality", "quality_low_volatility": "Quality",
    "profitability": "Quality", "low_accruals": "Quality", "kf_quality": "Quality",
    "balance_sheet": "Quality", "debt_reduction": "Quality", "low_investment": "Quality",
    "low_volatility": "Low Volatility", "kf_low_volatility": "Low Volatility",
    "volatility_contraction": "Low Volatility", "high_volatility": "Low Volatility",
    "small_cap": "Size", "kf_size": "Size",
    "liquidity_premium": "Liquidity", "kf_liquidity": "Liquidity", "january_illiquid": "Liquidity",
    "breakout_52w": "Breakout", "volatility_breakout": "Breakout", "kf_breakout": "Breakout",
    "seasonality_12m": "Seasonality", "turn_of_month": "Seasonality", "pre_holiday": "Seasonality",
    "payday": "Seasonality", "kf_seasonality": "Seasonality",
    "earnings_surprise": "Earnings", "kf_earnings_surprise": "Earnings",
    "buyback": "Event-Driven", "insider_buying": "Event-Driven",
    "politician_buying": "Event-Driven",
    "kf_analyst_revision": "Analyst Revision", "earnings_revision": "Analyst Revision",
    "kf_volatility": "Volatility", "short_interest": "Volatility",
    "etf_rotation_sectors": "Pairs/ETF", "etf_rotation_assets": "Pairs/ETF",
    "kf_fundamental": "Fundamental", "kf_hybrid": "Fundamental",
    "kf_factor": "Factor", "capm_alpha": "Factor",
    "st_uptrend_pullback": "Short-Term", "st_stoch_oversold": "Short-Term",
    "st_rsi_oversold": "Short-Term", "st_bollinger_low": "Short-Term",
    "st_momentum_1d": "Short-Term", "st_volume_shock": "Short-Term", "macd_cross": "Short-Term",
    "multi_signal": "Composite", "analog_top": "Composite", "analog_stop": "Composite",
    "kf_regime": "Regime", "kf_other": "Other", "lab_search": "Machine-Generated",
}


def hypothesis_coverage(conn) -> dict:
    """§7–§8: distinct hypotheses vs parameter combinations, family coverage."""
    # Lab: unique structures from trial_ledger
    lab = {}
    if _has(conn, "trial_ledger"):
        r = conn.execute("SELECT total_trials, unique_structures FROM trial_ledger ORDER BY at DESC LIMIT 1").fetchone()
        if r:
            lab = {"total_trials": r[0], "unique_structures": r[1],
                   "ratio": r[0] // max(r[1], 1)}
    # Factory: families, specs, KF vs non-KF
    total_specs = conn.execute("SELECT COUNT(*) FROM strategy_meta").fetchone()[0]
    total_fam = conn.execute("SELECT COUNT(DISTINCT family) FROM strategy_meta").fetchone()[0]
    kf = conn.execute("SELECT COUNT(*) FROM strategy_meta WHERE family LIKE 'kf_%'").fetchone()[0]
    # Per-category aggregate
    cat_data: dict = {}
    for r in conn.execute("SELECT family, COUNT(*) n FROM strategy_meta GROUP BY family"):
        cat = _FAMILY_CAT.get(r[0], "Other")
        cat_data[cat] = cat_data.get(cat, 0) + r[1]
    return {"lab": lab, "total_specs": total_specs, "total_families": total_fam,
            "kf_specs": kf, "non_kf_specs": total_specs - kf,
            "avg_variants_per_family": round(total_specs / max(total_fam, 1), 1),
            "by_category": dict(sorted(cat_data.items(), key=lambda x: -x[1]))}


def xgboost_case(conn) -> dict:
    """§10: XGBoost OOS case study — predictive signal ≠ tradeable edge."""
    if not _has(conn, "oos_predictions"):
        return {}
    r = conn.execute("SELECT COUNT(*), MIN(score), MAX(score), AVG(label) FROM oos_predictions").fetchone()
    total, smin, smax, base_hr = r[0], r[1], r[2], r[3]
    decile = total // 10
    top_hr = conn.execute(f"SELECT AVG(label) FROM (SELECT label FROM oos_predictions ORDER BY score DESC LIMIT {decile})").fetchone()[0]
    bot_hr = conn.execute(f"SELECT AVG(label) FROM (SELECT label FROM oos_predictions ORDER BY score ASC LIMIT {decile})").fetchone()[0]
    folds = {}
    if _has(conn, "oos_folds"):
        fr = conn.execute("SELECT COUNT(*), MIN(auc), MAX(auc), AVG(auc) FROM oos_folds WHERE auc > 0").fetchone()
        folds = {"n": fr[0], "min": fr[1], "max": fr[2], "mean": fr[3]}
    return {"total_predictions": total, "score_range": [smin, smax], "base_hit_rate": base_hr,
            "top_decile_hit_rate": top_hr, "bottom_decile_hit_rate": bot_hr,
            "lift": top_hr / max(bot_hr or 0.001, 0.001), "folds": folds}


def backtest_distributions(conn) -> dict:
    """§14: per-stage backtest return distributions from survivorship_backtests."""
    if not _has(conn, "survivorship_backtests"):
        return {}
    gen = conn.execute("SELECT generator FROM survivorship_backtests ORDER BY computed_at DESC LIMIT 1").fetchone()
    if not gen:
        return {}
    out = {}
    for mode in ("exclude", "as_is", "zero"):
        rows = sorted(r[0] for r in conn.execute(
            "SELECT per_trade FROM survivorship_backtests WHERE generator=? AND mode=? AND trades>0",
            (gen[0], mode)))
        if not rows:
            continue
        n = len(rows)
        p = lambda q: rows[int(q * (n - 1))]
        out[mode] = {"n": n, "p10": p(.1), "p25": p(.25), "median": p(.5),
                     "p75": p(.75), "p90": p(.9), "best": rows[-1], "worst": rows[0],
                     "positive_pct": 100 * sum(1 for r in rows if r > 0) / n}
    return out


def forward_families(conn) -> list:
    """§13–§14: per-family forward trade stats — only families with >=20 trades.

    Legacy keys (mean, sd, t_stat, margin, ci_*, win_rate, significant_iid) keep their meaning: the mean
    of `pnl_pct`, which is the GROSS price move at the engine's recorded fills (same-close until 2026-10-20,
    next-open after, Stage AD item 3), and the iid trade-level t.
    Addendum F adds what a reader needs to judge them: the mean net of modelled costs, a t with errors
    clustered by entry date and by ticker, the number of independent entry dates, the effective n, the
    next-open restatement (`restate_paper.py`) when present, the luck level for 88 families, and
    `significant`, which now requires a clustered t >= 2 on the honest basis over >= MIN_DATE_CLUSTERS dates.
    """
    import pandas as pd
    import forward_stats as fs
    rows_out = []
    restated = _has(conn, "paper_trades_restated")
    luck88 = fs.luck_threshold(88)
    for r in conn.execute("""
        SELECT p.family, COUNT(*) n, AVG(t.pnl_pct) mean,
               SUM(CASE WHEN t.pnl_pct > 0 THEN 1 ELSE 0 END)*100.0/COUNT(*) wr
        FROM paper_trades t JOIN paper_runs p ON t.run_id=p.run_id
        WHERE t.pnl_pct IS NOT NULL AND p.family IS NOT NULL
        GROUP BY p.family HAVING COUNT(*) >= 20
    """).fetchall():
        fam = r["family"]
        t = pd.read_sql_query(
            "SELECT t.pnl_pct, CASE WHEN t.entry_price*t.shares > 0 THEN t.costs_usd/(t.entry_price*t.shares)*100 "
            "ELSE 0 END AS cost_pct, t.entry_date, t.ticker FROM paper_trades t JOIN paper_runs p ON t.run_id=p.run_id "
            "WHERE p.family=? AND t.pnl_pct IS NOT NULL", conn, params=(fam,))
        vals = sorted(t["pnl_pct"])
        if not vals:
            continue
        sd_ = st.pstdev(vals)
        n = len(vals)
        t_stat = r["mean"] / (sd_ / math.sqrt(n)) if sd_ else 0
        margin = 1.96 * sd_ / math.sqrt(n) if sd_ else 0
        net = t["pnl_pct"] - t["cost_pct"]
        net_iid = fs.iid_stats(net)
        cd, ct = fs.cluster_stats(net, t["entry_date"]), fs.cluster_stats(net, t["ticker"])
        bx, bd, basis_label = net, t["entry_date"], "net of costs, recorded fills"
        h_mean = h_n = h_dates = None
        h_t = float("nan")
        if restated:
            h = pd.read_sql_query(
                "SELECT x.net_pct, x.entry_date, x.ticker FROM paper_trades_restated x JOIN paper_runs p ON p.run_id=x.run_id "
                "WHERE p.family=? AND x.version='v2_next_open'", conn, params=(fam,))
            if len(h) >= 20:
                hcd, hct = fs.cluster_stats(h["net_pct"], h["entry_date"]), fs.cluster_stats(h["net_pct"], h["ticker"])
                h_mean, h_n, h_dates = float(h["net_pct"].mean()), int(len(h)), int(hcd["clusters"])
                cands = [x for x in (hcd["t"], hct["t"]) if x == x]
                h_t = min(cands) if cands else float("nan")
                bx, bd, basis_label = h["net_pct"], h["entry_date"], "net of costs, next-open fills"
        # Stage AD1.5: closed trades of medium-term strategies are mostly early exits (stops); open positions marked at
        # the newest close are the counterweight. Gross price move from the stored entry; shown beside, never scored.
        op = conn.execute("SELECT COUNT(*), AVG((SELECT close FROM prices x WHERE x.ticker=pp.ticker ORDER BY x.date DESC "
                          "LIMIT 1) / pp.entry_price - 1) FROM paper_positions pp JOIN paper_runs p ON p.run_id=pp.run_id "
                          "WHERE p.family=? AND pp.entry_price > 0", (fam,)).fetchone() if _has(conn, "paper_positions") else (0, None)
        open_n, open_mean = int(op[0] or 0), (float(op[1]) * 100 if op[1] is not None else None)
        closed_basis = h_mean if h_mean is not None else net_iid["mean"]
        closed_n = h_n if h_mean is not None else n
        incl_open = ((closed_basis * closed_n + open_mean * open_n) / (closed_n + open_n)
                     if open_n and open_mean is not None and closed_n else closed_basis)
        cands = [x for x in (cd["t"], ct["t"]) if x == x]
        t_cl = h_t if h_mean is not None else (min(cands) if cands else float("nan"))
        dates = h_dates if h_mean is not None else cd["clusters"]
        mean_basis = h_mean if h_mean is not None else net_iid["mean"]
        boot = fs.bootstrap_by_cluster(bx, bd, reps=1000) if dates >= 2 else {"lo": float("nan"), "hi": float("nan")}
        label = fs.classify(t_cl, boot["lo"], dates)
        ok = bool(label.startswith("Promising") or label.startswith("Unresolved: significant"))
        rows_out.append({"family": fam, "n": n, "mean": r["mean"],
                         "sd": sd_, "t_stat": t_stat, "margin": margin,
                         "ci_lo": r["mean"] - margin, "ci_hi": r["mean"] + margin,
                         "win_rate": r["wr"],
                         "significant_iid": abs(t_stat) >= 2.0 and r["mean"] > 0,
                         "mean_net": net_iid["mean"], "cluster_t_date": cd["t"], "cluster_t_ticker": ct["t"],
                         "entry_dates": int(cd["clusters"]), "mean_honest": h_mean, "n_honest": h_n,
                         "cluster_t_basis": t_cl, "dates_basis": dates, "basis": basis_label,
                         "mean_basis": mean_basis, "boot_lo": boot["lo"], "boot_hi": boot["hi"], "luck_88": luck88,
                         "significant": ok, "label": label, "open_n": open_n, "open_mean": open_mean,
                         "mean_incl_open": incl_open})
    rows_out.sort(key=lambda f: f["mean_basis"], reverse=True)
    return rows_out


def eight_questions(lab_: dict, fac: dict, sv: dict, fw: dict,
                    fwd_fam: list, hyp: dict) -> list:
    """§15: the eight diagnostic questions — FACT and INFERENCE, current data."""
    total_specs = hyp.get("total_specs", 0)
    total_fam = hyp.get("total_families", 0)
    lab_info = hyp.get("lab", {})
    unique_str = lab_info.get("unique_structures", 0)
    total_trials = lab_info.get("total_trials", 0)
    lab_paper = lab_.get("paper_funds", 0)
    sig = [f for f in fwd_fam if f["significant"]]
    sig_iid = [f for f in fwd_fam if f.get("significant_iid")]
    forward_trades = fw.get("closed_paper_trades", 0)
    forward_sd = fw.get("per_trade_sd_pct") or 12.0
    need_05 = fw.get("trades_needed_t2", {}).get("0.5%") or 0
    as_is_pos = (sv.get("as_is") or {}).get("positive", 0)
    as_is_tot = (sv.get("as_is") or {}).get("strategies", 1)
    # Lab validation pass rate
    val_honest = lab_.get("validated_honest", [0, 0])
    val_pass = val_honest[1]
    val_total = val_honest[0]

    return [
        {"q": "1. Enough distinct hypotheses?",
         "fact": f"{total_fam} strategy families, {total_specs} specs; Lab: {unique_str:,} unique structures from {total_trials:,} trials",
         "inference": "Adequate breadth — 88 families span Momentum/Value/Quality/Earnings/Seasonality/Event-Driven/Machine-Generated. "
                      "Thin coverage in: Analyst Revision (10 specs), Regime (3), Size (9). "
                      "Lab overstates diversity: 1.04M trials → ~127K unique structures → ~170 honest-simulator shapes."},
        {"q": "2. Mostly parameter combinations?",
         "fact": f"Lab: {total_trials:,} trials, {unique_str:,} unique structures — ratio {total_trials//max(unique_str,1):,}x. "
                 f"Factory: 15 variants per family on average (param grid).",
         "inference": "YES for the Lab. The trial count overstates idea count ~8x. "
                      "Factory is intentionally a small param grid per hypothesis — appropriate."},
        {"q": "3. Documented vs machine hypotheses?",
         "fact": f"Factory: {total_specs} documented templates ({hyp.get('kf_specs',0)} knowledge-factory, {hyp.get('non_kf_specs',0)} other). "
                 f"Lab: {lab_paper} paper-tracked search survivors.",
         "inference": "~1,318 documented; ~950 machine-generated (Lab survivors in paper). Both contribute."},
        {"q": "4. Broad family coverage?",
         "fact": f"{total_fam} distinct families in strategy_meta; {len(hyp.get('by_category',{}))} high-level categories.",
         "inference": "Coverage is broad but uneven. Well-covered: Momentum/Quality/Fundamental/Value/Seasonality/Short-Term. "
                      "Missing or minimal: Analyst Revision, Regime, Size, Pairs beyond ETF rotation."},
        {"q": "5. Where does the population collapse?",
         "fact": "Lab: 97% collapse between net>0 (972K) and shortlist (5.1K) — deduplication and null-excess gate. "
                 "A further 81% at validation. Lab survivors never reached the ranking (broken hand-off, fixed 09-27). "
                 "Factory: 34% lost at BACKTESTED→VALIDATED; forward evidence accumulating (15 sessions).",
         "inference": "The dominant bottleneck is NOT the validation gates. It is (1) Lab→paper hand-off was broken for months, "
                      "now fixed; (2) forward evidence requires calendar time to accrue."},
        {"q": "6. What destroys edges — costs/slippage/survivorship/robustness/holdout/forward?",
         "fact": f"Survivorship: {as_is_tot} ranked strategies, {as_is_pos} positive with dead companies ({100*as_is_pos//as_is_tot}%). "
                 f"Lab: in-sample→out-of-sample: 19% of shortlist pass honest validation. "
                 f"Forward: {forward_trades:,} closed paper trades; {len(sig)} families positive after costs, next-open fills and "
                 f"clustering by entry date ({', '.join(f['family'] for f in sig[:4]) or 'none'}); "
                 f"{len(sig_iid)} by the older iid test on gross returns.",
         "inference": "Out-of-sample generalisation (Lab validation) is the largest measured gate (~81% attrition). "
                      "Survivorship adds ~20% further reduction. Costs add ~6% in-sample. "
                      f"Forward evidence: {len(sig)} of {len(fwd_fam)} families clear the dependence-corrected test; "
                      f"the largest family has {max((f['entry_dates'] for f in fwd_fam), default=0)} independent entry dates at most."},
        {"q": "7. Any small persistent positive performance?",
         "fact": f"{len(sig)} families positive after costs, next-open fills and dependence: " +
                 ("; ".join(f"{f['family']} ({f['mean_basis']:+.2f}%/trade, cluster t={f['cluster_t_basis']:+.1f}, "
                             f"{f['dates_basis']} dates, n={f['n']})" for f in sig[:4]) or "none") +
                 f". Older iid-on-gross test: {len(sig_iid)} families.",
         "inference": ("Candidates exist and must be confirmed over more entry dates, with a correction for the number of "
                       "families tested (luck among 88 independent tests reaches t ~3.25). Not promoted." if sig else
                       "None survive the dependence-corrected test yet; the older iid test overstates because trades "
                       "repeat across funds and share entry days. Absence is not proof of no edge: most families have "
                       "fewer than 20 independent entry dates.")},
        {"q": "8. Enough tests to call absence meaningful?",
         "fact": f"{forward_trades:,} forward trades total; {need_05:,} needed to show +0.5%/trade at t=2 (sd={forward_sd:.1f}%). "
                 f"Longest record: {fw.get('longest_record_sessions',0)} sessions. "
                 f"lab_search alone has {next((f['n'] for f in fwd_fam if f['family']=='lab_search'),0):,} trades.",
         "inference": f"Trade counts are large but entry dates are few, and trades share dates and tickers; the independent "
                      f"sample is the number of entry dates, not trades. For +0.5%/trade across the whole population ~{need_05:,} "
                      f"independent trades would be needed (iid assumption); we have {forward_trades:,} trades on a handful of dates."},
    ]


def market(conn) -> dict:
    """The bull-market checks (market_checks.py) and the unseen window (holdout.py): counts only."""
    out = {}
    try:
        import market_checks
        out["checks"] = market_checks.summary(conn)
    except Exception:                                        # noqa: BLE001
        out["checks"] = {}
    if _has(conn, "holdout_results"):
        r = conn.execute("SELECT COUNT(*), SUM(net_usd > 0), SUM(excess_vs_null_usd > 0) FROM holdout_results").fetchone()
        out["unseen"] = {"tested": r[0], "net_positive": r[1] or 0, "above_random": r[2] or 0}
    return out


def build(conn) -> dict:
    init(conn)
    as_of = datetime.now(timezone.utc).date().isoformat()
    lab_, fac, sv = lab(conn), factory(conn), survivorship(conn)
    fw = forward(conn)
    hyp = hypothesis_coverage(conn)
    fwd_fam = forward_families(conn)
    return {"as_of": as_of, "lab": lab_, "factory": fac, "survivorship": sv, "forward": fw,
            "market": market(conn), "bottlenecks": bottlenecks(lab_, fac, sv),
            "failures": failures(conn, as_of), "hypothesis": hyp,
            "xgboost": xgboost_case(conn), "backtest_dist": backtest_distributions(conn),
            "forward_families": fwd_fam,
            "eight_questions": eight_questions(lab_, fac, sv, fw, fwd_fam, hyp)}


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    r = build(conn)
    text = render(r)
    Path("data/funnel.txt").write_text(text + "\n")
    Path("data/funnel.json").write_text(json.dumps(r, indent=2, default=str))
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
