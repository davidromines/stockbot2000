"""earnings_call_test: the release is the latest 8-K reaction session within 45 sessions before the surprise; features
are taken no later than the buy date and a previous surprise counts only if it was known by then; the selection cut
comes from the training years only; the call is delta 0.70-0.80, 20-75 days, tight, expiring after the exit; the spot
is read by put-call parity from stored quotes; the pass rule."""
import runtime  # noqa: F401
import sqlite3

import numpy as np
import pandas as pd

import earnings_call_test as ect

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)


sessions = np.array(pd.bdate_range("2023-01-02", "2023-12-29").strftime("%Y-%m-%d"), dtype=str)
pos = {d: i for i, d in enumerate(sessions)}
ev = pd.DataFrame({"ticker": ["AAA", "AAA", "BBB"], "sue_date": ["2023-05-10", "2023-08-10", "2023-05-10"],
                   "sue": [1.0, -0.5, 0.3], "prev_sue": [np.nan, 1.0, 0.2], "prev_date": [None, "2023-05-10", "2023-03-01"],
                   "prev2_sue": [np.nan, np.nan, np.nan], "prev2_date": [None, None, None]})
rep = {"AAA": np.array([pos["2023-04-27"], pos["2023-07-27"]]), "BBB": np.array([pos["2023-01-05"]])}
e2 = ect.attach_release(ev, rep, sessions)
check("the release is the latest 8-K reaction session before the surprise (AAA 04-27, 07-27)",
      list(e2["R"][:2]) == [pos["2023-04-27"], pos["2023-07-27"]], list(e2["R"]))
check("a release more than 45 sessions before the surprise is not this quarter's: no trade (BBB)", e2["R"].iloc[2] == -1)

A = ect.as_of_dates(e2, sessions)
check("as-of = the earlier of the buy date and 60 days before the filing (03-11, 06-11)",
      A.tolist()[:2] == ["2023-03-11", "2023-06-11"], A.tolist())
check("as-of never falls after the buy date", all(a <= str(sessions[r - 5]) for a, r in zip(A[:2], e2["R"][:2])))
check("with no release, as-of = 60 days before the filing", A.iloc[2] == "2023-03-11", A.iloc[2])

# a previous surprise counts only if it was known by the as-of date
late = pd.DataFrame({"ticker": ["CCC"], "sue_date": ["2023-05-10"], "sue": [0.4], "prev_sue": [2.0],
                     "prev_date": ["2023-04-01"], "prev2_sue": [np.nan], "prev2_date": [None], "R": [-1]})
evk = pd.concat([e2, late], ignore_index=True)
Ak = ect.as_of_dates(evk, sessions)
known = ect.prev_known(evk, Ak)[0]
check("a previous surprise filed before the as-of date counts (AAA 05-10 by 06-11; BBB 03-01 by 03-11)",
      known[1] == 1.0 and known[2] == 0.2, known)
check("one filed AFTER the as-of date is not used (CCC 04-01 > 03-11): no look-ahead", np.isnan(known[3]), known)

# walk-forward: the selection cut comes from training years only
rng = np.random.default_rng(0)
n = 2000
years = rng.choice([2017, 2018, 2019, 2020], n)
evw = pd.DataFrame({"ticker": "T", "sue_date": [f"{y}-06-01" for y in years], "sue": rng.normal(0, 1, n)})
Xw = pd.DataFrame({f: rng.normal(0, 1, n) for f in ect.FEATURES}, index=evw.index)
Xw["prev_sue"] = evw["sue"] * 0.8 + rng.normal(0, 0.6, n)          # informative: a high last surprise -> a beat
out = ect.walk_forward(evw, Xw)
te = out["sue_date"].str[:4] == "2020"
check("only the test year (2020 on) is scored", out.loc[~te, "p_model"].isna().all() and out.loc[te, "p_model"].notna().all())
check("about a fifth is selected (cut from the training predictions)", 0.10 < out.loc[te, "sel_model"].mean() < 0.35,
      out.loc[te, "sel_model"].mean())
check("the selected beat more often than the rest (the model learned the signal)",
      (out.loc[te & out["sel_model"], "sue"] > 0).mean() > (out.loc[te & ~out["sel_model"], "sue"] > 0).mean() + 0.2)

# the call and the spot, from stored quotes
c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE option_quotes (date TEXT, symbol TEXT, expiration TEXT, strike REAL, cp TEXT, bid REAL, ask REAL, "
          "iv REAL, delta REAL)")
rows = [("2023-04-20", "AAA", "2023-05-19", 90, "C", 11.9, 12.1, 0.3, 0.76),   # good: 29 days, gap 1.7%, delta .76
        ("2023-04-20", "AAA", "2023-04-28", 90, "C", 11.0, 11.2, 0.3, 0.75),   # expires before the exit
        ("2023-04-20", "AAA", "2023-05-19", 95, "C", 7.0, 8.0, 0.3, 0.72),     # gap 13%
        ("2023-04-20", "AAA", "2023-05-19", 80, "C", 21.0, 21.2, 0.3, 0.90),   # too deep
        ("2023-04-20", "AAA", "2023-05-19", 100, "C", 3.0, 3.1, 0.3, 0.45),
        ("2023-04-20", "AAA", "2023-05-19", 100, "P", 2.9, 3.1, 0.3, -0.5)]    # call - put at 100 = +0.05 -> spot 100.05
c.executemany("INSERT INTO option_quotes VALUES (?,?,?,?,?,?,?,?,?)", rows)
pick = ect.pick_call(c, "AAA", "2023-04-20", "2023-05-01")
check("the call: delta 0.70-0.80, 20-75 days, gap <= 5%, expiring after the exit", pick == ("2023-05-19", 90, 12.1, 0.76), pick)
check("the spot by put-call parity from stored quotes (100 + 3.05 - 3.0 = 100.05)",
      abs(ect.local_spot(c, "AAA", "2023-04-20") - 100.05) < 1e-9)

# features: as of A from the company's own history, never a later value
cf = sqlite3.connect(":memory:")
cf.execute("CREATE TABLE daily_fundamentals (ticker TEXT, date TEXT, " + ", ".join(f"{x} REAL" for x in ect.FUND) + ")")
cf.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
for d_, v in (("2023-01-03", 1.0), ("2023-03-01", 2.0), ("2023-05-01", 3.0)):          # a new filing each time
    cf.execute("INSERT INTO daily_fundamentals VALUES (?,?," + ",".join("?" * len(ect.FUND)) + ")", ("AAA", d_, *[v] * len(ect.FUND)))
for i, d_ in enumerate(pd.bdate_range("2022-01-03", "2023-06-30").strftime("%Y-%m-%d")):
    cf.execute("INSERT INTO prices VALUES ('AAA', ?, ?)", (d_, 100.0 + i))
evf = pd.DataFrame({"ticker": ["AAA", "AAA"], "prev_sue": [0.5, 0.5], "prev_date": ["2023-01-01"] * 2,
                    "prev2_sue": [np.nan] * 2, "prev2_date": [None] * 2})
Xf = ect.features(cf, evf, pd.Series(["2023-04-15", "2023-02-15"]))
check("fundamentals as of A: 04-15 sees the 03-01 filing (2.0), 02-15 sees 01-03 (1.0), never 05-01",
      list(Xf["roa"]) == [2.0, 1.0], list(Xf["roa"]))
check("the 120-session momentum is computed to A only", Xf["mom120"].iloc[1] < Xf["mom120"].iloc[0] + 1 and
      Xf["mom120"].notna().all(), list(Xf["mom120"]))

# the pass rule
days = pd.bdate_range("2020-01-02", "2026-06-30").strftime("%Y-%m-%d")
sp = days[np.linspace(0, len(days) - 1, 400).astype(int)]
T = pd.DataFrame({"report": sp, "ret": 0.12 + rng.normal(0, 0.4, 400), "stock_ret": 0.01, "stock_lev_ret": 0.04,
                  "contract_usd": 3000.0, "beat": True, "missing_exit": False})
s = ect.stats(T)
check("a steady +12% a trade, better than the leveraged stock, passes", s["pass"], s)
check("the same returns but worse than the leveraged stock do not pass", not ect.stats(T.assign(stock_lev_ret=0.5))["pass"])
check("trades without an exit quote are not counted", ect.stats(T.assign(missing_exit=True))["n"] == 0)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
