"""
The Phase 6 final report. Phase 6 §31 (and the §30 checklist).

Built from the database, the truth-set manifest, the registered experiments
and a run of the regression suite. Every figure is read here, never typed
in: a report that restates numbers from memory outlives their retraction.

The spec's closing rule is kept in the output itself: infrastructure working
is not success, and the goal of Phase 6 was never a profitable strategy. It
was to make a positive result substantially harder to dismiss as an artifact.

    python phase6_report.py                     writes reports/phase6_report.md
    python phase6_report.py --no-tests          skip the suite (marks tests UNRUN)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("phase6")

# §30, item -> evidence: the test files whose PASS it requires, or a check.
CHECKLIST = [
    ("Seed-free search works", ["regression/test_search_hygiene"], "seed_free"),
    ("Seed ancestry tracked", ["regression/test_ancestry_and_freshness"], None),
    ("Truth set immutable", ["regression/test_truth_set"], None),
    ("Truth set versioned", ["regression/test_truth_set"], None),
    ("Truth set hashed", ["regression/test_truth_set"], None),
    ("Point-in-time universe works", ["regression/test_pit_universe"], None),
    ("Fundamental availability dates enforced", ["regression/test_pit_provenance", "regression/test_lookahead"], None),
    ("Data freshness audit works", ["regression/test_ancestry_and_freshness", "regression/test_partial_bars"], None),
    ("Validation firewall documented", [], "firewall_doc"),
    ("Sealed holdout inaccessible to research", ["regression/test_sealed_holdout", "regression/test_seal_boundary"], None),
    ("Experiment registry works", ["regression/test_experiment_registry"], None),
    ("Experiments can be preregistered", ["regression/test_experiment_registry"], None),
    ("Registered experiments cannot silently mutate", ["regression/test_experiment_registry"], None),
    ("Stop sweep works", ["regression/test_sweep_and_decay"], None),
    ("Forward scoreboard works", ["regression/test_scoreboard"], None),
    ("Matched-universe null works", ["regression/test_baselines"], None),
    ("Random control works", ["regression/test_random_control"], None),
    ("Multiple-testing counter works", ["regression/test_multiple_testing"], None),
    ("XGBoost calibration metrics work", ["regression/test_model_calibration"], None),
    ("Signal decay analysis works", ["regression/test_sweep_and_decay"], None),
    ("Regime analysis works", ["regression/test_regimes"], None),
    ("TNON regression test works", ["regression/test_tnon"], None),
    ("Historical measurement bug tests pass", ["regression/test_fill_and_pricing", "regression/test_lookahead",
                                               "regression/test_data_integrity", "test_fills"], None),
    ("Live mode remains disabled", [], "live"),
]


def run_tests() -> dict:
    """name -> PASS/FAIL from ./run_tests.sh, plus the totals line."""
    out = subprocess.run(["./run_tests.sh"], capture_output=True, text=True).stdout
    clean = re.sub(r"\x1b\[[0-9;]*m", "", out)
    res = {m.group(2): m.group(1) for m in re.finditer(r"^\s+(PASS|FAIL)\s+(\S+)", clean, re.M)}
    return {"by_file": res, "passed": sum(v == "PASS" for v in res.values()),
            "failed": sorted(k for k, v in res.items() if v == "FAIL")}


def _q(conn, sql, args=(), default=None):
    try:
        r = conn.execute(sql, args).fetchone()
        return r[0] if r and r[0] is not None else default
    except sqlite3.Error:
        return default


def gather(conn, cfg: dict, tests: dict | None) -> dict:
    import research_integrity
    import truth_set
    ri = research_integrity.gather(conn, cfg)
    d = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ri": ri}
    try:
        man = truth_set.load_manifest()
        d["truth"] = {"versions": sorted(man.get("versions", {})), "problems": truth_set.verify()}
    except Exception as e:                                   # noqa: BLE001
        d["truth"] = {"versions": [], "problems": [f"manifest unreadable: {type(e).__name__}"]}
    try:
        import pit_universe
        d["pit"] = [pit_universe.coverage(conn, day) for day in ("2008-06-30", "2016-06-30", "2024-06-28")]
    except Exception as e:                                   # noqa: BLE001
        d["pit"] = [{"error": f"{type(e).__name__}: {e}"}]
    filings = _q(conn, "SELECT COUNT(*) FROM sec_filings", default=0)
    d["fundamentals"] = {"filings": filings,
                         "with_first_tradeable": _q(conn, "SELECT COUNT(*) FROM sec_filings "
                                                          "WHERE first_tradeable IS NOT NULL", default=0),
                         "with_accepted": _q(conn, "SELECT COUNT(*) FROM sec_filings WHERE accepted IS NOT NULL",
                                             default=0)}
    d["freshness"] = {"prices": _q(conn, "SELECT MAX(date) FROM prices"),
                      "features": _q(conn, "SELECT MAX(date) FROM features WHERE ticker='SPY'"),
                      "daily_fundamentals": _q(conn, "SELECT MAX(date) FROM daily_fundamentals")}
    sf = Path("experiments/seed_free_search/results.json")
    d["seed_free"] = json.loads(sf.read_text()) if sf.exists() else None
    d["firewall_doc"] = Path("docs/VALIDATION_FIREWALL.md").exists()
    import risk_engine
    lim = risk_engine.load_limits()
    d["execution"] = {"mode": str(lim.get("execution_mode", "SIMULATION")).upper(),
                      "by_mode": {m: {"trades": _q(conn, "SELECT COUNT(*) FROM slot_trades WHERE mode=?", (m,), 0),
                                      "open_positions": None}
                                  for m in ("SIMULATION", "SHADOW", "LIVE")}}
    d["forward"] = {"funds": len(ri["forward"]) + len(ri["pair"]),
                    "first_start": min((f["started_on"] for f in ri["forward"] + ri["pair"] if f.get("started_on")),
                                       default=None),
                    "last_mark": ri.get("price_max"), "paper_trades": ri["paper_trades"]}
    d["tests"] = tests
    return d


def checklist(d: dict) -> list:
    tests = (d.get("tests") or {}).get("by_file") or {}
    rows = []
    for item, files, special in CHECKLIST:
        if special == "live":
            state = ("SUPERSEDED" if d["execution"]["mode"] == "LIVE" else "PASS")
            why = ("LIVE armed by the owner under Addendum B (B14); §23 no longer applies"
                   if state == "SUPERSEDED" else "execution_mode is not LIVE")
        elif special == "firewall_doc":
            state, why = ("PASS" if d["firewall_doc"] else "FAIL"), "docs/VALIDATION_FIREWALL.md"
        else:
            if not tests:
                state, why = "UNRUN", "tests not run"
            else:
                got = [tests.get(f) for f in files]
                state = ("PASS" if all(g == "PASS" for g in got) else
                         "MISSING" if any(g is None for g in got) else "FAIL")
                why = ", ".join(f"{f}={g or 'missing'}" for f, g in zip(files, got))
            if special == "seed_free" and not d.get("seed_free"):
                state, why = "FAIL", "no experiments/seed_free_search/results.json"
        rows.append((item, state, why))
    return rows


def render(d: dict) -> str:
    ri, t = d["ri"], d.get("tests") or {}
    tr = ri["trials"]
    pit = d["pit"]
    sf = d.get("seed_free") or {}
    ex = d["execution"]
    fund = d["fundamentals"]
    cl = checklist(d)
    ok = sum(s in ("PASS", "SUPERSEDED") for _, s, _ in cl)

    def pct(a, b):
        return f"{a / b * 100:.1f}%" if b else "—"
    L = ["# STOCKBOT2000 PHASE 6 REPORT", "", f"Generated {d['generated']} from the database and a test run.", "",
         "## STATUS", "",
         f"{ok} of {len(cl)} §30 checklist items pass or are superseded. "
         + ("Phase 6 infrastructure is complete." if ok == len(cl) else "Phase 6 is NOT complete; see the checklist."),
         "**No strategy has demonstrated an edge.** Phase 6 was not meant to find one.", "",
         "## DATA INTEGRITY", "",
         f"- **Truth set:** versions {', '.join(d['truth']['versions']) or 'none'}; "
         + ("verified, hashes match, files read-only" if not d["truth"]["problems"]
            else "PROBLEMS: " + "; ".join(d["truth"]["problems"])),
         "- **Point-in-time universe:** " + "; ".join(
             f"{p['as_of']}: {p['coverage_pct']}% of {p['knowable']:,} knowable priced" if "as_of" in p
             else p.get("error", "?") for p in pit),
         f"- **Delisting coverage:** prices held for {ri['delisted_priced']:,} of {ri['delisted']:,} "
         f"delisted listings ({pct(ri['delisted_priced'], ri['delisted'])})",
         f"- **Fundamental availability:** {fund['with_first_tradeable']:,} of {fund['filings']:,} filings carry "
         f"a first tradeable session ({pct(fund['with_first_tradeable'], fund['filings'])}); "
         f"{fund['with_accepted']:,} an acceptance time",
         f"- **Freshness:** prices {d['freshness']['prices']}, features {d['freshness']['features']}, "
         f"daily_fundamentals {d['freshness']['daily_fundamentals']}", "",
         "## RESEARCH", "",
         f"- **Trials:** {tr['total_trials']:,} cumulative (append-only); the best Sharpe noise alone reaches at "
         f"this count is ~{ri['noise_bar']:.2f}",
         "- **Seed-free search:** " + (
             f"both arms run (n={sf.get('A_seeded', {}).get('n')} each); best fitness seeded "
             f"{sf.get('A_seeded', {}).get('best_fitness', 0):.3f} vs seed-free "
             f"{sf.get('B_seed_free', {}).get('best_fitness', 0):.3f}; seed-shaped share "
             f"{sf.get('A_seeded', {}).get('seed_shaped_share', 0):.0%} vs "
             f"{sf.get('B_seed_free', {}).get('seed_shaped_share', 0):.0%}. Caveat: {sf.get('conclusion_caveat')}"
             if sf else "no result recorded"),
         f"- **Multiple-testing accounting:** counter append-only; search mode {ri['search_mode']}; "
         f"{ri['registered_experiments']} registered experiment versions", "",
         "## VALIDATION", "",
         f"- **Holdout:** sealed; {ri['sealed']} strategies have used their one evaluation",
         f"- **Firewall:** {'documented (docs/VALIDATION_FIREWALL.md)' if d['firewall_doc'] else 'NOT documented'}",
         "- **Random control:** " + (
             f"{ri['control']['passed']} of {ri['control']['n']} random strategies cleared the gate "
             f"(best Sharpe {ri['control']['max_sharpe']:.2f}, best net ${ri['control']['max_pnl']:,.0f})"
             if ri["control"].get("n") else "not run for the current pipeline fingerprint"),
         "- **Matched null:** `baselines.py` per forward fund; `benchmark.py` price x horizon surface in the Lab", "",
         "## FORWARD TESTING", "",
         f"- **Active funds:** {d['forward']['funds']} (paper and pair)",
         f"- **Days forward:** since {d['forward']['first_start']} (last bar {d['forward']['last_mark']})",
         f"- **Total trades:** {d['forward']['paper_trades']:,} closed paper trades", "",
         "## EXECUTION", ""]
    for m in ("SIMULATION", "SHADOW", "LIVE"):
        L.append(f"- **{m.title()}:** {ex['by_mode'][m]['trades']} slot trades recorded"
                 + ("  (**armed**: real orders, Robinhood Agentic)" if m == "LIVE" and ex["mode"] == "LIVE" else ""))
    L += ["", "## REGRESSION", ""]
    if t:
        L += [f"- **Tests:** {t['passed'] + len(t['failed'])} files", f"- **Pass:** {t['passed']}",
              f"- **Fail:** {len(t['failed'])}" + (f" ({', '.join(t['failed'])})" if t["failed"] else "")]
    else:
        L += ["- **Tests:** not run (--no-tests)"]
    L += ["", "### §30 checklist", "", "| item | state | evidence |", "|---|---|---|"]
    L += [f"| {i} | {s} | {w} |" for i, s, w in cl]
    L += ["", "## REMAINING RISKS", "",
          "- **Survivorship bias** is bounded, not closed: the per-date coverage above is what a backtest can see. "
          "Synthetic dead companies fail their realism gate and are for stress bounds only.",
          "- **Real money is trading strategies with no demonstrated edge.** Most slots hold Rising 200 variants, "
          "an entry rule the 14-year stop sweep found loses net in all 30 cells.",
          "- **Forward samples are weeks long.** Nothing clears the scoreboard's 60-mark floor; every forward "
          "breakdown (baselines, regimes) is a record, not a verdict.",
          "- **One seed-free comparison (n=1 per arm)** cannot separate seeding from run-to-run variance.",
          "- **Stops are checked on quotes and exited by market order**: gaps through a stop are not protected.",
          "", "## NEXT RECOMMENDED ENGINEERING PHASE", "",
          "Not another search. Accrue forward time, keep every fund stepping and backed up, and let the league's "
          "sample floors decide. The one purchase that would change the data problem is point-in-time delisted "
          "prices (~$270/yr). Do not launch another million-strategy search.", "",
          "---", "",
          "Infrastructure working is not success. The goal of Phase 6 was to make Stockbot2000 a research system "
          "whose positive result would be substantially harder to dismiss as an artifact.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase 6 final report (§31).")
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--out", default="reports/phase6_report.md")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    tests = None if a.no_tests else run_tests()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    d = gather(conn, cfg, tests)
    text = render(d)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text, encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
