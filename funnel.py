"""
Stage T — the strategy funnel, rebuilt from the database every day.

Where does apparent performance disappear, and why? One report, read-only except
for its own two tables, over the stages the system already has (no parallel
validation system, no gate changed):

  Lab search      evaluated -> gross>0 -> net>0 -> beats null -> shortlist ->
                  validation (honest simulator split) -> sealed -> paper -> ranked
  Factory         specified -> backtested -> validated -> robust -> paper ->
                  qualified -> live candidate
  Survivorship    positive survivors-only / with the dead / worst case
  Forward         funds with marks, closed trades, the trades an edge would need

Per strategy it writes structured failure reasons (§18: FAILED_BACKTEST,
FAILED_VALIDATION, FAILED_COSTS, FAILED_SLIPPAGE, FAILED_ROBUSTNESS,
FAILED_SURVIVORSHIP, FAILED_FORWARD, INSUFFICIENT_TRADES — several may apply) and
a near-miss list (§19): failed, but by a small margin. Near misses are not
winners and nothing here promotes or rejects anything.

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
    return "\n".join(L)


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
    return {"as_of": as_of, "lab": lab_, "factory": fac, "survivorship": sv, "forward": forward(conn),
            "market": market(conn), "bottlenecks": bottlenecks(lab_, fac, sv), "failures": failures(conn, as_of)}


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
