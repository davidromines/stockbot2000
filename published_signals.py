"""Stage L1: import published factor evidence (JKP + OSAP) and measure our
families' long-leg returns before and after publication.

The point of this module is survivorship. Our own price store cannot price the
companies that died, so every backtest we run is conditioned on survival. The
JKP factor portfolios are built from CRSP and therefore include delisted names;
they are the only survivorship-free evidence available here. We import them
verbatim and never re-derive them from our own data.
"""

import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

from universe import load_config

# family -> (JKP factor name, OSAP acronym). The JKP name is the join key into
# the factor files; the acronym is the join key into SignalDoc.
FAMILY_MAP = {
    "value_book": ("be_me", "BM"),
    "earnings_yield": ("ni_me", "EP"),
    "profitability": ("gp_at", "GP"),
    "quality_roa": ("niq_at", "roaq"),
    "quality_piotroski": ("f_score", "PS"),
    "low_investment": ("at_gr1", "AssetGrowth"),
    "low_accruals": ("oaccruals_at", "Accruals"),
    "buyback": ("chcsho_12m", "ShareIss1Y"),
    "liquidity_premium": ("ami_126d", "Illiquidity"),
    "small_cap": ("market_equity", "Size"),
    "xs_momentum": ("ret_12_1", "Mom12m"),
    "seasonality_12m": ("seas_1_1an", "MomSeason"),
    "breakout_52w": ("prc_highprc_252d", "High52"),
    "rsi_reversion": ("ret_1_0", "STreversal"),
    "low_volatility": ("ivol_capm_252d", "IdioVol3F"),
    "balance_sheet": ("o_score", "OScore"),
}

WEIGHTINGS = ("ew", "vw_cap")

# The market series is only published value-weighted; both weightings are
# measured against it so the excess is comparable across the two columns.
MKT_WEIGHTING = "vw_cap"

JKP_FILES = {
    ("pf", "ew"): "pf_ew/[usa]_[all_factors]_[monthly]_[ew].csv",
    ("pf", "vw_cap"): "pf_vw/[usa]_[all_factors]_[monthly]_[vw_cap].csv",
    ("ls", "vw_cap"): "ls_vw/[usa]_[all_factors]_[monthly]_[vw_cap].csv",
    ("mkt", "vw_cap"): "mkt/[usa]_[mkt]_[monthly]_[vw_cap].csv",
}


def init(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS published_signals (
            source       TEXT NOT NULL,
            signal       TEXT NOT NULL,
            acronym      TEXT,
            authors      TEXT,
            year         INTEGER,
            sample_start INTEGER,
            sample_end   INTEGER,
            op_return    REAL,
            op_tstat     REAL,
            description  TEXT,
            direction    INTEGER,
            PRIMARY KEY (source, signal)
        );
        CREATE TABLE IF NOT EXISTS published_returns (
            source    TEXT NOT NULL,
            signal    TEXT NOT NULL,
            leg       TEXT NOT NULL,
            weighting TEXT NOT NULL,
            date      TEXT NOT NULL,
            ret       REAL,
            n         INTEGER,
            PRIMARY KEY (source, signal, leg, weighting, date)
        );
        CREATE TABLE IF NOT EXISTS published_evidence (
            family       TEXT NOT NULL,
            signal       TEXT NOT NULL,
            weighting    TEXT NOT NULL,
            period       TEXT NOT NULL,
            months       INTEGER NOT NULL,
            mean_long    REAL,
            mean_mkt     REAL,
            mean_excess  REAL,
            tstat_excess REAL,
            mean_ls      REAL,
            computed_at  TEXT NOT NULL,
            PRIMARY KEY (family, signal, weighting, period)
        );
        """
    )
    conn.commit()


def _read_jkp(base, rel):
    path = os.path.join(base, rel)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def load_jkp(conn, base="data/jkp"):
    """Load the four JKP files. Returns a dict of row counts."""
    counts = {"pf": 0, "ls": 0, "mkt": 0, "signals": 0}

    # direction is a property of the factor, not of the row; take the modal
    # value so a stray sign flip in one month cannot invert the long leg.
    ls = _read_jkp(base, JKP_FILES[("ls", "vw_cap")])
    ls = ls[ls["name"] != "mkt"]
    direction = (
        ls.groupby("name")["direction"]
        .agg(lambda s: s.value_counts().idxmax())
        .to_dict()
    )

    rows = []
    for weighting in WEIGHTINGS:
        pf = _read_jkp(base, JKP_FILES[("pf", weighting)])
        for rec in pf.itertuples(index=False):
            leg = "pf%d" % int(rec.pf)
            rows.append(("jkp", rec.name, leg, weighting, str(rec.date),
                         float(rec.ret), int(rec.n)))
    counts["pf"] = len(rows)

    for rec in ls.itertuples(index=False):
        rows.append(("jkp", rec.name, "ls", "vw_cap", str(rec.date),
                     float(rec.ret), int(rec.n_stocks)))
    counts["ls"] = len(ls)

    mkt = _read_jkp(base, JKP_FILES[("mkt", "vw_cap")])
    for rec in mkt.itertuples(index=False):
        rows.append(("jkp", rec.name, "mkt", "vw_cap", str(rec.date),
                     float(rec.ret), int(rec.n_stocks)))
    counts["mkt"] = len(mkt)

    conn.executemany(
        "INSERT OR REPLACE INTO published_returns"
        " (source, signal, leg, weighting, date, ret, n)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )

    signals = [
        ("jkp", name, None, None, None, None, None, None, None, None,
         int(direction.get(name, 1)))
        for name in sorted(set(ls["name"]))
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO published_signals"
        " (source, signal, acronym, authors, year, sample_start, sample_end,"
        "  op_return, op_tstat, description, direction)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        signals,
    )
    counts["signals"] = len(signals)
    conn.commit()
    return counts


def _int_or_none(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_osap_doc(conn, path="data/osap/SignalDoc.csv"):
    """Attach SignalDoc metadata to mapped JKP factors and store every acronym."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        doc = list(csv.DictReader(fh))

    by_acronym = {}
    for rec in doc:
        acronym = (rec.get("Acronym") or "").strip()
        if acronym:
            by_acronym[acronym] = rec

    n_osap = 0
    for rec in doc:
        acronym = (rec.get("Acronym") or "").strip()
        if not acronym:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO published_signals"
            " (source, signal, acronym, authors, year, sample_start, sample_end,"
            "  op_return, op_tstat, description, direction)"
            " VALUES ('osap', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                acronym,
                acronym,
                rec.get("Authors"),
                _int_or_none(rec.get("Year")),
                _int_or_none(rec.get("SampleStartYear")),
                _int_or_none(rec.get("SampleEndYear")),
                _float_or_none(rec.get("Return")),
                _float_or_none(rec.get("T-Stat")),
                rec.get("LongDescription"),
            ),
        )
        n_osap += 1

    n_mapped = 0
    for _family, (jkp_name, acronym) in FAMILY_MAP.items():
        rec = by_acronym.get(acronym)
        if rec is None:
            continue
        conn.execute(
            "UPDATE published_signals SET acronym=?, authors=?, year=?,"
            " sample_start=?, sample_end=?, op_return=?, op_tstat=?,"
            " description=? WHERE source='jkp' AND signal=?",
            (
                acronym,
                rec.get("Authors"),
                _int_or_none(rec.get("Year")),
                _int_or_none(rec.get("SampleStartYear")),
                _int_or_none(rec.get("SampleEndYear")),
                _float_or_none(rec.get("Return")),
                _float_or_none(rec.get("T-Stat")),
                rec.get("LongDescription"),
                jkp_name,
            ),
        )
        n_mapped += 1
    conn.commit()
    return {"osap": n_osap, "mapped": n_mapped}


def _series(conn, signal, leg, weighting):
    cur = conn.execute(
        "SELECT date, ret FROM published_returns"
        " WHERE source='jkp' AND signal=? AND leg=? AND weighting=?",
        (signal, leg, weighting),
    )
    return {row[0]: row[1] for row in cur.fetchall() if row[1] is not None}


def _period_of(date, sample_end, pub_year):
    year = int(str(date)[:4])
    if sample_end is not None and year <= sample_end:
        return "pre"
    if pub_year is not None and year > pub_year:
        return "post"
    return "gap"


def _stats(excess, ls_vals):
    n = len(excess)
    if n == 0:
        return None
    mean_excess = sum(excess) / n
    if n > 1:
        var = sum((x - mean_excess) ** 2 for x in excess) / (n - 1)
        sd = var ** 0.5
        tstat = mean_excess / (sd / (n ** 0.5)) if sd > 0 else None
    else:
        tstat = None
    mean_ls = sum(ls_vals) / len(ls_vals) if ls_vals else None
    return mean_excess, tstat, mean_ls


def evidence(conn):
    """Compute pre/post/all long-leg excess for every mapped family."""
    mkt = _series(conn, "mkt", "mkt", MKT_WEIGHTING)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []

    for family, (jkp_name, _acronym) in FAMILY_MAP.items():
        row = conn.execute(
            "SELECT year, sample_end, direction FROM published_signals"
            " WHERE source='jkp' AND signal=?",
            (jkp_name,),
        ).fetchone()
        if row is None:
            continue
        pub_year, sample_end, direction = row
        long_leg = "pf3" if (direction or 1) > 0 else "pf1"

        for weighting in WEIGHTINGS:
            long = _series(conn, jkp_name, long_leg, weighting)
            ls = _series(conn, jkp_name, "ls", "vw_cap")
            buckets = {"pre": [], "post": [], "all": []}
            for date, ret in long.items():
                if date not in mkt:
                    continue
                period = _period_of(date, sample_end, pub_year)
                if period == "gap":
                    continue
                buckets[period].append((ret, mkt[date], ls.get(date)))
                buckets["all"].append((ret, mkt[date], ls.get(date)))

            for period in ("pre", "post", "all"):
                obs = buckets[period]
                if not obs:
                    continue
                excess = [o[0] - o[1] for o in obs]
                ls_vals = [o[2] for o in obs if o[2] is not None]
                stats = _stats(excess, ls_vals)
                if stats is None:
                    continue
                mean_excess, tstat, mean_ls = stats
                rec = {
                    "family": family,
                    "signal": jkp_name,
                    "year": pub_year,
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


def render(rows):
    """One line per family/weighting for the post-publication period."""
    index = {(r["family"], r["weighting"], r["period"]): r for r in rows}
    lines = [
        "%-18s %-6s %-16s %5s %6s %9s %6s %9s"
        % ("family", "weight", "jkp_signal", "pubyr", "months", "post_exc%", "t", "pre_exc%")
    ]
    for family in sorted(FAMILY_MAP):
        jkp_name = FAMILY_MAP[family][0]
        for weighting in WEIGHTINGS:
            post = index.get((family, weighting, "post"))
            pre = index.get((family, weighting, "pre"))
            if post is None:
                continue
            pub_year = ""
            for r in rows:
                if r["family"] == family:
                    pub_year = r.get("year", "")
                    break
            lines.append(
                "%-18s %-6s %-16s %5s %6d %9.2f %6.2f %9s"
                % (
                    family,
                    weighting,
                    jkp_name,
                    pub_year if pub_year is not None else "",
                    post["months"],
                    post["mean_excess"] * 100.0,
                    post["tstat_excess"] if post["tstat_excess"] is not None else float("nan"),
                    ("%.2f" % (pre["mean_excess"] * 100.0)) if pre else "n/a",
                )
            )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stage L1 published signals")
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--evidence", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(load_config()["database"]["market_data_path"])
    try:
        init(conn)
        if args.load:
            print(load_jkp(conn))
            print(load_osap_doc(conn))
        if args.evidence:
            rows = evidence(conn)
            print("%d evidence rows" % len(rows))
        if args.report:
            print(render(evidence(conn)))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
