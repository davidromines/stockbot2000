"""predict_service (Stage AD5): the model ladder keeps the simplest rung that works, frozen models are content-hashed and
never overwritten, forecasts are written before outcomes with an abstain flag, and calibration reads only passed
horizons. A synthetic market in which book_to_market carries real information."""
import runtime  # noqa: F401
import sqlite3

import numpy as np
import pandas as pd

import alpha_bench as ab
import predict_service as ps

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

rng = np.random.default_rng(5)
ab.MIN_NAMES = 40
dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2019-01-01", periods=640)]
ab.DISCOVERY, ab.VALIDATION = (dates[260], dates[420]), (dates[421], dates[560])
N = 120
tick = [f"S{i:03d}" for i in range(N)]
q = rng.normal(0, 1, N)
c = sqlite3.connect(":memory:")
c.executescript("""CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT);
CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL);
CREATE TABLE daily_fundamentals (ticker TEXT, date TEXT, fcf_to_price REAL, earnings_yield REAL, book_to_market REAL,
  gross_profitability REAL, asset_growth REAL, accruals REAL);
CREATE TABLE daily_sue (ticker TEXT, date TEXT, sue REAL, sue_age REAL);
CREATE TABLE oos_predictions (ticker TEXT, date TEXT, fold INT, score REAL, label INT);""")
spy = 300.0
for d in dates:
    c.execute("INSERT INTO prices VALUES ('SPY',?,?,?,?,?,1)", (d, spy, spy, spy, spy))
    spy *= 1 + rng.normal(0.0003, 0.008)
P, F, FU, SU = [], [], [], []
for t, qq in zip(tick, q):
    c.execute("INSERT INTO symbols VALUES (?, 'common_stock', NULL)", (t,))
    px = 30.0
    for k, d in enumerate(dates):
        o = px
        px *= 1 + 0.0004 * qq + rng.normal(0, 0.015)
        P.append((t, d, o, px, px, px, 1)); F.append((t, d, 5e7))
        FU.append((t, d, rng.normal(), rng.normal(), float(qq) + rng.normal(0, 0.3), rng.normal(), rng.normal(), rng.normal()))
        SU.append((t, d, rng.normal(), float(k % 60)))
c.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", P)
c.executemany("INSERT INTO features VALUES (?,?,?)", F)
c.executemany("INSERT INTO daily_fundamentals VALUES (?,?,?,?,?,?,?,?)", FU)
c.executemany("INSERT INTO daily_sue VALUES (?,?,?,?)", SU)

res = ps.ladder(c)
m20 = res[20]
check("ridge finds the informative signal at h = 20 (validation IC well above the margin)", m20["ic_ridge"] > 0.05, m20["ic_ridge"])
check("...so ridge is the kept rung", m20["keep"] == "ridge")
check("the informative signal carries the largest positive coefficient",
      max(m20["coefs"], key=m20["coefs"].get) in ("book_to_market", "mom_12_1", "mom_9_1"), m20["coefs"])
check("no XGBoost scores on these rows: its rung is reported as unavailable, not as zero", m20["xgb_dates"] == 0
      and m20["ic_xgb"] != m20["ic_xgb"])
v = ps.freeze(c, res)
check("kept models are frozen under a content hash", v and all(x.startswith("ridge-h") for x in v), v)
check("freezing again does not duplicate or overwrite", ps.freeze(c, res) == v
      and c.execute("SELECT COUNT(*) FROM prediction_models").fetchone()[0] == len(v))
n = ps.score(c)
log = pd.read_sql("SELECT * FROM prediction_log", c)
check("today's forecasts are written for every frozen model", n > 0 and set(log.model_version) == set(v), n)
check("forecasts are dated on the newest session (before any outcome exists)", set(log.date) == {dates[-1]})
check("P(up) is a probability and q10 sits below the expectation",
      log.p_up.between(0, 1).all() and (log.q10 <= log.expected_excess + 1e-12).all())
check("expected net = expected excess less the modelled round trip", (log.expected_net < log.expected_excess).all())
check("abstention is a first-class decision (some names abstain)", log.abstain.isin([0, 1]).all() and log.abstain.sum() > 0)
check("a second score the same day writes nothing new", ps.score(c) == n
      and c.execute("SELECT COUNT(*) FROM prediction_log").fetchone()[0] == len(log))
# calibration only reads forecasts whose horizon has passed
c.execute("INSERT INTO prediction_log (at, date, ticker, horizon, model_version, expected_excess, expected_net, p_up, q10, "
          "abstain) VALUES ('x', ?, 'S000', 5, 'ridge-h5-test', 0.01, 0.009, 0.6, -0.02, 0)", (dates[500],))
cal = ps.calibration(c)
check("calibration uses passed horizons only", len(cal) >= 1 and int(cal["n"].sum()) == 1, cal)
check("the report renders", "Prediction ladder" in ps.render(res, v))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
