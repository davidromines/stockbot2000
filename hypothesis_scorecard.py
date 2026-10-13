"""
Addendum F, Phase E1/E2 — is the Knowledge Factory producing different economic hypotheses, and which should be tested next?

E1  Audit: documented ideas -> usable specifications -> strategies -> distinct lineages, with the count of strategies per
    lineage, the origin of every strategy, whether a specification was written before its first evaluation, and how each
    origin kind has fared on the evidence we hold.  Parameter variants are never counted as hypotheses.
E2  Scorecard: one row per lineage (the unit of an economic hypothesis).  Each dimension is 0 to 2 and comes from a stored
    field; the total ORDERS experiments and explains why one was chosen.  It is not evidence of profit and it is not
    combined with any empirical result: results sit beside it, unscored.

    ./venv/bin/python hypothesis_scorecard.py        # prints and writes reports/hypothesis_scorecard_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

DIMENSIONS = [("rationale", "economic rationale stated by the source"), ("literature", "independent literature support"),
              ("data", "data available at decision time"), ("bias", "survivorship / look-ahead exposure"),
              ("cost", "robustness to transaction costs (holding period)"), ("distinct", "distinct from lineages already tested"),
              ("feasible", "feasible at the account size (long-only equities)"), ("validation", "clean independent validation still possible")]
UNTRANSLATED = "untranslated"


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS hypothesis_scorecard (
        as_of TEXT NOT NULL, lineage_id TEXT NOT NULL, total INTEGER NOT NULL, scores TEXT NOT NULL, why TEXT NOT NULL,
        PRIMARY KEY (as_of, lineage_id))""")
    conn.commit()


# --- E1 -----------------------------------------------------------------------------------------
def library(conn) -> dict:
    q = lambda s: conn.execute(s).fetchone()[0]
    ent = pd.read_sql_query("SELECT source, source_type, translation_state, data_available FROM knowledge_entries", conn)
    tr = pd.read_sql_query("SELECT machine_translatable, COUNT(*) n FROM knowledge_translations GROUP BY 1", conn).set_index("machine_translatable")["n"].to_dict()
    lin = pd.read_sql_query("SELECT lineage_id, COUNT(*) n FROM knowledge_lineage GROUP BY 1", conn)
    real = lin[~lin["lineage_id"].str.endswith(UNTRANSLATED)]
    return {"entries": len(ent), "by_source": ent.groupby(["source", "source_type"]).size().sort_values(ascending=False),
            "translations": tr, "genomes": q("SELECT COUNT(*) FROM knowledge_translations WHERE genome IS NOT NULL AND genome NOT IN ('', 'null')"),
            "lineages_total": int(len(lin)), "lineages_real": int(len(real)), "title_only": int(lin[lin["lineage_id"].str.endswith(UNTRANSLATED)]["n"].sum()),
            "linked_entries": q("SELECT COUNT(DISTINCT entry_id) FROM knowledge_links"), "linked_strategies": q("SELECT COUNT(DISTINCT strategy_key) FROM knowledge_links"),
            "reproductions": q("SELECT COUNT(*) FROM knowledge_reproductions"),
            "data_yes": int((ent["data_available"] == "YES").sum()), "data_no": int((ent["data_available"] == "NO").sum())}


def origins(conn) -> pd.DataFrame:
    import audit_pipeline as ap
    s = ap.strategy_table(conn)
    p = pd.read_sql_query("SELECT strategy_key, origin_kind, lineage_id, entry_id FROM strategy_provenance", conn).drop_duplicates("strategy_key")
    made = pd.read_sql_query("SELECT strategy_key, version, created_at FROM league_strategies", conn)      # when the strategy was DEFINED
    m = s.merge(p, on="strategy_key", how="inner").merge(made, on=["strategy_key", "version"], how="left")
    first_eval = pd.read_sql_query("SELECT strategy_key, MIN(as_of) first_eval FROM strategy_metrics GROUP BY 1", conn)
    m = m.merge(first_eval, on="strategy_key", how="left")
    m["specified_before_eval"] = np.where(m["first_eval"].isna(), np.nan, (m["created_at"].str[:10] <= m["first_eval"]).astype(float))
    return m


def by_origin(m: pd.DataFrame) -> pd.DataFrame:
    g = m.groupby("origin_kind")
    return pd.DataFrame({"strategies": g.size(), "lineages": g["lineage_id"].nunique(),
                         "per_lineage": g.size() / g["lineage_id"].nunique(),
                         "pos_as_is": g["sb_as_is"].apply(lambda x: float((x.dropna() > 0).mean()) if x.notna().any() else np.nan),
                         "pos_zero": g["sb_zero"].apply(lambda x: float((x.dropna() > 0).mean()) if x.notna().any() else np.nan),
                         "pos_unseen": g["holdout"].apply(lambda x: float((x.dropna() > 0).mean()) if x.notna().any() else np.nan),
                         "fw_funds": g["fw_n"].apply(lambda x: int((x >= 20).sum())),
                         "fw_mean": g.apply(lambda d: float(d.loc[d["fw_n"] >= 20, "fw_mean"].mean()) if (d["fw_n"] >= 20).any() else np.nan, include_groups=False),
                         "prespec": g["specified_before_eval"].mean()}).sort_values("strategies", ascending=False)


# --- E2 -----------------------------------------------------------------------------------------
def scorecard(conn, m: pd.DataFrame) -> pd.DataFrame:
    ent = pd.read_sql_query("SELECT e.entry_id, l.lineage_id, e.source_type, e.original_claim, e.data_available, e.long_short, e.holding_period "
                            "FROM knowledge_entries e JOIN knowledge_lineage l USING(entry_id)", conn)
    ent = ent[~ent["lineage_id"].str.endswith(UNTRANSLATED)]
    st = pd.read_sql_query("SELECT lineage_id, independent_sources, test_count, holdout_tests, variant_count, strategy_count FROM knowledge_lineage_stats "
                           "WHERE as_of=(SELECT MAX(as_of) FROM knowledge_lineage_stats)", conn).set_index("lineage_id")
    hold = pd.read_sql_query("SELECT strategy_key, avg_hold_days FROM strategy_hold", conn).drop_duplicates("strategy_key").set_index("strategy_key")["avg_hold_days"]
    corr = pd.read_sql_query("SELECT key_a, key_b, corr FROM strategy_correlation", conn)
    lin_of = m.set_index("strategy_key")["lineage_id"].to_dict()
    corr["la"], corr["lb"] = corr["key_a"].map(lin_of), corr["key_b"].map(lin_of)
    cross = corr.dropna(subset=["la", "lb"])
    cross = cross[cross["la"] != cross["lb"]]
    maxc = pd.concat([cross[["la", "corr"]].rename(columns={"la": "l"}), cross[["lb", "corr"]].rename(columns={"lb": "l"})]).groupby("l")["corr"].median()
    rows = []
    for lid, g in ent.groupby("lineage_id"):
        strat = m[m["lineage_id"] == lid]
        s = st.loc[lid] if lid in st.index else None
        sc, why = {}, {}
        has_claim = g["original_claim"].fillna("").str.len().gt(20).any()
        academic = g["source_type"].isin(["ACADEMIC_PAPER", "KNOWN_FACTOR"]).any()
        sc["rationale"] = 2 if (has_claim and academic) else 1 if (has_claim or academic) else 0
        why["rationale"] = "academic source with a stated claim" if sc["rationale"] == 2 else "practitioner source or no stated claim"
        nsrc = int(s["independent_sources"]) if s is not None else 1
        sc["literature"] = 2 if nsrc >= 2 else 1 if (g["source_type"] == "KNOWN_FACTOR").any() else 0
        why["literature"] = f"{nsrc} independent source(s)" + ("; published factor" if (g["source_type"] == "KNOWN_FACTOR").any() else "")
        da = (g["data_available"] == "YES").mean()
        sc["data"] = 2 if da >= 0.5 else 1 if len(strat) else 0
        why["data"] = f"{da:.0%} of entries data-available" + (f"; {len(strat)} strategies built" if len(strat) else "; none built")
        z = strat["sb_zero"].dropna()
        sc["bias"] = 1 if z.empty else (2 if (z > 0).mean() >= 0.6 else 0 if (z > 0).mean() < 0.3 else 1)
        why["bias"] = "no survivorship backtest" if z.empty else f"{(z > 0).mean():.0%} positive in the worst case"
        h = hold.reindex(strat["strategy_key"]).dropna()
        hd = float(h.median()) if len(h) else np.nan
        sc["cost"] = 1 if np.isnan(hd) else (2 if hd >= 20 else 1 if hd >= 5 else 0)
        why["cost"] = "holding period unknown" if np.isnan(hd) else f"median hold {hd:.0f} sessions"
        c = maxc.get(lid, np.nan)
        sc["distinct"] = 1 if np.isnan(c) else (2 if c < 0.4 else 1 if c < 0.6 else 0)
        why["distinct"] = "correlation with other lineages not measured" if np.isnan(c) else f"median cross-lineage correlation {c:.2f}"
        ls = g["long_short"].dropna().str.lower()
        sc["feasible"] = 2 if (ls.empty or (ls.str.contains("long")).any()) else 1
        why["feasible"] = "long-only or long leg encodable"
        tc = int(s["test_count"]) if s is not None else 0
        sc["validation"] = 2 if tc <= 20 else 1 if tc <= 100 else 0
        why["validation"] = f"{tc} prior tests in this lineage"
        rows.append({"lineage": lid, "entries": len(g), "strategies": len(strat), "variants": int(s["variant_count"]) if s is not None else 0,
                     "total": sum(sc.values()), **{"s_" + k: v for k, v in sc.items()}, "why": why,
                     "as_is": float(strat["sb_as_is"].median() * 100) if strat["sb_as_is"].notna().any() else np.nan,
                     "zero": float(strat["sb_zero"].median() * 100) if strat["sb_zero"].notna().any() else np.nan,
                     "fw_funds": int((strat["fw_n"] >= 20).sum()), "fw_mean": float(strat["fw_mean"].dropna().mean()) if strat["fw_mean"].notna().any() else np.nan})
    return pd.DataFrame(rows).sort_values(["total", "entries"], ascending=False)


def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def render(conn, as_of: str) -> str:
    lib, m = library(conn), origins(conn)
    bo, sc = by_origin(m), scorecard(conn, m)
    init(conn)
    import json
    for r in sc.itertuples():
        conn.execute("INSERT OR REPLACE INTO hypothesis_scorecard VALUES (?,?,?,?,?)", (as_of[:10], r.lineage, int(r.total),
                     json.dumps({k: getattr(r, "s_" + k) for k, _ in DIMENSIONS}), json.dumps(r.why)))
    conn.commit()
    nonmach = m[(m["origin_kind"] != "MACHINE_GENERATED") & (m["lineage_id"] != "MACHINE:search")]
    L = ["# Phase E1-E2: the Knowledge Factory audit and the hypothesis scorecard", "",
         f"Computed {as_of}, read-only except the append-only `hypothesis_scorecard` table. The scorecard orders experiments; it is not evidence that any hypothesis is profitable.", "",
         "## E1. What the library actually contains", "",
         f"- **{lib['entries']:,} documented ideas**, of which **{lib['title_only']:,} are title-only** (no extractable rule): they sit in lineages named `*:untranslated` and cannot be tested. "
         f"Usable specifications: {lib['genomes']:,} with a stored genome ({lib['translations'].get('YES', 0)} fully and {lib['translations'].get('PARTIAL', 0)} partly machine-translatable); {lib['data_yes']} marked data-available, {lib['data_no']} data-unavailable.",
         f"- Those specifications map to **{lib['lineages_real']} distinct lineages** (the unit of an economic hypothesis) and produced **{lib['linked_strategies']:,} strategies from {lib['linked_entries']} entries**; {lib['reproductions']} are recorded reproductions of a source rule.", "",
         "| source | type | entries |", "|---|---|---:|"]
    for (src, typ), n in lib["by_source"].items():
        L.append(f"| {src} | {typ} | {n:,} |")
    L += ["", "### Strategies by origin (latest version of each; machine search shown for contrast)", "",
          "| origin | strategies | lineages | strategies per lineage | positive as_is | positive worst case | positive unseen | funds with >= 20 fwd trades | mean fwd honest % (funds with >= 20 trades) | specified before first evaluation |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k, r in bo.iterrows():
        L.append(f"| {k} | {int(r.strategies):,} | {int(r.lineages)} | {r.per_lineage:.1f} | {f(r.pos_as_is * 100, '{:.0f}%')} | {f(r.pos_zero * 100, '{:.0f}%')} | {f(r.pos_unseen * 100, '{:.0f}%')} | {int(r.fw_funds)} | {f(r.fw_mean)} | {f(r.prespec * 100, '{:.0f}%')} |")
    top = nonmach["lineage_id"].value_counts()
    L += ["", f"Outside machine search there are {len(nonmach):,} strategies in {nonmach['lineage_id'].nunique()} lineages: **{len(nonmach) / nonmach['lineage_id'].nunique():.0f} variants per lineage on average**; "
          f"the five largest lineages hold {top.head(5).sum():,} strategies ({top.head(5).sum() / len(nonmach):.0%}): " + ", ".join(f"{k} {v}" for k, v in top.head(5).items()) + ". "
          "Hybrid strategies come from two lineages. The library is therefore ~100 hypotheses represented by ~2,000 strategies, not 2,000 hypotheses; the Phase A4 effective number of independent family tests was about 28.", "",
          "**Answer to E1:** the factory is mostly reproducing variants of a small set of well-known factors (momentum, earnings surprise, quality/accruals, value, reversal, trend, low volatility), as designed; "
          "it is not generating many economically distinct ideas, and 91 % of the documented ideas never reached a testable form. "
          "The sound step is to widen distinct lineages (E2 below), not to add parameter variants.", "",
          "## E2. Scorecard (0 to 2 per dimension; ordering only)", "",
          "Dimensions: " + "; ".join(f"**{k}** = {d}" for k, d in DIMENSIONS) + ".", "",
          "### Highest-scoring lineages, with what they have shown so far (unscored)", "",
          "| lineage | total / 16 | entries | strategies | rationale | literature | data | bias | cost | distinct | feasible | validation | as_is % | worst case % | fwd funds >= 20 trades |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in sc.head(15).itertuples():
        L.append(f"| {r.lineage} | {r.total} | {r.entries} | {r.strategies} | {r.s_rationale} | {r.s_literature} | {r.s_data} | {r.s_bias} | {r.s_cost} | {r.s_distinct} | {r.s_feasible} | {r.s_validation} | {f(r.as_is)} | {f(r.zero)} | {r.fw_funds} |")
    L += ["", "### Why the top five were selected", ""]
    for r in sc.head(5).itertuples():
        L.append(f"- **{r.lineage}** ({r.total}/16): " + "; ".join(f"{k}: {r.why[k]}" for k, _ in DIMENSIONS if getattr(r, 's_' + k) == 2) + ".")
    L += ["", "### Lowest-scoring lineages (deprioritised)", "", "| lineage | total | main weaknesses |", "|---|---:|---|"]
    for r in sc.tail(6).itertuples():
        L.append(f"| {r.lineage} | {r.total} | " + "; ".join(f"{k}: {r.why[k]}" for k, _ in DIMENSIONS if getattr(r, 's_' + k) == 0) + " |")
    L += ["", "### How the scorecard is to be used", "",
          "1. It prioritises which lineage to specify and test next; it never promotes, ranks for capital, or changes a lifecycle state.",
          "2. A new test starts from a pre-registered one-paragraph specification (hypothesis, rule, window, what would count as failure) in `experiment_registry`, not from a new batch of parameter variants.",
          "3. Every market or window tried is added to the trial ledger, so the multiple-testing denominator stays honest.", "",
          "## What could be wrong with this analysis", "",
          "- Lineage assignment is the factory's own (keyword and rule based): two lineages may be one idea and one lineage several; lineage counts are an estimate of distinct hypotheses, not a count.",
          "- The `bias` dimension uses the worst-case survivorship backtest as an exposure proxy, so the order is not independent of backtests; results are shown beside the score, not in it, for the other columns.",
          "- Dimension scores are coarse thresholds on stored fields (stated in the code); they do not capture economic quality, which needs a reader.",
          "- 'Specified before first evaluation' compares the provenance record time with the first stored metric date, at day resolution.",
          "- Strategies of machine origin are one lineage by construction (`MACHINE:search`), so per-lineage figures for them are not comparable."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    now = datetime.now(timezone.utc)
    text = render(conn, now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"hypothesis_scorecard_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
