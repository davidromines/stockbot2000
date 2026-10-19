"""earnings_study (Stage AD3.5): event timing (after-close announcements move a session), the control window, the
pre-stated reading. Synthetic stocks whose announcements move the price far more than ordinary days."""
import runtime  # noqa: F401
import sqlite3

import numpy as np
import pandas as pd

import earnings_study as es

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

rng = np.random.default_rng(3)
days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2016-01-04", periods=900)]
c = sqlite3.connect(":memory:")
c.executescript("""CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL);
CREATE TABLE edgar_events (adsh TEXT, cik INT, ticker TEXT, form TEXT, item TEXT, filed TEXT, accepted TEXT);""")
for d in days:
    c.execute("INSERT INTO prices VALUES ('SPY',?,100,100,100,100,1)", (d,))
ev_idx = list(range(80, 880, 63))                              # a report each quarter
for t in ("AAA", "BBB", "CCC"):
    px, rows = 50.0, []
    for k, d in enumerate(days):
        rows.append((t, d, px, px, px, px, 1))
        px *= 1 + rng.normal(0, 0.005) + (rng.normal(0, 0.08) if k in ev_idx else 0)   # announcements: big moves
    c.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", rows)
    c.executemany("INSERT INTO features VALUES (?,?,5e7)", [(t, d) for d in days])
    for k in ev_idx:
        # announced before the open of session k (09:00 ET = 13:00/14:00 UTC): the move shows in session k's prices
        c.execute("INSERT INTO edgar_events VALUES ('x',1,?,'8-K','2.02',?,?)", (t, days[k], days[k] + "T13:00:00.000Z"))
        c.execute("INSERT INTO edgar_events VALUES ('x',1,?,'8-K','7.01',?,?)", (t, days[k], days[k] + "T13:00:00.000Z"))
ev = es.events(c, "2016-01-01", "2019-12-31")
check("one event per 2.02 filing (other items ignored)", len(ev) == 3 * len(ev_idx), len(ev))
check("a 13:00 UTC acceptance is a before-the-close announcement", not ev["after_close"].any())
spy, opens, dvs = es.load(c, ["AAA", "BBB", "CCC"], days[0], days[-1])
w = es.windows(c, ev, spy, opens, dvs)
check("windows are measured for most events (the first is too early for a control)", len(w) >= 3 * (len(ev_idx) - 2), len(w))
s = es.summarize(w)
check("announcement windows are far more dispersed than controls", s["sd_event"] > 3 * s["sd_control"], s)
check("with no reward for that risk, the pre-stated reading supports testing a skip rule", s["supports_skip_rule"] is True)
late = pd.DataFrame({"ticker": ["AAA"], "day": [days[200]], "after_close": [True]})
early = pd.DataFrame({"ticker": ["AAA"], "day": [days[200]], "after_close": [False]})
wl, we = es.windows(c, late, spy, opens, dvs), es.windows(c, early, spy, opens, dvs)
check("an after-close announcement starts one session later", wl.iloc[0]["day"] == days[201] and we.iloc[0]["day"] == days[200],
      (wl, we))
blocked = pd.DataFrame({"ticker": ["AAA", "AAA"], "day": [days[ev_idx[2]], days[ev_idx[2] - 12]], "after_close": [False, False]})
check("a control window that contains another announcement is not used",
      days[ev_idx[2]] not in set(es.windows(c, blocked, spy, opens, dvs)["day"]))
check("the report renders", "Earnings-date study" in es.render(s))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
