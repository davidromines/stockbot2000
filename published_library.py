"""Stage L2: attach original-paper provenance to every JKP factor, measure the
post-publication long-leg evidence, and enter each factor into the Research
Library as a HYPOTHESIS.

Stage L1 (published_signals) imported the survivorship-free JKP portfolios and
measured the families we already trade. This stage does the same for all 153
factors, because the only honest prior for a factor is what it did after the
paper that sold it was published (McLean & Pontiff 2016). Nothing here is
evidence about our own data; it is evidence about the factor, and it enters the
library as a hypothesis, never as a validated strategy.
"""

import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import csv
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

import published_signals as ps
import strategy_library
from universe import load_config

CLUSTER_TO_FAMILY = {
    "Value": "value",
    "Size": "value",
    "Quality": "quality",
    "Profitability": "quality",
    "Accruals": "quality",
    "Investment": "quality",
    "Debt Issuance": "quality",
    "Low Leverage": "defensive",
    "Low Risk": "defensive",
    "Momentum": "momentum",
    "Profit Growth": "fundamental_momentum",
    "Seasonality": "technical",
    "Short-Term Reversal": "technical",
}

# Harvey, Liu and Zhu (2016): with hundreds of factors tested, a t of 2 is not
# a discovery. The bar for even entering the library as an adoption candidate
# is 3, and it must clear it in one of the two weightings.
ADOPT_T = 3.0

SOURCE = "JKP Global Factor Data (Jensen, Kelly & Pedersen 2023)"
UNIVERSE = "US common stock (CRSP incl. delisted), tercile portfolios"

_PAREN_YEAR = re.compile(r"\((\d{4})\)")
_ANY_YEAR = re.compile(r"\b(19\d{2}|20[0-3]\d)\b")
_YEAR = re.compile(r"\b(\d{4})\b")


def _year_from_cite(cite):
    if not cite:
        return None
    m = _PAREN_YEAR.search(cite)
    if m:
        return int(m.group(1))
    m = _ANY_YEAR.search(cite)
    return int(m.group(1)) if m else None


def _last_year(text):
    if not text:
        return None
    years = _YEAR.findall(text)
    return int(years[-1]) if years else None


def _num(value, cast):
    try:
        if value is None or str(value).strip() == "":
            return None
        return cast(float(value))
    except (TypeError, ValueError):
        return None


def read_details(path="data/jkp/factor_details.csv",
                 clusters="data/jkp/cluster_labels.csv"):
    """Parse factor_details.csv into {abr_jkp: {...}}.

    Duplicate abr_jkp rows keep the first occurrence: the file is ordered by
    the authors' own grouping and later duplicates are re-listings, not
    corrections.
    """
    cluster_of = {}
    if os.path.exists(clusters):
        with open(clusters, newline="", encoding="utf-8-sig") as fh:
            for rec in csv.DictReader(fh):
                char = (rec.get("characteristic") or "").strip()
                if char:
                    cluster_of[char] = (rec.get("cluster") or "").strip() or None

    out = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for rec in csv.DictReader(fh):
            abr = (rec.get("abr_jkp") or "").strip()
            if not abr or abr in out:
                continue
            cite = (rec.get("cite") or "").strip()
            period = (rec.get("in-sample period") or "").strip()
            name = (rec.get("name_new") or "").strip()
            out[abr] = {
                "name": name or None,
                "cite": cite or None,
                "year": _year_from_cite(cite),
                "sample_end": _last_year(period),
                "tstat": _num(rec.get("t-stat"), float),
                "significance": _num(rec.get("significance"), int),
                "cluster": cluster_of.get(abr),
            }
    return out


def _columns(conn, table):
    return {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}


def attach(conn, details):
    """Add cluster/significance columns and fill provenance for jkp rows."""
    cols = _columns(conn, "published_signals")
    if "cluster" not in cols:
        conn.execute("ALTER TABLE published_signals ADD COLUMN cluster TEXT")
    if "significance" not in cols:
        conn.execute("ALTER TABLE published_signals ADD COLUMN significance INTEGER")

    n = 0
    for signal, d in details.items():
        cur = conn.execute(
            "UPDATE published_signals SET authors=?, year=?, sample_end=?,"
            " description=?, op_tstat=?, cluster=?, significance=?"
            " WHERE source='jkp' AND signal=?",
            (
                d["cite"], d["year"], d["sample_end"], d["name"],
                d["tstat"], d["cluster"], d["significance"], signal,
            ),
        )
        n += cur.rowcount
    conn.commit()
    return n


def evidence_all(conn):
    """Pre/post/all long-leg excess for every jkp signal, family 'jkp:<signal>'."""
    mkt = ps._series(conn, "mkt", "mkt", ps.MKT_WEIGHTING)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []

    rows = conn.execute(
        "SELECT signal, year, sample_end, direction FROM published_signals"
        " WHERE source='jkp' ORDER BY signal"
    ).fetchall()

    for signal, pub_year, sample_end, direction in rows:
        if pub_year is None or sample_end is None:
            continue
        long_leg = "pf3" if (direction or 1) > 0 else "pf1"
        for weighting in ps.WEIGHTINGS:
            long = ps._series(conn, signal, long_leg, weighting)
            ls = ps._series(conn, signal, "ls", ps.MKT_WEIGHTING)
            buckets = {"pre": [], "post": [], "all": []}
            for date, ret in long.items():
                if date not in mkt:
                    continue
                period = ps._period_of(date, sample_end, pub_year)
                if period == "gap":
                    continue
                obs = (ret, mkt[date], ls.get(date))
                buckets[period].append(obs)
                buckets["all"].append(obs)

            for period in ("pre", "post", "all"):
                obs = buckets[period]
                if not obs:
                    continue
                excess = [o[0] - o[1] for o in obs]
                ls_vals = [o[2] for o in obs if o[2] is not None]
                stats = ps._stats(excess, ls_vals)
                if stats is None:
                    continue
                mean_excess, tstat, mean_ls = stats
                rec = {
                    "family": "jkp:" + signal,
                    "signal": signal,
                    "weighting": weighting,
                    "period": period,
                    "months": len(obs),
                    "mean_long": sum(o[0] for o in obs) / len(obs),
                    "mean_mkt": sum(o[1] for o in obs) / len(obs),
                    "mean_excess": mean_excess,
                    "tstat_excess": tstat,
                    "mean_ls": mean_ls,
                    "computed_at": now,
                }
                out.append(rec)
                conn.execute(
                    "INSERT OR REPLACE INTO published_evidence"
                    " (family, signal, weighting, period, months, mean_long,"
                    "  mean_mkt, mean_excess, tstat_excess, mean_ls, computed_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        rec["family"], rec["signal"], rec["weighting"],
                        rec["period"], rec["months"], rec["mean_long"],
                        rec["mean_mkt"], rec["mean_excess"],
                        rec["tstat_excess"], rec["mean_ls"], rec["computed_at"],
                    ),
                )
    conn.commit()
    return out


def candidates(conn):
    """Every jkp signal with post-period evidence, adopt-first ordering."""
    meta = {}
    for row in conn.execute(
        "SELECT signal, description, cluster, year FROM published_signals"
        " WHERE source='jkp'"
    ):
        meta[row[0]] = {"name": row[1], "cluster": row[2], "year": row[3]}

    post = {}
    for row in conn.execute(
        "SELECT signal, weighting, mean_excess, tstat_excess"
        " FROM published_evidence WHERE period='post'"
    ):
        post.setdefault(row[0], {})[row[1]] = (row[2], row[3])

    out = []
    for signal, by_weight in post.items():
        info = meta.get(signal, {})
        ew = by_weight.get("ew", (None, None))
        vw = by_weight.get("vw_cap", (None, None))
        # A missing t is not a pass; only a measured t above the bar adopts.
        adopt = any(t is not None and t > ADOPT_T for t in (ew[1], vw[1]))
        out.append({
            "signal": signal,
            "name": info.get("name"),
            "cluster": info.get("cluster"),
            "year": info.get("year"),
            "post_ew_excess": ew[0],
            "post_ew_t": ew[1],
            "post_vw_excess": vw[0],
            "post_vw_t": vw[1],
            "adopt": adopt,
        })

    def key(c):
        return max(t for t in (c["post_ew_t"], c["post_vw_t"]) if t is not None) \
            if any(t is not None for t in (c["post_ew_t"], c["post_vw_t"])) else float("-inf")

    out.sort(key=key, reverse=True)
    return out


def _fmt_pct(value):
    return "n/a" if value is None else "%.2f" % (value * 100.0)


def _fmt_t(value):
    return "n/a" if value is None else "%.2f" % value


def to_library(conn):
    """Upsert one HYPOTHESIS entry per candidate. Returns entries written."""
    n = 0
    for c in candidates(conn):
        signal = c["signal"]
        row = conn.execute(
            "SELECT direction, sample_start, sample_end, op_tstat, significance,"
            " authors FROM published_signals WHERE source='jkp' AND signal=?",
            (signal,),
        ).fetchone()
        direction, sample_start, sample_end, op_tstat, significance, cite = row
        name = c["name"] or signal
        high = (direction or 1) > 0
        period = ("%s-%s" % (sample_start, sample_end)
                  if sample_start is not None else str(sample_end))
        family = CLUSTER_TO_FAMILY.get(c["cluster"], "technical")
        adopt = "yes" if c["adopt"] else "no"
        reason = (
            "published; post-publication long-leg excess %s%%/mo (t %s) ew,"
            " %s%%/mo (t %s) vw; adopt candidate: %s"
            % (_fmt_pct(c["post_ew_excess"]), _fmt_t(c["post_ew_t"]),
               _fmt_pct(c["post_vw_excess"]), _fmt_t(c["post_vw_t"]), adopt)
        )
        strategy_library.upsert(conn, {
            "entry_id": "published:jkp:" + signal,
            "name": name,
            "family": family,
            "source": SOURCE,
            "publication": cite,
            "original_hypothesis": "%s: %s values predict higher returns (%s)"
                                   % (name, "high" if high else "low", cite),
            "original_period": period,
            "original_universe": UNIVERSE,
            "original_metrics": {"t_stat": op_tstat, "significance": significance},
            "known_biases": (
                "Portfolio evidence: monthly-rebalanced tercile portfolios of all"
                " US stocks incl. microcaps; a single $20 slot position is not the"
                " portfolio. Returns decay after publication (McLean & Pontiff"
                " 2016); only the post-publication period counts."
            ),
            "limitations": (
                "Long-leg excess over the market, before trading costs; our data"
                " may not compute this characteristic; not tested on our data."
            ),
            "results": {
                "post_ew_excess": c["post_ew_excess"],
                "post_ew_t": c["post_ew_t"],
                "post_vw_excess": c["post_vw_excess"],
                "post_vw_t": c["post_vw_t"],
                "adopt": c["adopt"],
            },
            "validation_status": strategy_library.HYPOTHESIS,
            "status_reason": reason,
        })
        n += 1
    conn.commit()
    return n


def render(rows):
    lines = [
        "%-22s %-18s %5s %10s %6s %10s %6s %s"
        % ("signal", "cluster", "year", "post_ew%", "t", "post_vw%", "t", "adopt")
    ]
    for c in rows:
        lines.append(
            "%-22s %-18s %5s %10s %6s %10s %6s %s"
            % (
                c["signal"],
                c["cluster"] or "",
                c["year"] if c["year"] is not None else "",
                _fmt_pct(c["post_ew_excess"]),
                _fmt_t(c["post_ew_t"]),
                _fmt_pct(c["post_vw_excess"]),
                _fmt_t(c["post_vw_t"]),
                "ADOPT" if c["adopt"] else "",
            )
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage L2 published library")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(load_config()["database"]["market_data_path"])
    try:
        ps.init(conn)
        strategy_library.init(conn)
        if args.run:
            details = read_details()
            print("%d factors parsed" % len(details))
            print("%d rows attached" % attach(conn, details))
            print("%d evidence rows" % len(evidence_all(conn)))
            print("%d library entries" % to_library(conn))
        if args.report:
            print(render(candidates(conn)))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
