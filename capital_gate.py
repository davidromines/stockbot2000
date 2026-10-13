"""
Addendum F, Phase C1 — an evidence-based eligibility gate for REAL capital, in SHADOW mode.

Research ranking decides what is worth paper-trading; this gate answers a different question: does the evidence
justify real money?  It reports which current strategies would pass and why not.  It changes NOTHING live: it does
not import slots, execution, broker or the risk engine's decisions, writes only its own append-only table, and
`slots.py` does not read it.  Whether it ever binds is the owner's decision (see the report).

Every criterion returns PASS, FAIL or UNKNOWN.  UNKNOWN blocks (a missing measurement is never an average one).
Thresholds are configuration (`capital_gate:` in config.yaml, defaults below) and are not tuned to any result;
they are stated before the report is read.

  C1  data integrity        fund accounting reconciles
  C2  provenance            versioned identity; share of trades that are a retroactive replay <= max_retro_share
  C3  net, realistic fills  mean honest net per trade (next-open fills, modelled costs) > 0
  C4  independent evidence  >= min_dates of the strategy's OWN independent entry dates
  C5  uncertainty           date-block bootstrap lower bound of the net mean > 0
  C6  multiple testing      the strategy's FAMILY has a max-T adjusted p <= alpha on excess-over-SPY (prospective trades)
  C7  stability             >= min_weeks entry weeks and at least min_positive_weeks of them positive
  C8  cost sensitivity      net mean still > 0 when modelled costs are multiplied by cost_stress
  C9  survivorship          the worst-case survivorship backtest (zero) is positive
  C10 correlation           weekly-return correlation with every already-eligible strategy <= max_corr
  C11 downside              fund max drawdown <= max_drawdown_pct
  C12 decay                 the later half of the strategy's trades has a mean >= 0
  C13 prospective status    its family passed the pre-registered prospective test (forward_families_prospective)

    ./venv/bin/python capital_gate.py            # print and write reports/capital_gate_<date>.md + shadow table
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import forward_stats as fs
from universe import load_config

DEFAULTS = {"max_retro_share": 0.25, "min_dates": 20, "alpha": 0.05, "min_weeks": 3, "min_positive_weeks": 0.6,
            "cost_stress": 2.0, "max_corr": 0.7, "max_drawdown_pct": 20.0, "min_trades": 20}
PASS, FAIL, UNKNOWN, NA = "PASS", "FAIL", "UNKNOWN", "NOT REACHED"
CRITERIA = [("C1", "data integrity"), ("C2", "provenance"), ("C3", "net, realistic fills"), ("C4", "independent evidence"),
            ("C5", "uncertainty"), ("C6", "multiple testing"), ("C7", "stability"), ("C8", "cost sensitivity"),
            ("C9", "survivorship"), ("C10", "correlation"), ("C11", "downside"), ("C12", "decay"), ("C13", "prospective status")]


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("capital_gate") or {})}


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS capital_gate_shadow (
        as_of TEXT NOT NULL, strategy_key TEXT NOT NULL, version INTEGER NOT NULL, verdict TEXT NOT NULL,
        passed TEXT NOT NULL, failed TEXT NOT NULL, unknown TEXT NOT NULL, detail TEXT,
        PRIMARY KEY (as_of, strategy_key, version))""")
    conn.commit()


# --- family-level evidence (C6, C13) -----------------------------------------------------------
def family_evidence(conn) -> dict:
    """{family: max-T adjusted p on prospective excess-over-SPY}, from the same computation as Phase A4."""
    import audit_selection as a4
    sess = a4.sessions(conn)
    df = a4.retro_flag(a4.add_spy(conn, a4.load(conn), sess), sess)
    pro = df[~df["retro"]]
    fams = [k for k, g in pro.groupby("family") if len(g) >= a4.MIN_TRADES]
    mt = fs.maxt_signflip(a4.date_matrix(pro, "excess_pct", fams))
    return {fam: float(mt.loc[fam, "p_maxT"]) if fam in mt.index else float("nan") for fam in df["family"].unique()}, df


def prospective_status(conn) -> tuple:
    """(status, passed families) of the registered prospective test."""
    try:
        e = conn.execute("SELECT status, results FROM experiment_registry WHERE experiment_id='forward_families_prospective' "
                         "ORDER BY version DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return "ABSENT", set()
    if not e:
        return "ABSENT", set()
    passed = set(json.loads(e[1]).get("passed", [])) if e[1] else set()
    return e[0], passed


# --- per-strategy assessment ---------------------------------------------------------------------
def max_drawdown(conn, run_id: str):
    eq = pd.read_sql_query("SELECT equity_usd FROM paper_equity WHERE run_id=? ORDER BY date", conn, params=(run_id,))["equity_usd"]
    if len(eq) < 5:
        return None
    peak = eq.cummax()
    return float(((peak - eq) / peak).max() * 100)


def assess_one(conn, s: dict, tr: pd.DataFrame, fam_p: dict, fam_of: dict, pstat: tuple, sb_zero, recon, st: dict) -> dict:
    """tr = the strategy's own honest trades (columns entry_date, net_pct, cost_pct, retro)."""
    res, why = {}, {}
    # C1
    res["C1"] = UNKNOWN if recon is None else (PASS if recon else FAIL)
    # C2
    if tr.empty:
        res["C2"] = UNKNOWN
    else:
        share = float(tr["retro"].mean())
        res["C2"] = PASS if share <= st["max_retro_share"] else FAIL
        why["C2"] = f"{share:.0%} retroactive"
    # C3
    if len(tr) < 3:
        res["C3"] = UNKNOWN
    else:
        m = float(tr["net_pct"].mean())
        res["C3"] = PASS if m > 0 else FAIL
        why["C3"] = f"{m:+.2f}%"
    # C4
    nd = int(tr["entry_date"].nunique()) if len(tr) else 0
    res["C4"] = PASS if nd >= st["min_dates"] else FAIL
    why["C4"] = f"{nd} dates"
    # C5
    if len(tr) >= st["min_trades"] and nd >= 3:
        b = fs.bootstrap_by_cluster(tr["net_pct"], tr["entry_date"])
        res["C5"] = PASS if b["lo"] > 0 else FAIL
        why["C5"] = f"lower bound {b['lo']:+.2f}%"
    else:
        res["C5"] = UNKNOWN
    # C6
    p = fam_p.get(fam_of)
    res["C6"] = UNKNOWN if p is None or p != p else (PASS if p <= st["alpha"] else FAIL)
    why["C6"] = "family max-T p " + ("n/a" if p is None or p != p else f"{p:.2f}")
    # C7
    if len(tr):
        wk = tr.assign(w=pd.to_datetime(tr["entry_date"]).dt.to_period("W").astype(str)).groupby("w")["net_pct"].mean()
        if len(wk) >= st["min_weeks"]:
            share = float((wk > 0).mean())
            res["C7"] = PASS if share >= st["min_positive_weeks"] else FAIL
            why["C7"] = f"{share:.0%} of {len(wk)} weeks positive"
        else:
            res["C7"] = UNKNOWN
    else:
        res["C7"] = UNKNOWN
    # C8
    if len(tr) >= 3:
        stressed = float((tr["net_pct"] - (st["cost_stress"] - 1) * tr["cost_pct"]).mean())
        res["C8"] = PASS if stressed > 0 else FAIL
        why["C8"] = f"{stressed:+.2f}% at {st['cost_stress']:g}x costs"
    else:
        res["C8"] = UNKNOWN
    # C9
    res["C9"] = UNKNOWN if sb_zero is None or sb_zero != sb_zero else (PASS if sb_zero > 0 else FAIL)
    why["C9"] = "zero-mode " + ("n/a" if sb_zero is None or sb_zero != sb_zero else f"{sb_zero * 100:+.2f}%/trade")
    # C10 is filled in by the caller (needs the eligible set); C11
    dd = max_drawdown(conn, s["run_id"]) if s.get("run_id") else None
    res["C11"] = UNKNOWN if dd is None else (PASS if dd <= st["max_drawdown_pct"] else FAIL)
    why["C11"] = "drawdown " + ("n/a" if dd is None else f"{dd:.1f}%")
    # C12
    if len(tr) >= 6:
        t = tr.sort_values("entry_date")
        late = float(t["net_pct"].iloc[len(t) // 2:].mean())
        res["C12"] = PASS if late >= 0 else FAIL
        why["C12"] = f"later half {late:+.2f}%"
    else:
        res["C12"] = UNKNOWN
    # C13
    status, passed = pstat
    res["C13"] = PASS if (status == "COMPLETE" and fam_of in passed) else (FAIL if status == "COMPLETE" else UNKNOWN)
    why["C13"] = f"test {status}"
    return res, why


def run(conn, cfg: dict, holders_only: bool = False) -> dict:
    import audit_pipeline as ap
    st = settings(cfg)
    s = ap.strategy_table(conn, all_versions=True)
    fam_p, df = family_evidence(conn)
    tr_all = df[["run_id", "entry_date", "net_pct", "cost_pct", "retro", "family"]]
    pstat = prospective_status(conn)
    rec = {r[0]: r[1] for r in conn.execute(
        "SELECT f.fund_id, f.reconciled FROM fund_accounting f JOIN (SELECT fund_id, MAX(as_of) m FROM fund_accounting GROUP BY fund_id) x "
        "ON x.fund_id = f.fund_id AND x.m = f.as_of")}
    import slots
    cur = slots.current(conn, cfg)
    holder_keys = {(h["strategy_key"], h["version"]): sl for sl, h in cur.items() if h}
    is_holder = s.set_index(["strategy_key", "version"]).index.isin(list(holder_keys))
    cand = s[is_holder] if holders_only else s[(s["fw_n"] >= st["min_trades"]) | is_holder]
    rows = []
    for r in cand.itertuples():
        d = r._asdict()
        tr = tr_all[tr_all["run_id"] == r.run_id] if isinstance(r.run_id, str) else tr_all.iloc[0:0]
        res, why = assess_one(conn, d, tr, fam_p, r.family, pstat, r.sb_zero, rec.get(r.run_id) if isinstance(r.run_id, str) else None, st)
        rows.append({"strategy_key": r.strategy_key, "version": int(r.version), "family": r.family, "run_id": r.run_id,
                     "trades": int(len(tr)), "dates": int(tr["entry_date"].nunique()) if len(tr) else 0,
                     "mean": float(tr["net_pct"].mean()) if len(tr) else float("nan"), "slot": holder_keys.get((r.strategy_key, int(r.version))),
                     "res": res, "why": why})
    # C10 greedy: strategies passing everything else, best mean first; unknown pair correlation blocks
    import strategy_diversity as sd
    others = [x for x in rows if all(v == PASS for k, v in x["res"].items() if k != "C10")]
    kept = []
    for x in sorted(others, key=lambda z: -z["mean"]):
        verdict = PASS
        for y in kept:
            c = sd.lookup(conn, (x["strategy_key"], x["version"]), (y["strategy_key"], y["version"]))
            if c is None:
                verdict = UNKNOWN
            elif c > st["max_corr"]:
                verdict = FAIL
                break
        x["res"]["C10"] = verdict
        if verdict == PASS:
            kept.append(x)
    for x in rows:
        x["res"].setdefault("C10", NA)         # correlation is only tested for strategies that pass everything else
        fails = [k for k, v in x["res"].items() if v == FAIL]
        unk = [k for k, v in x["res"].items() if v == UNKNOWN]
        x["verdict"] = "ELIGIBLE" if not fails and not unk else "NOT ELIGIBLE"
        x["fails"], x["unknown"] = fails, unk
    return {"rows": rows, "settings": st, "pstat": pstat, "n_candidates": len(rows)}


def store(conn, o: dict, as_of: str) -> None:
    init(conn)
    for x in o["rows"]:
        conn.execute("INSERT OR REPLACE INTO capital_gate_shadow VALUES (?,?,?,?,?,?,?,?)",
                     (as_of, x["strategy_key"], x["version"], x["verdict"],
                      json.dumps([k for k, v in x["res"].items() if v == PASS]), json.dumps(x["fails"]), json.dumps(x["unknown"]),
                      json.dumps(x["why"])))
    conn.commit()


def render(o: dict, conn, as_of: str) -> str:
    rows, st = o["rows"], o["settings"]
    holders = sorted([x for x in rows if x["slot"]], key=lambda z: z["slot"])
    names = dict(conn.execute("SELECT strategy_key, name FROM league_strategies"))
    L = ["# Phase C1: shadow eligibility gate for real capital", "",
         f"Computed {as_of}, SHADOW only: nothing here is read by `slots.py`, the risk engine or the trader. {o['n_candidates']} strategies assessed "
         f"(every fund with >= {st['min_trades']} honest trades, plus the five slot holders). Unknown blocks.", "",
         "Thresholds (configuration, fixed before the run, not tuned): " + "; ".join(f"{k} {v}" for k, v in st.items()) + ".",
         f"Prospective test `forward_families_prospective`: {o['pstat'][0]}.", "",
         "## The five current slot holders", "",
         "| slot | strategy | trades | own dates | honest mean % | verdict | failed | unknown (cannot be assessed yet) |", "|---:|---|---:|---:|---:|---|---|---|"]
    for x in holders:
        nm = (names.get(x["strategy_key"]) or x["strategy_key"])
        nm = "Lab-discovered strategy" if x["family"] == "lab_search" else nm[:50]
        L.append(f"| {x['slot']} | {nm} | {x['trades']} | {x['dates']} | {'n/a' if x['mean'] != x['mean'] else f'{x['mean']:+.2f}'} | {x['verdict']} | "
                 f"{', '.join(x['fails']) or '-'} | {', '.join(x['unknown']) or '-'} |")
    L += ["", "## How many strategies pass each criterion", "", "| criterion | PASS | FAIL | UNKNOWN | not reached |", "|---|---:|---:|---:|---:|"]
    for cid, label in CRITERIA:
        c = pd.Series([x["res"].get(cid, UNKNOWN) for x in rows]).value_counts()
        L.append(f"| {cid} {label} | {int(c.get(PASS, 0))} | {int(c.get(FAIL, 0))} | {int(c.get(UNKNOWN, 0))} | {int(c.get(NA, 0))} |")
    n_el = sum(x["verdict"] == "ELIGIBLE" for x in rows)
    hold_el = sum(x["verdict"] == "ELIGIBLE" for x in holders)
    L += ["", f"**Eligible under the gate: {n_el} of {len(rows)}. Slot holders eligible: {hold_el} of {len(holders)}.**", "",
          "### Which single criterion blocks the most strategies that otherwise look good", "",
          "Strategies with a positive honest mean and >= 20 trades, by the criteria they fail or cannot yet satisfy:", ""]
    good = [x for x in rows if x["mean"] == x["mean"] and x["mean"] > 0 and x["trades"] >= st["min_trades"]]
    cnt = {}
    for x in good:
        for k in x["fails"] + x["unknown"]:
            cnt[k] = cnt.get(k, 0) + 1
    L += ["| criterion | blocks (of %d) |" % len(good), "|---|---:|"]
    for cid, label in CRITERIA:
        if cnt.get(cid):
            L.append(f"| {cid} {label} | {cnt[cid]} |")
    L += ["", "## Proposed effect on live eligibility (for the owner's decision; nothing has been changed)", "",
          "The gate asks for evidence the record cannot yet contain: 20 independent entry dates per strategy and a completed prospective test. "
          "Enforced today it would leave all five slots empty, which conflicts with the standing rule that slots are filled from day one and never wait for evidence. Options:", "",
          "| option | effect | recommended |", "|---|---|---|",
          "| A. Keep it shadow only; publish the verdict beside each slot in the daily report | no change to trading; the evidence grade is visible | yes, now |",
          "| B. Enforce only the do-no-harm criteria (C1, C2, C8, C9, C11) now; the evidence criteria stay informational | blocks strategies that are data-suspect, cost-fragile, or fail the worst-case survivorship | consider after A has run 2 weeks |",
          "| C. Enforce the full gate | empties the slots until the prospective test completes (about December) | not before the prospective result |", "",
          "## What could be wrong with this analysis", "",
          "- The thresholds are judgement, fixed in advance, and have not been calibrated against any outcome.",
          "- Strategy-level trades are mostly one fund's trades; a fund that trades rarely will fail C4 for a long time whatever its quality.",
          "- C6 uses the family, not the strategy: a good strategy inside a bad family is blocked and a poor one inside a good family is not.",
          "- Slot holders that are stand-ins or pair/value funds have no paper run and are assessed as UNKNOWN throughout.",
          "- Live stops and sizing differ from the paper fund; the gate judges the paper record."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--holders", action="store_true", help="assess only the five slot holders")
    ap.add_argument("--no-store", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = None
    now = datetime.now(timezone.utc)
    o = run(conn, cfg, a.holders)
    if not a.no_store:
        store(conn, o, now.strftime("%Y-%m-%d"))
    text = render(o, conn, now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"capital_gate_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
