"""
Stage L1: published_signals.py on tiny hand-made JKP / OSAP files. Checks the
long-leg choice from the factor's direction, the pre / gap / post split, and the
excess-return arithmetic by hand. No network; never the real downloads.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import math
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import published_signals as ps

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


# be_me: long leg pf3 (direction +1); ni_me: long leg pf1 (direction -1).
# Years: 1975 (pre, <= sample_end 1976), 1978 (gap), 1981 and 1982 (post, > 1980).
DATES = ["1975-01-31", "1978-01-31", "1981-01-31", "1982-01-31"]
PF3 = {"be_me": [0.05, 0.50, 0.03, 0.01], "ni_me": [0.90, 0.90, 0.90, 0.90]}
PF1 = {"be_me": [0.00, 0.00, 0.00, 0.00], "ni_me": [0.02, 0.02, 0.04, 0.00]}
MKT = [0.01, 0.10, 0.01, 0.02]


def write(base):
    for sub, w in (("pf_ew", "ew"), ("pf_vw", "vw_cap")):
        os.makedirs(os.path.join(base, sub))
        with open(os.path.join(base, sub, f"[usa]_[all_factors]_[monthly]_[{w}].csv"), "w") as f:
            f.write("location,name,pf,n,freq,weighting,date,ret\n")
            for name in ("be_me", "ni_me"):
                for i, d in enumerate(DATES):
                    f.write(f"usa,{name},1.0,10,monthly,{w},{d},{PF1[name][i]}\n")
                    f.write(f"usa,{name},2.0,10,monthly,{w},{d},0.0\n")
                    f.write(f"usa,{name},3.0,10,monthly,{w},{d},{PF3[name][i]}\n")
    os.makedirs(os.path.join(base, "ls_vw"))
    with open(os.path.join(base, "ls_vw", "[usa]_[all_factors]_[monthly]_[vw_cap].csv"), "w") as f:
        f.write("location,name,freq,weighting,direction,n_stocks,n_stocks_min,date,ret\n")
        for name, dr in (("be_me", 1), ("ni_me", -1)):
            for d in DATES:
                f.write(f"usa,{name},monthly,vw_cap,{dr},20,5,{d},0.001\n")
    os.makedirs(os.path.join(base, "mkt"))
    with open(os.path.join(base, "mkt", "[usa]_[mkt]_[monthly]_[vw_cap].csv"), "w") as f:
        f.write("location,name,freq,weighting,direction,n_stocks,n_stocks_min,date,ret\n")
        for d, m in zip(DATES, MKT):
            f.write(f"usa,mkt,monthly,vw_cap,na,100,na,{d},{m}\n")
    doc = os.path.join(base, "SignalDoc.csv")
    with open(doc, "w") as f:
        f.write("Acronym,Authors,Year,Journal,SampleStartYear,SampleEndYear,Return,T-Stat,LongDescription\n")
        f.write("BM,Stattman,1980,J,1962,1976,,,book to market\n")
        f.write("EP,Basu,1980,J,1962,1976,0.58,,earnings to price\n")
    return doc


def main():
    base = tempfile.mkdtemp()
    doc = write(base)
    c = sqlite3.connect(":memory:")
    ps.init(c)
    n = ps.load_jkp(c, base)
    check("pf, ls and mkt rows stored", n["pf"] == 2 * 2 * 3 * 4 and n["ls"] == 8 and n["mkt"] == 4, n)
    ps.load_osap_doc(c, doc)
    yr = c.execute("SELECT year, sample_end, direction FROM published_signals WHERE source='jkp' AND signal='be_me'"
                   ).fetchone()
    check("OSAP paper year attached to the mapped JKP factor", yr == (1980, 1976, 1), yr)
    rows = {(r["family"], r["weighting"], r["period"]): r for r in ps.evidence(c)}
    vb = rows.get(("value_book", "ew", "post"))
    check("post = years after publication, gap year excluded", vb is not None and vb["months"] == 2, vb)
    want = ((0.03 - 0.01) + (0.01 - 0.02)) / 2                       # direction +1 -> pf3
    check("direction +1: long leg is pf3; mean excess by hand", vb and abs(vb["mean_excess"] - want) < 1e-12, vb)
    pre = rows.get(("value_book", "ew", "pre"))
    check("pre = years up to the sample end", pre and pre["months"] == 1 and abs(pre["mean_excess"] - 0.04) < 1e-12,
          pre)
    allp = rows.get(("value_book", "ew", "all"))
    check("all = pre + post (gap excluded)", allp and allp["months"] == 3, allp)
    ey = rows.get(("earnings_yield", "ew", "post"))
    want = ((0.04 - 0.01) + (0.00 - 0.02)) / 2                       # direction -1 -> pf1
    check("direction -1: long leg is pf1", ey and abs(ey["mean_excess"] - want) < 1e-12, ey)
    ex = [0.04 - 0.01, 0.00 - 0.02]
    m = sum(ex) / 2
    sd = math.sqrt(sum((x - m) ** 2 for x in ex) / 1)
    check("t-stat = mean / (sd / sqrt(n))", ey and abs(ey["tstat_excess"] - m / (sd / math.sqrt(2))) < 1e-9, ey)
    text = ps.render(list(rows.values()))
    check("report shows the publication year and weighting", "1980" in text and "vw_cap" in text, text[:300])
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
