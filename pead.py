"""
Post-earnings announcement drift, sorted by surprise. Ball & Brown (1968).

The earlier 8-K study pooled all 26,812 earnings events and found +0.08% drift at
21 days — which looks like a refutation and is actually a null construction. PEAD
is a statement about *surprise*, not about earnings. Pooling beats and misses
cancels them by design; the effect can only appear once the events are sorted.

Surprise here is the standardised unexpected earnings (SUE) that the literature
uses: this quarter's year-on-year change in earnings, divided by the volatility
of that change. Scaling by its own volatility is what makes a $0.02 beat at a
steady utility comparable to a $0.02 beat at a biotech.

Entry is the next session's close after the filing was ACCEPTED, so the overnight
reaction is excluded and any measured drift understates the truth. Returns are
against each stock's own median forward return, not against the index, because
benchmarking a sample of filers against a cap-weighted index measures the size
effect and calls it news.

Usage:
    python pead.py --measure
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pead")


def build_sue(conn) -> pd.DataFrame:
    """
    Standardised unexpected earnings per filing.

    SUE = (this quarter's EPS - the same quarter a year ago) / stdev of that
    change over the company's history. A seasonal-random-walk expectation, which
    is the standard construction and needs no analyst estimates — we have none,
    and buying them would introduce a different look-ahead problem entirely.
    """
    df = pd.read_sql_query("""
        SELECT f.ticker, f.filed, f.adsh, n.value AS eps
        FROM sec_filings f
        JOIN sec_facts n ON n.adsh = f.adsh AND n.tag = 'EarningsPerShareBasic'
        WHERE f.ticker IS NOT NULL AND f.form IN ('10-Q','10-K') AND n.qtrs = 1
        ORDER BY f.ticker, f.filed""", conn)
    if df.empty:
        raise SystemExit("No EPS facts — has sec_fundamentals.py been loaded?")
    df = df.drop_duplicates(subset=["ticker", "filed"], keep="last")
    out = []
    for t, g in df.groupby("ticker", observed=True):
        if len(g) < 8:
            continue
        g = g.sort_values("filed").copy()
        # Year-on-year change: four quarters back, per the seasonal random walk.
        g["delta"] = g["eps"] - g["eps"].shift(4)
        sd = g["delta"].expanding(min_periods=4).std()
        g["sue"] = g["delta"] / sd.replace(0, np.nan)
        out.append(g.dropna(subset=["sue"]))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def measure(conn, horizons=(1, 5, 21, 63)) -> None:
    sue = build_sue(conn)
    log.info(f"{len(sue):,} earnings events with a computable surprise")

    # Acceptance timestamps, so entry is the session after the market could see it.
    acc = pd.read_sql_query(
        "SELECT adsh, accepted FROM edgar_events WHERE item='2.02' AND accepted!=''", conn)
    acc = acc.drop_duplicates("adsh")
    sue = sue.merge(acc, on="adsh", how="left")
    sue["asof"] = np.where(sue["accepted"].notna(),
                           sue["accepted"].astype(str).str[:10],
                           pd.to_datetime(sue["filed"], format="%Y%m%d",
                                          errors="coerce").astype(str).str[:10])
    sue = sue.dropna(subset=["asof"])

    cal = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM prices WHERE date>='2010-01-01' ORDER BY date")]
    calarr = np.array(cal)

    px_cache, base_cache, rows = {}, {}, []
    for r in sue.itertuples(index=False):
        t = str(r.ticker)
        if t not in px_cache:
            px_cache[t] = dict(conn.execute(
                "SELECT date, close FROM prices WHERE ticker=? AND close>0 "
                "AND date>='2010-01-01'", (t,)))
            arr = np.array([px_cache[t][d] for d in cal if d in px_cache[t]], dtype="float64")
            base_cache[t] = {}
            for h in horizons:
                if len(arr) > h + 20:
                    f = arr[h:] / arr[:-h] - 1.0
                    f = f[np.isfinite(f) & (np.abs(f) < 5)]
                    base_cache[t][h] = float(np.median(f)) if f.size else None
                else:
                    base_cache[t][h] = None
        px, base = px_cache[t], base_cache[t]
        if not px:
            continue
        j = int(np.searchsorted(calarr, r.asof, side="right"))
        if j >= len(cal) or cal[j] not in px:
            continue
        p0 = px[cal[j]]
        rec = {"sue": float(r.sue)}
        ok = False
        for h in horizons:
            k = j + h
            if k < len(cal) and cal[k] in px and base.get(h) is not None:
                ex = (px[cal[k]] / p0 - 1) - base[h]
                if abs(ex) < 5:
                    rec[h] = ex; ok = True
        if ok:
            rows.append(rec)

    d = pd.DataFrame(rows)
    if d.empty:
        raise SystemExit("No measurable events.")
    d["decile"] = pd.qcut(d["sue"], 10, labels=False, duplicates="drop")

    print(f"\n  POST-EARNINGS ANNOUNCEMENT DRIFT — {len(d):,} events sorted by surprise")
    print(f"  Excess over each stock's own norm. Entry is the session AFTER acceptance,")
    print(f"  so the overnight reaction is excluded and the drift is understated.\n")
    print(f"  {'SUE decile':<14}{'n':>8}" + "".join(f"{'+'+str(h)+'d':>10}" for h in horizons))
    print("  " + "-" * 66)
    for dec in sorted(d["decile"].dropna().unique()):
        s = d[d["decile"] == dec]
        cells = "".join(f"{s[h].median():>+10.2%}" if h in s else f"{'—':>10}" for h in horizons)
        lab = "1 (worst)" if dec == 0 else ("10 (best)" if dec == 9 else str(int(dec) + 1))
        print(f"  {lab:<14}{len(s):>8,}{cells}")

    top, bot = d[d["decile"] == 9], d[d["decile"] == 0]
    print("  " + "-" * 66)
    spread = "".join(f"{top[h].median()-bot[h].median():>+10.2%}"
                     if h in top and h in bot else f"{'—':>10}" for h in horizons)
    print(f"  {'10 minus 1':<14}{'':>8}{spread}")
    print("\n  The spread is the whole test. A monotone rise across deciles and a")
    print("  positive top-minus-bottom is PEAD; a flat table means the surprise is")
    print("  fully priced by the next close, which is what an efficient market does.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--measure", action="store_true")
    ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    measure(conn)
    conn.close()


if __name__ == "__main__":
    main()
