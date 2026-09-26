"""
Aggregate calibration of the synthetic dead companies (Stage M5, §5.4 of
docs/STAGE_M_RESEARCH.md): does adding them close the gap to a benchmark that
includes the dead?

Ken French's 48 industry portfolios are built from CRSP, delisted firms
included; bias_benchmark.py rebuilds an equal-weighted market return from
them. Here the same equal-weighted monthly return is computed three ways:

    ours       survivors only (bias_benchmark.our_ew_market)
    ours+syn   survivors plus every synthetic company alive that month
               (universe_loader.SYNTH), its delisting bar included in its last month
    CRSP       the French reconstruction

A calibrated synthetic set moves the ours+syn line toward CRSP. The gap that
remains is an UPPER bound on what is still missing: CRSP also covers microcaps
and OTC names this universe never had, so it can stay below ours for reasons
that are not survivorship.

    ./run_bounded.sh ./venv/bin/python french_calibration.py [--start 1997]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

import bias_benchmark as bb
from universe import load_config

log = logging.getLogger("french_calibration")
OUT = Path("data/universe/french_calibration.json")


def synthetic_monthly(path: str, start: str) -> pd.DataFrame:
    """Per company-month: return from the previous month-end close (the delisting bar counts)."""
    df = pd.read_parquet(path, columns=["company_id", "date", "close"], filters=[("date", ">=", f"{start}-01-01")])
    df["ym"] = pd.Index(df["date"]).astype(str).str[:7]
    last = df.sort_values("date").groupby(["company_id", "ym"], observed=True)["close"].last().reset_index()
    last = last.sort_values(["company_id", "ym"])
    last["ret"] = last.groupby("company_id", observed=True)["close"].pct_change()
    return last.dropna(subset=["ret"])[["company_id", "ym", "ret"]]


def our_monthly(cfg: dict, start: str) -> pd.DataFrame:
    """Survivor company-months (the same SQL as bias_benchmark, kept per ticker so they can be pooled)."""
    import storage
    conn = storage.connect(cfg["database"]["market_data_path"])
    types = cfg["universe"]["tradeable_types"]
    ph = ",".join("?" * len(types))
    df = pd.read_sql_query(f"""
        SELECT ticker, ym, close FROM (
            SELECT ticker, substr(date, 1, 7) AS ym, close,
                   ROW_NUMBER() OVER (PARTITION BY ticker, substr(date, 1, 7) ORDER BY date DESC) AS rn
            FROM prices WHERE date >= ?
              AND ticker IN (SELECT ticker FROM symbols WHERE security_type IN ({ph}) AND data_quality IS NULL)
        ) WHERE rn = 1""", conn, params=[f"{start}-01-01", *types])
    conn.close()
    df = df.sort_values(["ticker", "ym"])
    df["ret"] = df.groupby("ticker", observed=True)["close"].pct_change()
    return df.dropna(subset=["ret"])[["ticker", "ym", "ret"]]


def run(cfg: dict, start: str) -> dict:
    import universe_loader as ul
    cache = Path(cfg["universe"].get("archive_cache_dir", "data/archive_snapshots")).parent / "french"
    french = bb.french_ew_market(bb.download(cache))
    ours = our_monthly(cfg, start)
    syn = synthetic_monthly(ul.SYNTH, start)
    # A synthetic return above +300% in a month is a reverse-split-style artifact of
    # a penny path, not something CRSP's equal weight would contain either way; cap
    # it the way the generator caps daily returns, and report how many were capped.
    capped = int((syn["ret"] > 3.0).sum())
    syn["ret"] = syn["ret"].clip(upper=3.0)
    a = ours.groupby("ym")["ret"].agg(["mean", "size"])
    b = syn.groupby("ym")["ret"].agg(["sum", "size"]).rename(columns={"size": "size_syn"})
    m = pd.concat([a, b, french.rename("crsp")], axis=1).dropna(subset=["mean", "crsp"])
    m[["sum", "size_syn"]] = m[["sum", "size_syn"]].fillna(0)
    m["with_syn"] = (m["mean"] * m["size"] + m["sum"]) / (m["size"] + m["size_syn"])
    m = m[m.index >= f"{start}-01"]
    rows = []
    for year, g in m.groupby(m.index.str[:4]):
        o, w, c = bb.annualise(g["mean"]), bb.annualise(g["with_syn"]), bb.annualise(g["crsp"])
        rows.append({"year": year, "ours": o, "ours_syn": w, "crsp": c, "gap": o - c, "gap_syn": w - c,
                     "syn_share": float((g["size_syn"] / (g["size"] + g["size_syn"])).mean())})
    tot = {"ours": bb.annualise(m["mean"]), "ours_syn": bb.annualise(m["with_syn"]), "crsp": bb.annualise(m["crsp"])}
    tot["gap"], tot["gap_syn"] = tot["ours"] - tot["crsp"], tot["ours_syn"] - tot["crsp"]
    closed = sum(abs(r["gap_syn"]) < abs(r["gap"]) for r in rows)
    rep = {"synthetic": ul.SYNTH, "start": start, "months": int(len(m)), "capped_months": capped,
           "all": tot, "years_gap_narrowed": closed, "years": len(rows), "by_year": rows}
    OUT.write_text(json.dumps(rep, indent=1))
    return rep


def render(rep: dict) -> str:
    L = ["", f"  EQUAL-WEIGHTED MARKET vs CRSP (dead included) — {rep['months']} months, synthetic {rep['synthetic']}",
         f"  {'year':<6}{'ours':>8}{'ours+syn':>10}{'CRSP':>8}{'gap':>8}{'gap+syn':>9}{'syn share':>11}"]
    for r in rep["by_year"]:
        L.append(f"  {r['year']:<6}{r['ours']:>8.1%}{r['ours_syn']:>10.1%}{r['crsp']:>8.1%}"
                 f"{r['gap']:>8.1%}{r['gap_syn']:>9.1%}{r['syn_share']:>11.0%}")
    t = rep["all"]
    L += [f"  {'ALL':<6}{t['ours']:>8.1%}{t['ours_syn']:>10.1%}{t['crsp']:>8.1%}{t['gap']:>8.1%}{t['gap_syn']:>9.1%}",
          f"  gap narrowed in {rep['years_gap_narrowed']} of {rep['years']} years; "
          f"{rep['capped_months']} synthetic company-months capped at +300%"]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="1997")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    runtime.be_nice()
    print(render(run(load_config(), a.start)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
