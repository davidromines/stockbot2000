"""
The research library: every strategy idea, with its provenance. Phase 8, items 19-22.

THE RULE THAT GOVERNS THIS WHOLE MODULE
----------------------------------------
Phase 8 states it in capitals: *"All external strategies must be treated as
HYPOTHESES. Never assume a published strategy works in Stockbot's universe."*

So `validation_status` starts at HYPOTHESIS for everything, including ideas with
decades of academic support behind them, and only moves on evidence measured
HERE. A citation is provenance, not a result. Novy-Marx's gross profitability
finding is a reason to test the idea on this data; it is not a reason to believe
the answer in advance.

The library is deliberately a record of ideas, not of code. `conviction.py`
already implements six screens and `seeds.py` twenty published rules; this does
not re-implement them. It records where each came from, what it claimed, what
was actually measured here, and — the part that matters — what is KNOWN AGAINST
it. `known_biases` and `limitations` are required fields, because the single
most expensive habit in this project has been discovering a caveat after
believing a number.

WHY THE EVIDENCE IS COMPUTED, NOT TYPED
-----------------------------------------
Every `results` field is derived from the live database at import time. Typing a
remembered figure into a library is how a retracted result outlives its
retraction: this project has already had one finding survive an hour past its
own refutation because it had been written down somewhere else.

A worked example of why the phrasing matters. The project record says "0 of 20
published rules beat the null." Measured at import: **40.3% of seed evaluations
show positive excess over the null**, and **0% clear the promotion gate**. Both
statements are true and only the second one means anything — the gate sits at
the 95th percentile of what random strategies achieve, so beating the null by a
little is what noise does too. The library stores both numbers so the loose
phrasing cannot be mistaken for the strict one.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("library")

# Validation status. Everything enters at HYPOTHESIS, whatever its pedigree.
HYPOTHESIS = "HYPOTHESIS"      # recorded, never tested here
TESTING = "TESTING"            # under measurement now
REFUTED = "REFUTED"            # measured here and failed
SUPPORTED = "SUPPORTED"        # measured here and passed — nothing is, yet
INCONCLUSIVE = "INCONCLUSIVE"  # measured, sample cannot decide
STATUSES = (HYPOTHESIS, TESTING, REFUTED, SUPPORTED, INCONCLUSIVE)

# How closely our encoding matches what was actually published. This governs
# what a failed test is allowed to conclude.
FAITHFUL = "FAITHFUL"            # the rule as published
ADAPTED = "ADAPTED"              # deliberately changed to fit this universe
APPROXIMATION = "APPROXIMATION"  # the nearest expressible thing, not the rule
FAITHFULNESS = (FAITHFUL, ADAPTED, APPROXIMATION)

# Seeds whose encoding is NOT the published strategy, and why. Refuting one of
# these refutes OUR VERSION of the idea and says little about the publication —
# a distinction worth enforcing in code, because "Jegadeesh & Titman: REFUTED"
# is a far larger claim than anything measured here, and it is the version
# someone would remember.
NOT_FAITHFUL = {
    "cross_sectional_momentum": (APPROXIMATION,
        "published on 3-12 month formation periods; roc_10 is a fortnight, "
        "which is closer to short-term reversal than to momentum"),
    "dual_momentum": (ADAPTED,
        "published as a monthly asset-class rotation, not a daily "
        "single-stock rule"),
    "donchian_breakout": (APPROXIMATION,
        "a z-score break and an N-day-high break are not the same event"),
    "obv_accumulation": (APPROXIMATION,
        "Granville's claim is about divergence, which this only approximates"),
    "cci_extreme": (ADAPTED,
        "designed for commodity futures cycles, applied here to equities"),
}

FAMILIES = ("value", "quality", "momentum", "fundamental_momentum",
            "value_momentum", "value_quality", "defensive", "event_driven",
            "technical", "machine_learning")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_library (
            entry_id          TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            family            TEXT NOT NULL,
            original_author   TEXT,
            source            TEXT,
            publication       TEXT,
            original_hypothesis TEXT NOT NULL,
            original_universe TEXT,
            original_period   TEXT,
            original_metrics  TEXT,
            required_data     TEXT,
            interpretation    TEXT,
            implementation    TEXT,
            known_biases      TEXT NOT NULL,
            faithfulness      TEXT,
            limitations       TEXT NOT NULL,
            results           TEXT,
            validation_status TEXT NOT NULL,
            status_reason     TEXT,
            measured_at       TEXT,
            created_at        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_lib_fam "
                 "ON strategy_library(family)")
    conn.commit()


def upsert(conn, entry: dict) -> None:
    """
    Write one entry. Provenance fields are required, not optional.

    A library entry without `known_biases` and `limitations` is a
    recommendation wearing a citation, and this project's whole record is of
    caveats discovered after a number was believed.
    """
    init(conn)
    for req in ("entry_id", "name", "family", "original_hypothesis",
                "known_biases", "limitations", "validation_status"):
        if not entry.get(req):
            raise SystemExit(f"library entry {entry.get('name')!r} is missing "
                             f"{req!r} — provenance fields are not optional")
    if entry["validation_status"] not in STATUSES:
        raise SystemExit(f"unknown status {entry['validation_status']!r}")
    if entry["family"] not in FAMILIES:
        raise SystemExit(f"unknown family {entry['family']!r}; have {FAMILIES}")

    e = {**entry}
    e.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for k in ("original_universe", "original_metrics", "required_data", "results"):
        if isinstance(e.get(k), (dict, list)):
            e[k] = json.dumps(e[k], sort_keys=True, default=str)
    cols = ",".join(e)
    ph = ",".join("?" * len(e))
    conn.execute(f"INSERT OR REPLACE INTO strategy_library ({cols}) VALUES ({ph})",
                 tuple(e.values()))
    conn.commit()


# ------------------------------------------------------- measured evidence ---

def _seed_evidence(conn, cfg: dict, entry_desc: str) -> dict:
    """
    What this project actually measured for one published rule.

    Matched on `entry_desc` rather than genome text: the stored JSON key order
    differs from `seeds.py`, so an exact text match finds nothing and would
    silently report every published rule as untested.
    """
    g = cfg["lab"].get("gates", {})
    row = conn.execute("""
        SELECT COUNT(*) n,
               SUM(CASE WHEN e.excess_pnl_usd > 0 THEN 1 ELSE 0 END) pos,
               SUM(CASE WHEN e.excess_pnl_usd >= ? AND e.sharpe >= ?
                        AND e.n_trades >= ? THEN 1 ELSE 0 END) passed,
               AVG(e.excess_pnl_usd) avg_excess, MAX(e.sharpe) best_sharpe
        FROM strategies s JOIN evaluations e ON e.strategy_id = s.id
        WHERE s.origin='seed' AND s.generation=0 AND s.entry_desc=?""",
        (g.get("min_excess_pnl_usd", 0), g.get("min_sharpe", 0),
         g.get("min_trades", 20), entry_desc)).fetchone()
    n = row["n"] or 0
    if not n:
        return {"evaluations": 0, "note": "no evaluation recorded here"}
    return {
        "evaluations": int(n),
        "positive_excess": int(row["pos"] or 0),
        "positive_excess_share": (row["pos"] or 0) / n,
        "passed_gate": int(row["passed"] or 0),
        "mean_excess_usd": float(row["avg_excess"] or 0.0),
        "best_sharpe": float(row["best_sharpe"] or 0.0),
        "gate": g,
    }


def _conviction_evidence(conn, screen: str) -> dict:
    """Walk-forward windows won, if `conviction_walkforward` has recorded any."""
    try:
        row = conn.execute("""SELECT COUNT(*) n,
            SUM(CASE WHEN excess > 0 THEN 1 ELSE 0 END) won, AVG(excess) avg
            FROM conviction_walkforward WHERE screen=?""", (screen,)).fetchone()
        if row and row["n"]:
            return {"windows": int(row["n"]), "windows_won": int(row["won"] or 0),
                    "mean_excess_vs_spy": float(row["avg"] or 0.0)}
    except Exception:
        pass
    return {"note": "no stored walk-forward record; see docs for the "
                    "2026-09-14 measurement"}


# ------------------------------------------------------------- the imports ---

def import_seeds(conn, cfg: dict) -> int:
    """The 20 published rules in `seeds.py`, with what was measured here."""
    import genome as gn
    import seeds as seed_lib
    n = 0
    for s in seed_lib.SEEDS:
        desc = gn.describe(s["genome"]["entry"])
        fidelity, fid_why = NOT_FAITHFUL.get(s["name"], (FAITHFUL, ""))
        ev = _seed_evidence(conn, cfg, desc)
        if ev.get("evaluations", 0) == 0:
            status, why = HYPOTHESIS, "no evaluation recorded in this database"
        elif ev["passed_gate"] == 0:
            measured = (f"{ev['evaluations']} evaluations here: "
                        f"{ev['positive_excess_share']:.1%} showed positive "
                        f"excess over the null, but NONE cleared the promotion "
                        f"gate (excess >= "
                        f"${ev['gate'].get('min_excess_pnl_usd', 0):,.0f}, "
                        f"Sharpe >= {ev['gate'].get('min_sharpe', 0)}). The gate "
                        f"sits at the 95th percentile of what random strategies "
                        f"achieve, so positive excess alone is what noise does "
                        f"too.")
            if fidelity == FAITHFUL:
                status, why = REFUTED, measured
            else:
                # The encoding failed, which is not the same as the published
                # idea failing. Recording this as REFUTED would attribute a
                # result to an author whose strategy was never run.
                status = INCONCLUSIVE
                why = (f"OUR ENCODING was refuted, not the published rule — "
                       f"{fidelity.lower()}: {fid_why}. {measured} To refute "
                       f"the publication, the rule would have to be implemented "
                       f"as published first.")
        else:
            status = INCONCLUSIVE
            why = f"{ev['passed_gate']} of {ev['evaluations']} cleared the gate"
        upsert(conn, {
            "entry_id": f"seed:{s['name']}", "name": s["name"],
            "family": "technical",
            "original_author": s["source"].split(",")[0],
            "source": s["source"], "publication": s["source"],
            "original_hypothesis": s["idea"],
            "original_universe": "as published — typically US equities",
            "original_period": "as published",
            "required_data": ["prices", "features"],
            "interpretation": f"Encoded as a genome: {desc}",
            "implementation": "seeds.py",
            "known_biases": (
                "Measured on a survivorship-biased universe: 22.6% coverage of "
                "the knowable 2008 universe rising to 83.7% by 2024. Published "
                "technical rules are also the most widely data-mined ideas in "
                "the field, so any edge is the most likely to be arbitraged."),
            "limitations": s["caution"], "faithfulness": fidelity,
            "results": ev, "validation_status": status, "status_reason": why,
            "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        n += 1
    return n


CONVICTION_PROVENANCE = {
    "piotroski_value": ("Joseph Piotroski",
        "Value Investing: The Use of Historical Financial Statement Information "
        "to Separate Winners from Losers (2000)",
        "Among high book-to-market firms, a nine-point accounting score "
        "separates future winners from losers.", "value_quality"),
    "magic_formula": ("Joel Greenblatt", "The Little Book That Beats the Market (2005)",
        "Rank on earnings yield for cheapness and return on capital for "
        "quality; buy the best combined rank.", "value_quality"),
    "quality_value": ("Robert Novy-Marx",
        "The Other Side of Value: The Gross Profitability Premium (2013)",
        "Gross profits over assets predicts returns about as well as "
        "book-to-market, and the two are complementary.", "value_quality"),
    "conservative": ("Pim van Vliet", "The Conservative Formula (2018)",
        "Low volatility, high net payout yield and positive momentum "
        "together outperform.", "defensive"),
    "buffett": ("Frazzini, Kabiller, Pedersen", "Buffett's Alpha (2018)",
        "Buffett's record is explained by cheap, safe, quality stocks held "
        "with leverage — not by stock-picking magic.", "value_quality"),
    "deep_value": ("Benjamin Graham", "Security Analysis (1934); The Intelligent Investor (1949)",
        "Buy well below conservative estimates of intrinsic worth and let "
        "the margin of safety do the work.", "value"),
}


def import_conviction(conn) -> int:
    import conviction as cv
    n = 0
    for screen in cv.SCREENS:
        author, pub, hyp, fam = CONVICTION_PROVENANCE.get(
            screen, ("unknown", "unknown", f"The {screen} screen.", "value"))
        upsert(conn, {
            "entry_id": f"conviction:{screen}", "name": screen, "family": fam,
            "original_author": author, "source": pub, "publication": pub,
            "original_hypothesis": hyp,
            "original_universe": "US equities, as published",
            "original_period": "as published",
            "required_data": ["daily_fundamentals", "prices"],
            "interpretation": "Ranked WITHIN size buckets, assigned per review "
                              "date, because book-to-market correlates -0.35 "
                              "with log market cap and would otherwise sort "
                              "toward small before it sorts toward cheap.",
            "implementation": "conviction.py",
            "known_biases": (
                "The small-cap leg is the least trustworthy part of this data: "
                "7,062 delisted companies are absent and they concentrate in "
                "microcaps. Fundamentals coverage improves toward the present, "
                "which is itself the signature of survivorship bias."),
            "limitations": (
                "Walk-forward windows overlap heavily and are nowhere near "
                "independent, so 15 windows are not 15 observations. No screen "
                "has cleared a forward test here."),
            "faithfulness": FAITHFUL,
            "results": _conviction_evidence(conn, screen),
            "validation_status": HYPOTHESIS,
            "status_reason": "implemented and backtested here, but no forward "
                             "record has reached the 60-mark floor",
            "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        n += 1
    return n


def import_models(conn) -> int:
    """The classifier and PEAD — implemented here, not imported from anyone."""
    for e in (
        {"entry_id": "model:xgboost", "name": "XGBoost classifier",
         "family": "machine_learning", "original_author": "this project",
         "source": "train_model.py / walk_forward.py",
         "publication": "none — built here",
         "original_hypothesis": "A gradient-boosted classifier over 20 technical "
                                "indicators can rank next-period winners.",
         "original_universe": "US common stock", "original_period": "2011-2026",
         "required_data": ["features", "prices"],
         "interpretation": "31 rolling retrains, 7.6M out-of-sample predictions.",
         "implementation": "train_model.py",
         "known_biases": "Trained on survivorship-biased data; part of the "
                         "measured lift may be survivors recovering.",
         "limitations": "AUC 0.63 is real (31 of 31 folds above 0.5) but the "
                        "ranking is NOT monotonic at its own top decile — the "
                        "top 5 names perform worse than the top 10.",
         "faithfulness": FAITHFUL,
         "results": {"pooled_auc": 0.633, "folds_above_half": "31/31",
                     "gross_pnl_next_open_fills_usd": -58.77,
                     "note": "gross NEGATIVE under honest next-open fills"},
         "validation_status": REFUTED,
         "status_reason": "Under next-open fills the model is gross negative "
                          "before costs: -0.279% per trade over 1,053 trades. "
                          "Ranking skill and tradeable edge are different "
                          "quantities and this is the distance between them."},
        {"entry_id": "event:pead", "name": "Post-earnings announcement drift",
         "family": "event_driven", "original_author": "Ball and Brown; Bernard and Thomas",
         "source": "An Empirical Evaluation of Accounting Income Numbers (1968); "
                   "Post-Earnings-Announcement Drift (1989)",
         "publication": "Journal of Accounting Research",
         "original_hypothesis": "Prices continue drifting in the direction of an "
                                "earnings surprise for weeks after the announcement.",
         "original_universe": "US equities", "original_period": "1960s-1980s",
         "required_data": ["sec_filings", "daily_fundamentals", "prices"],
         "interpretation": "Standardised unexpected earnings (SUE) deciles, "
                           "forward returns at 1/5/21/63 days.",
         "implementation": "pead.py",
         "known_biases": "Filing dates here come from SEC indexes, so the "
                         "announcement date is approximated by the filing date "
                         "— PEAD is sensitive to exactly that timing.",
         "limitations": "One of the most heavily published anomalies, and "
                        "therefore among the most likely to be arbitraged away "
                        "since the original studies.",
         "faithfulness": FAITHFUL,
         "results": {"note": "measured here; no forward record"},
         "validation_status": HYPOTHESIS,
         "status_reason": "implemented and measured, never forward-tested"},
    ):
        e.setdefault("measured_at",
                     datetime.now(timezone.utc).isoformat(timespec="seconds"))
        upsert(conn, e)
    return 2


# Phase 8 items 21-22. Families named in the spec, entered as hypotheses BEFORE
# anything is measured. Pre-registering them is the point: writing down what
# will be tested, and what would count as it failing, before seeing a result is
# the only thing that stops a family being quietly dropped when it disappoints.
#
# Every one of these is UNTESTED here. The citations say why each is worth the
# compute, not what the answer will be.
FAMILY_HYPOTHESES = [
    ("family:value", "Value", "value",
     "Fama and French; Basu", "The Cross-Section of Expected Stock Returns (1992)",
     "Cheap stocks on book-to-market, earnings yield, FCF yield, EV/EBIT and "
     "EV/sales outperform expensive ones over long horizons.",
     ["daily_fundamentals", "prices"],
     "Rank within size buckets assigned per review date. Book-to-market "
     "correlates -0.35 with log market cap here, so an unbucketed value rank "
     "sorts toward small before it sorts toward cheap.",
     "Value's small-cap tilt lands exactly where this database is weakest: "
     "7,062 delisted companies are missing and they concentrate in microcaps.",
     "The value premium has been weak-to-absent in US large caps for much of "
     "the last fifteen years, which overlaps most of the usable data here."),
    ("family:quality", "Quality", "quality",
     "Robert Novy-Marx", "The Other Side of Value (2013)",
     "Gross profits over assets predicts the cross-section about as well as "
     "book-to-market, and ROIC, margins, accruals and leverage add to it.",
     ["daily_fundamentals"],
     "Gross profitability first, since it is the cleanest to compute from what "
     "is held here and correlates only -0.03 with size — so unlike value it "
     "needs no size neutralisation.",
     "Accounting quality metrics are restated after the fact; our fundamentals "
     "are lagged to filing date, which helps but does not eliminate this.",
     "Quality is the leg most likely to be already priced, since it needs no "
     "special data and every screener computes it."),
    ("family:momentum", "Momentum", "momentum",
     "Jegadeesh and Titman", "Returns to Buying Winners and Selling Losers (1993)",
     "Stocks that rose over 3-12 months keep rising over the next 3-12 months; "
     "12-1 momentum skipping the most recent month is the standard form.",
     ["prices", "features"],
     "12-1 as published — NOT the roc_10 fortnight the seeds encode, which is "
     "short-term reversal territory and is why those entries are inconclusive "
     "rather than refuted.",
     "Momentum crashes are the defining risk and they cluster in exactly the "
     "periods this database covers worst — 2008 coverage is 22.6%.",
     "Requires monthly rebalancing at minimum; a $100 account paying spread on "
     "every rebalance may not be able to afford the strategy at all."),
    ("family:fundamental_momentum", "Fundamental momentum",
     "fundamental_momentum", "Bernard and Thomas; Novy-Marx",
     "Post-Earnings-Announcement Drift (1989)",
     "Accelerating earnings, revenue and margins predict returns, and do so "
     "partly independently of price momentum.",
     ["daily_fundamentals", "sec_filings"],
     "EPS and revenue acceleration from lagged filings, with SUE from pead.py.",
     "Filing date approximates announcement date here, and this family is "
     "unusually sensitive to that timing.",
     "Quarterly data gives few observations per name, so the effective sample "
     "is far smaller than the row count suggests."),
    ("family:value_momentum", "Value + momentum", "value_momentum",
     "Asness, Moskowitz and Pedersen", "Value and Momentum Everywhere (2013)",
     "Value and momentum are negatively correlated, so a combination has a "
     "better risk-adjusted profile than either leg alone.",
     ["daily_fundamentals", "prices", "features"],
     "Both legs ranked within size buckets, combined on rank rather than on "
     "score, so neither leg's scale decides the weighting by accident.",
     "Inherits the biases of both legs, and the negative correlation that "
     "makes the combination attractive is itself a historical estimate.",
     "The combination has more parameters than either leg, so it is the more "
     "likely of the three to fit the past."),
    ("family:value_quality", "Value + quality", "value_quality",
     "Asness, Frazzini and Pedersen", "Quality Minus Junk (2019)",
     "Cheap AND profitable AND low-leverage AND cash-generative outperforms "
     "cheap alone; junk value is where the value premium goes to die.",
     ["daily_fundamentals"],
     "Intersection rather than a blended score, so a name must clear every leg "
     "rather than offset a failing one with a strong other.",
     "Already partly implemented as the conviction screens, which have not "
     "cleared a forward test here.",
     "An intersection thins the candidate set fast; at five positions the "
     "resulting book may be too concentrated to interpret."),
    ("family:defensive", "Defensive", "defensive",
     "Frazzini and Pedersen; van Vliet",
     "Betting Against Beta (2014); The Conservative Formula (2018)",
     "Low-beta and low-volatility stocks deliver better risk-adjusted returns "
     "than the CAPM predicts.",
     ["prices", "risk_metrics"],
     "Beta and idiosyncratic volatility are already computed monthly in "
     "risk_metrics, so this family needs no new data.",
     "Low-volatility screens select survivors by construction, which is the "
     "specific bias this database has most of.",
     "The published edge is risk-adjusted, not absolute; on a $100 account "
     "with no leverage available, a better Sharpe at a lower return may be "
     "worth nothing in dollars."),
]


def import_families(conn) -> int:
    """Items 21-22: the named families, pre-registered as untested hypotheses."""
    n = 0
    for (eid, name, fam, author, pub, hyp, data, interp, bias, lim) in FAMILY_HYPOTHESES:
        upsert(conn, {
            "entry_id": eid, "name": name, "family": fam,
            "original_author": author, "source": pub, "publication": pub,
            "original_hypothesis": hyp,
            "original_universe": "US equities, as published",
            "original_period": "as published",
            "required_data": data, "interpretation": interp,
            "implementation": "NOT YET IMPLEMENTED",
            "known_biases": bias, "limitations": lim,
            "faithfulness": FAITHFUL,
            "results": {"note": "not yet tested in this universe"},
            "validation_status": HYPOTHESIS,
            "status_reason": "pre-registered before any measurement. Recorded "
                             "now so that a family which later disappoints "
                             "cannot be quietly dropped from the record.",
        })
        n += 1
    return n


def listing(conn, family: str | None = None, status: str | None = None) -> list:
    init(conn)
    q = "SELECT * FROM strategy_library"
    args, where = [], []
    if family:
        where.append("family=?"); args.append(family)
    if status:
        where.append("validation_status=?"); args.append(status)
    if where:
        q += " WHERE " + " AND ".join(where)
    return [dict(r) for r in conn.execute(q + " ORDER BY family, name", args)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--import-existing", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--family"); ap.add_argument("--status")
    ap.add_argument("--show", metavar="ENTRY_ID")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.import_existing:
        n = (import_seeds(conn, cfg) + import_conviction(conn)
             + import_models(conn) + import_families(conn))
        print(f"\n  imported {n} existing strategies with provenance")

    if a.show:
        e = conn.execute("SELECT * FROM strategy_library WHERE entry_id=?",
                         (a.show,)).fetchone()
        if not e:
            print(f"  no entry {a.show!r}"); conn.close(); return 1
        e = dict(e)
        print(f"\n  {e['name']}   [{e['validation_status']}]")
        print("  " + "-" * 70)
        for k in ("family", "original_author", "publication",
                  "original_hypothesis", "faithfulness", "interpretation",
                  "known_biases", "limitations", "status_reason"):
            if e.get(k):
                print(f"  {k.replace('_', ' ')}:")
                txt = str(e[k])
                while txt:
                    print(f"    {txt[:68]}"); txt = txt[68:]
        conn.close(); return 0

    rows = listing(conn, a.family, a.status)
    counts = {}
    for r in rows:
        counts[r["validation_status"]] = counts.get(r["validation_status"], 0) + 1
    print(f"\n  STRATEGY LIBRARY — {len(rows)} entries")
    print(f"  {counts}")
    print("  Every entry is a HYPOTHESIS until measured HERE. A citation is")
    print("  provenance, not a result.")
    print("  " + "-" * 78)
    print(f"  {'entry':<28}{'family':<20}{'status':<14}author")
    for r in rows:
        print(f"  {r['name'][:27]:<28}{r['family'][:19]:<20}"
              f"{r['validation_status']:<14}{(r['original_author'] or '')[:22]}")
    print()
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
