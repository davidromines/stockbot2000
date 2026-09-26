"""Regression test for Stage L2 (published_library).

Everything runs against an in-memory database and tiny CSVs in a temp dir; the
real market_data.db and the JKP downloads are never touched.
"""

import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import published_library as pl
import published_signals as ps
import strategy_library

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


DETAILS_HEADER = "abr_jkp,name_new,cite,in-sample period,t-stat,direction,significance\n"
DETAILS_ROWS = [
    "be_me,Book-to-market,Foster Olsen and Shevlin (1984),1974 - 1981,4.10,1,1\n",
    "ret_12_1,Momentum,Chan Jegadeesh and Lakonishok (1996) 1972/1,1965 - 1993,5.20,1,1\n",
    "at_gr1,Asset growth,Cooper Gulen and Schill (2008),1968 - 2003,3.10,-1,1\n",
    ",No abbreviation,Someone (2001),1990 - 2000,1.00,1,0\n",
    "be_me,Duplicate row,Someone Else (2020),1990 - 2000,9.99,1,1\n",
]
CLUSTERS = "characteristic,cluster\nbe_me,Value\nret_12_1,Momentum\nat_gr1,Investment\n"   # keyed by JKP code, as the real file is


def write_csvs(tmp):
    dpath = os.path.join(tmp, "factor_details.csv")
    cpath = os.path.join(tmp, "cluster_labels.csv")
    with open(dpath, "w", encoding="utf-8") as fh:
        fh.write(DETAILS_HEADER)
        fh.writelines(DETAILS_ROWS)
    with open(cpath, "w", encoding="utf-8") as fh:
        fh.write(CLUSTERS)
    return dpath, cpath


def seed(conn):
    ps.init(conn)
    strategy_library.init(conn)
    conn.executemany(
        "INSERT OR REPLACE INTO published_signals"
        " (source, signal, acronym, authors, year, sample_start, sample_end,"
        "  op_return, op_tstat, description, direction)"
        " VALUES ('jkp', ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)",
        [("be_me", 1), ("ret_12_1", 1), ("at_gr1", -1)],
    )
    rows = []
    # be_me: pre 1980 (in-sample), post 1990 (after 1984). Long leg pf3.
    for year, ret in ((1980, 0.02), (1990, 0.01), (1991, 0.01), (1992, 0.01)):
        rows.append(("jkp", "be_me", "pf3", "ew", "%d-01-31" % year, ret, 100))
        rows.append(("jkp", "be_me", "pf3", "vw_cap", "%d-01-31" % year, ret, 100))
        rows.append(("jkp", "be_me", "ls", "vw_cap", "%d-01-31" % year, ret, 100))
        rows.append(("jkp", "mkt", "mkt", "vw_cap", "%d-01-31" % year, 0.0, 100))
    # ret_12_1: post returns far above the market -> t above 3.
    for year in (1994, 1995, 1996, 1997, 1998, 1999):
        rows.append(("jkp", "ret_12_1", "pf3", "ew", "%d-01-31" % year, 0.05, 100))
        rows.append(("jkp", "ret_12_1", "pf3", "vw_cap", "%d-01-31" % year, 0.05, 100))
        rows.append(("jkp", "ret_12_1", "ls", "vw_cap", "%d-01-31" % year, 0.05, 100))
        rows.append(("jkp", "mkt", "mkt", "vw_cap", "%d-01-31" % year, 0.0, 100))
    # at_gr1: direction -1 so the long leg is pf1; post returns below market.
    for year in (2004, 2005, 2006, 2007, 2008, 2009):
        rows.append(("jkp", "at_gr1", "pf1", "ew", "%d-01-31" % year, -0.01, 100))
        rows.append(("jkp", "at_gr1", "pf1", "vw_cap", "%d-01-31" % year, -0.01, 100))
        rows.append(("jkp", "at_gr1", "ls", "vw_cap", "%d-01-31" % year, -0.01, 100))
        rows.append(("jkp", "mkt", "mkt", "vw_cap", "%d-01-31" % year, 0.0, 100))
    conn.executemany(
        "INSERT OR REPLACE INTO published_returns"
        " (source, signal, leg, weighting, date, ret, n)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def main():
    tmp = tempfile.mkdtemp()
    dpath, cpath = write_csvs(tmp)

    details = pl.read_details(dpath, cpath)
    check("read_details skips empty abr_jkp", len(details) == 3, str(sorted(details)))
    check("cite with parentheses -> year",
          details["be_me"]["year"] == 1984, str(details["be_me"]["year"]))
    check("cite with trailing date -> year",
          details["ret_12_1"]["year"] == 1996, str(details["ret_12_1"]["year"]))
    check("in-sample period -> sample_end",
          details["be_me"]["sample_end"] == 1981, str(details["be_me"]["sample_end"]))
    check("duplicate abr_jkp keeps first row",
          details["be_me"]["tstat"] == 4.10, str(details["be_me"]["tstat"]))
    check("cluster attached by JKP code",
          details["be_me"]["cluster"] == "Value", str(details["be_me"]["cluster"]))

    conn = sqlite3.connect(":memory:")
    seed(conn)

    n1 = pl.attach(conn, details)
    check("attach updates jkp rows", n1 == 3, str(n1))
    row = conn.execute(
        "SELECT authors, year, sample_end, description, op_tstat, cluster,"
        " significance FROM published_signals WHERE signal='be_me'"
    ).fetchone()
    check("attach writes provenance",
          row[0] == "Foster Olsen and Shevlin (1984)" and row[1] == 1984
          and row[2] == 1981 and row[4] == 4.10 and row[5] == "Value",
          str(row))
    n2 = pl.attach(conn, details)
    row2 = conn.execute(
        "SELECT authors, year, sample_end, description, op_tstat, cluster,"
        " significance FROM published_signals WHERE signal='be_me'"
    ).fetchone()
    check("attach is idempotent", n2 == 3 and row2 == row, str((n2, row2)))

    rows = pl.evidence_all(conn)
    fams = {r["family"] for r in rows}
    check("evidence_all uses jkp:<signal> family",
          fams == {"jkp:be_me", "jkp:ret_12_1", "jkp:at_gr1"}, str(sorted(fams)))
    be = [r for r in rows if r["signal"] == "be_me" and r["weighting"] == "ew"]
    pre = [r for r in be if r["period"] == "pre"]
    post = [r for r in be if r["period"] == "post"]
    check("pre/post split follows year and sample_end",
          len(pre) == 1 and pre[0]["months"] == 1
          and len(post) == 1 and post[0]["months"] == 3,
          str([(r["period"], r["months"]) for r in be]))
    stored = conn.execute(
        "SELECT COUNT(*) FROM published_evidence WHERE family='jkp:be_me' AND weighting='ew'"
    ).fetchone()[0]
    check("evidence_all persists rows", stored == len(be), str(stored))

    cands = pl.candidates(conn)
    by_signal = {c["signal"]: c for c in cands}
    check("candidates covers every post signal", len(cands) == 3, str(len(cands)))
    check("high post t adopts", by_signal["ret_12_1"]["adopt"] is True,
          str(by_signal["ret_12_1"]))
    check("low post t does not adopt", by_signal["be_me"]["adopt"] is False,
          str(by_signal["be_me"]))
    check("candidates sorted by larger post t",
          cands[0]["signal"] == "ret_12_1", str([c["signal"] for c in cands]))

    written = pl.to_library(conn)
    check("to_library writes one entry per candidate", written == 3, str(written))
    cur = conn.execute("SELECT * FROM strategy_library WHERE entry_id='published:jkp:be_me'")
    r = cur.fetchone()
    entry = dict(zip([d[0] for d in cur.description], r)) if r else {}
    if isinstance(entry.get("results"), str):
        import json
        entry["results"] = json.loads(entry["results"])      # stored as JSON text
    check("library entry is a HYPOTHESIS",
          entry["validation_status"] == strategy_library.HYPOTHESIS,
          str(entry.get("validation_status")))
    check("library entry family from cluster map",
          entry["family"] == "value", str(entry.get("family")))
    check("library entry id and name",
          entry["entry_id"] == "published:jkp:be_me"
          and entry["name"] == "Book-to-market", str(entry.get("name")))
    check("library entry records adopt result",
          entry["results"]["adopt"] is False, str(entry.get("results")))

    conn.close()
    if FAILED:
        print("%d FAILED" % len(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
