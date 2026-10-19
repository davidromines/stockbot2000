"""external_benchmark (Stage AD8): tercile construction, month alignment, the spread comparison and its verdict."""
import runtime  # noqa: F401
import sqlite3

import numpy as np
import pandas as pd

import external_benchmark as eb

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

rng = np.random.default_rng(7)
c = sqlite3.connect(":memory:")
c.executescript("""CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT);
CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL);
CREATE TABLE daily_fundamentals (ticker TEXT, date TEXT, book_to_market REAL);
CREATE TABLE published_returns (source TEXT, signal TEXT, leg TEXT, weighting TEXT, date TEXT, ret REAL, n INT);""")
months = pd.period_range("2009-01", "2011-12", freq="M")
ends = [(m.to_timestamp(how="end") - pd.Timedelta(days=2)).strftime("%Y-%m-%d") for m in months]   # a weekday-ish month end
for d in ends:
    c.execute("INSERT INTO prices VALUES ('SPY',?,1,1,1,1,1)", (d,))
tick = [f"T{i:03d}" for i in range(90)]
quality = rng.normal(0, 1, len(tick))          # persistent: drives both the past and the future return
for t, q in zip(tick, quality):
    c.execute("INSERT INTO symbols VALUES (?, 'common_stock', NULL)", (t,))
    px = 20.0
    for d in ends:
        c.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,1)", (t, d, px, px, px, px))
        c.execute("INSERT INTO features VALUES (?,?,5e7)", (t, d))
        c.execute("INSERT INTO daily_fundamentals VALUES (?,?,?)", (t, d, float(q)))
        px *= 1 + 0.01 * q + rng.normal(0, 0.02)
c.execute("INSERT INTO symbols VALUES ('BAD', 'common_stock', 'price_anomaly')")
for d in ends:
    c.execute("INSERT INTO prices VALUES ('BAD',?,1e9,1e9,1e9,1e9,1)", (d,))

dates = eb.month_ends(c, "2009-01-01", "2011-12-31")
check("one date per month, the last in each", len(dates) == 36 and dates[0] == ends[0], dates[:2])
panel = eb.attach_bm(c, eb.load_month_end_panel(c, dates), dates)
check("flagged price anomalies and non-common stock are excluded", "BAD" not in set(panel.ticker) and "SPY" not in set(panel.ticker))
p = eb.signals(panel)
row = p[(p.ticker == "T000")].iloc[13]
check("ret_12_1 = price 1 month ago / 12 months ago - 1", abs(row.ret_12_1 - (row.lag1 / row.lag12 - 1)) < 1e-12)
ours = eb.terciles(p, "ret_12_1")
check("terciles start once 12 months of history exist", len(ours) == 36 - 12 - 1, len(ours))
check("persistent quality: the top momentum tercile beats the bottom on average", ours.spread.mean() > 0, ours.spread.mean())
check("the return is dated in the month after formation", ours["month"].iloc[0] == pd.Period(dates[12][:7], "M") + 1)
# publish our own series as "JKP" -> a faithful replication must say so
for r in ours.itertuples():
    me = r.month.to_timestamp(how="end").strftime("%Y-%m-%d")
    c.execute("INSERT INTO published_returns VALUES ('jkp','ret_12_1','pf1','ew',?,?,100)", (me, r.pf1))
    c.execute("INSERT INTO published_returns VALUES ('jkp','ret_12_1','pf3','ew',?,?,100)", (me, r.pf3))
cmp_ = eb.compare(ours, eb.published(c, "ret_12_1"))
check("identical series: spread correlation 1 and verdict faithful", abs(cmp_["corr_spread"] - 1) < 1e-9
      and cmp_["verdict"] == "faithful", cmp_)
noise = ours.copy(); noise["spread"] = rng.normal(0, 0.01, len(noise)); noise["pf3"] = noise["pf1"] + noise["spread"]
check("an unrelated spread is called out", eb.compare(noise, eb.published(c, "ret_12_1"))["verdict"] != "faithful")
check("fewer than 12 overlapping months: no verdict", "verdict" not in eb.compare(ours.iloc[:5], eb.published(c, "ret_12_1")))
bm = eb.terciles(p, "be_me")
check("book-to-market terciles use the point-in-time column", len(bm) > 0 and bm.spread.mean() > 0)
check("report renders", "corr spread" in eb.render({"ret_12_1": {**cmp_, "avg_names": 90}}, "2010-01", "2011-12"))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
