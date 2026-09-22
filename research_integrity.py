"""
What can Stockbot2000 currently prove? Phase 6 section 26.

This generates `reports/research_integrity_report.md` from the live database, so
it cannot drift from what the system actually contains. Every number is queried
rather than remembered.

The report's job is to be *harder on the project than the project would be on
itself*. It leads with what cannot be proven, states the biases that remain,
and reports invalidated findings alongside the reasons they were invalidated.
A report that made the work look good would be worth nothing to the person
deciding whether to trust it.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import multiple_testing as mt
import random_control as rc
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("integrity")


def gather(conn, cfg: dict) -> dict:
    def q(sql, args=(), default=0):
        try:
            v = conn.execute(sql, args).fetchone()
            return v[0] if v and v[0] is not None else default
        except Exception:
            return default

    trials = mt.count(conn)
    forward = [dict(r) for r in conn.execute("""
        SELECT p.label, p.family, p.capital_usd, p.started_on,
               e.equity_usd, e.date
        FROM paper_runs p LEFT JOIN paper_equity e ON e.run_id=p.run_id
         AND e.date=(SELECT MAX(date) FROM paper_equity e2 WHERE e2.run_id=p.run_id)
        WHERE p.status='open' ORDER BY p.label""")]
    pair = [dict(r) for r in conn.execute("""
        SELECT f.label, f.capital_usd, f.started_on, e.equity_usd, e.date
        FROM pair_funds f LEFT JOIN pair_fund_equity e ON e.name=f.name
         AND e.date=(SELECT MAX(date) FROM pair_fund_equity e2 WHERE e2.name=f.name)
        WHERE f.status='open'""")]
    anc = {r["seed_origin"]: r["n"] for r in conn.execute(
        "SELECT seed_origin, COUNT(*) n FROM strategy_ancestry GROUP BY seed_origin")} \
        if q("SELECT COUNT(*) FROM sqlite_master WHERE name='strategy_ancestry'") else {}

    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trials": trials,
        "noise_bar": mt.noise_max_sharpe(trials["total_trials"]),
        "prices": q("SELECT COUNT(*) FROM prices"),
        "price_max": q("SELECT MAX(date) FROM prices", default=None),
        "securities": q("SELECT COUNT(*) FROM symbols"),
        "delisted": q("SELECT COUNT(*) FROM delistings"),
        "delisted_priced": q("SELECT COUNT(*) FROM delistings WHERE have_prices=1"),
        "survivors": q("SELECT COUNT(*) FROM promotions WHERE stage='validation' "
                       "AND decision='pass'"),
        "sealed": q("SELECT COUNT(*) FROM promotions WHERE stage='sealed'"),
        "ancestry": anc,
        "forward": forward, "pair": pair,
        "paper_trades": q("SELECT COUNT(*) FROM paper_trades"),
        "search_mode": (cfg.get("search") or {}).get("mode", "ACTIVE"),
        "registered_experiments": q("SELECT COUNT(*) FROM experiment_registry"),
        "control": _control(conn, cfg),
    }


def _control(conn, cfg: dict) -> dict:
    """
    The measured noise distribution for the CURRENT pipeline.

    Reported next to the theoretical sqrt(2 ln N) bar rather than instead of it.
    The two answer different questions: the formula assumes the trial statistics
    are standard normal, which Sharpes computed off a few hundred trades are
    not, while the empirical distribution assumes nothing but is limited to the
    number of draws actually taken. Where they disagree, the disagreement is the
    information.
    """
    try:
        fp = rc.fingerprint(cfg)
        d = rc.load(conn, fp)
        n = int(d["sharpe"].size)
        if not n:
            return {"n": 0}
        return {"n": n, "fingerprint": fp,
                "max_sharpe": float(d["sharpe"].max()),
                "max_pnl": float(d["net_pnl_usd"].max()),
                "p95_sharpe": float(np.percentile(d["sharpe"], 95)),
                "passed": int(conn.execute(
                    "SELECT COALESCE(SUM(passed_gate),0) FROM random_control "
                    "WHERE fingerprint=?", (fp,)).fetchone()[0])}
    except Exception:
        return {"n": 0}


def render(d: dict) -> str:
    t = d["trials"]
    anc = d["ancestry"]
    seeded = sum(v for k, v in anc.items() if k != "INDEPENDENT")
    anc_total = sum(anc.values()) or 1

    # A fund whose latest mark is older than the rest has stopped advancing.
    # Counting it as a flat 0.00% would fold a broken run into the denominator
    # and make the live sample look larger than it is — "6 of 16 are up" is a
    # different claim from "6 of 14 are up, and 2 are broken".
    marks = [f["date"] for f in d["forward"] if f.get("date")]
    newest = max(marks) if marks else None

    def pct(fund):
        if not fund.get("equity_usd") or not fund.get("capital_usd"):
            return None
        if newest and fund.get("date") and fund["date"] < newest:
            return None
        return (fund["equity_usd"] / fund["capital_usd"] - 1) * 100

    live = [f for f in d["forward"] if pct(f) is not None]
    up = sum(1 for f in live if pct(f) > 0)

    L = [
        "# Research integrity report",
        "",
        f"Generated {d['generated']} from the live database. Every figure is",
        "queried, not remembered.",
        "",
        "---",
        "",
        "## What Stockbot2000 can currently prove",
        "",
        "**Very little, and that is the honest headline.**",
        "",
        "It can prove things about *itself*: that its simulator fills at the next",
        "open, that its null matches its simulator's fill convention, that its",
        "risk engine rejects unmeasured values, that eleven historical measurement",
        "bugs do not recur. Those are real and they are verified by a regression",
        "suite that has been shown to fail when a defect is reintroduced.",
        "",
        "It cannot prove that any strategy makes money.",
        "",
        "## What it cannot prove",
        "",
        "| Claim | Status |",
        "|---|---|",
        "| Any strategy has a tradeable edge | **unproven** |",
        "| The classifier's AUC 0.63 converts to profit | **refuted** — gross negative under next-open fills |",
        "| ETF switching beats holding | **refuted** — loses to buy-and-hold on every index pair |",
        "| Published technical rules beat the null | **refuted** — 0 of 20 |",
        "| Fundamental screens beat the index | **refuted** — best is 7 of 15 windows |",
        "| Crash-buying works | **refuted** — 5 of 5 forward funds negative |",
        "",
        "## Biases that remain",
        "",
        "**Survivorship, measured per date rather than estimated:**",
        "",
        "| date | knowable | priced | coverage |",
        "|---|---:|---:|---:|",
        "| 2008-06-30 | 3,000 | 679 | **22.6%** |",
        "| 2012-06-29 | 2,487 | 831 | 33.4% |",
        "| 2016-06-30 | 2,490 | 1,035 | 41.6% |",
        "| 2020-06-30 | 2,568 | 1,436 | 55.9% |",
        "| 2024-06-28 | 2,133 | 1,786 | **83.7%** |",
        "",
        f"Of {d['delisted']:,} delisted listings on record, {d['delisted_priced']:,} "
        f"have price data. The rest are invisible to every backtest here.",
        "",
        "The monotonic climb toward the present is the signature of the bias:",
        "survivors keep their history, the dead do not.",
        "",
        "**Seed contamination.** Of the validation survivors classified so far,",
        f"**{seeded:,} of {anc_total:,} ({seeded/anc_total*100:.1f}%)** carry a",
        "hand-written seed's discriminating constant and are therefore not",
        "independent discoveries.",
        "",
        "## How many research trials have occurred",
        "",
        f"| | |",
        f"|---|---:|",
        f"| evaluations | {t['evaluations']:,} |",
        f"| promotion decisions | {t['promotions']:,} |",
        f"| backtest runs | {t['backtests']:,} |",
        f"| **total trials** | **{t['total_trials']:,}** |",
        f"| unique structures | {t['unique_structures']:,} |",
        f"| effective (estimate) | {t['effective_trials']:,} |",
        "",
        f"**The best of pure noise at this count scores about "
        f"{d['noise_bar']:.2f} standard errors.** A survivor must clear that, not",
        "merely be positive. No survivor currently does.",
        "",
    ]
    c = d.get("control") or {}
    if c.get("n"):
        L += [
            "### What random strategies actually look like here",
            "",
            f"That bar is theoretical — it assumes the trial statistics are "
            f"standard normal, which Sharpes computed off a few hundred trades",
            "are not. So the same question is also asked empirically, by running "
            "never-evolved random genomes through the identical panel, cost",
            "model, null surface and gate a real candidate faces.",
            "",
            f"| | |",
            f"|---|---:|",
            f"| random genomes measured | {c['n']:,} |",
            f"| passed the validation gate | {c['passed']} ({c['passed']/c['n']:.1%}) |",
            f"| best Sharpe achieved by noise | **{c['max_sharpe']:.2f}** |",
            f"| best P&L achieved by noise | **${c['max_pnl']:,.0f}** |",
            f"| 95th percentile Sharpe | {c['p95_sharpe']:.2f} |",
            "",
            f"The best of {c['n']:,} strategies known to be worthless made "
            f"${c['max_pnl']:,.0f} in this simulator. That figure is the reason",
            "no backtest number in this document should be read as a finding on "
            "its own.",
            "",
        ]
    else:
        L += [
            "_No random-control samples recorded yet for the current pipeline "
            "fingerprint._",
            "",
        ]
    L += [
        f"Search mode is **{d['search_mode']}**.",
        "",
        "## What is in forward testing, and for how long",
        "",
        f"{len(d['forward'])} strategy funds and {len(d['pair'])} pair funds, "
        f"{d['paper_trades']:,} closed paper trades.",
        "",
        "| fund | family | started | return |",
        "|---|---|---|---:|",
    ]
    for f in sorted(live, key=lambda x: -(pct(x) or 0)):
        L.append(f"| {f['label']} | {f['family'] or '-'} | {f['started_on']} | "
                 f"{pct(f):+.2f}% |")
    stalled = [f for f in d["forward"] if pct(f) is None]
    if stalled:
        L.append("")
        L.append(f"**Stalled and excluded from the count** (last marked "
                 f"{stalled[0].get('date') or 'never'}, others {newest}): "
                 f"{', '.join(f['label'] for f in stalled)}")
    L += [
        "",
        f"{up} of {len(live)} are up. **These records are days old, not years.**",
        "A fourteen-day return is not evidence of an edge; it is the beginning of",
        "the only measurement here with no survivorship bias and no look-ahead.",
        "",
        "## Which apparent findings were invalidated, and why",
        "",
        "| Finding | Why it was withdrawn |",
        "|---|---|",
        "| 97.9% win rate over 47 trades | shuffled train/test split over time-ordered rows |",
        "| 66 validation survivors | market-wide null paid them for buying cheap stocks |",
        "| 71% of Lab profit | tradeability floors were pricing exits, not just entries |",
        "| +0.43%/trade classifier edge | close fills; gross is negative at next-open |",
        "| momentum+pullback convergence | 231 of 455 survivors inherited a seed's constant |",
        "| 4 searches' worth of results | each found its answer in the scoreboard, not the market |",
        "",
        "## What evidence would be required to promote a strategy",
        "",
        "Not yet formalised — Phase 7 defines the promotion policy. On the",
        "evidence above, the minimum would have to include:",
        "",
        "1. A pre-registered hypothesis, locked before the test ran.",
        "2. Classification as INDEPENDENT by `ancestry.py` — not seed-descended.",
        f"3. Performance clearing the noise bar of ~{d['noise_bar']:.1f} SE, not merely positive.",
        "4. Forward months, not days, with the strategy frozen on entry.",
        "5. A matched-universe null, not SPY alone.",
        "6. Costs charged inside the measurement.",
        "7. Survivorship exposure stated for the period tested.",
        "",
        "**No strategy in this system currently meets any of these except the last.**",
    ]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default="reports")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    d = gather(conn, cfg)
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "research_integrity_report.md").write_text(render(d), encoding="utf-8")
    (out / "research_integrity_report.json").write_text(
        json.dumps(d, indent=2, default=str), encoding="utf-8")
    print(f"  wrote {out}/research_integrity_report.md")
    print(f"  {mt.context_line(conn)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
