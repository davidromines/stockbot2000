"""timing_shadow: the live-model timing dial in shadow — logging, scaling, the pre-registered evaluation, registration."""
import runtime  # noqa: F401
import os
import sqlite3
import tempfile

import numpy as np
import pandas as pd

import storage
import timing_shadow as ts

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

import xgboost as xgb
rng = np.random.default_rng(2)
X = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400)})
y = (X["a"] + rng.normal(0, 0.5, 400) > 0).astype(int)
m = xgb.XGBClassifier(n_estimators=10, max_depth=2)
m.fit(X, y)
path = os.path.join(tempfile.mkdtemp(), "m.json")
m.save_model(path)
cfg = {"model": {"path": path}, "universe": {"tradeable_types": ["common_stock"]}, "scoresheet": {},
       "risk": {"min_price": 5, "min_dollar_volume": 1e6}}

c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
c.execute("CREATE TABLE features (ticker TEXT, date TEXT, a REAL, b REAL, dollar_volume_20 REAL)")
c.execute("CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT)")
days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-06-01", periods=160)]
spy = 500.0
for d in days:
    c.execute("INSERT INTO prices VALUES ('SPY',?,?,?,?,?,1)", (d, spy, spy, spy, spy))
    spy *= 1.001
for k in range(120):
    t = f"T{k}"
    c.execute("INSERT INTO symbols VALUES (?, 'common_stock', NULL)", (t,))
    for i, d in enumerate(days[-30:]):
        c.execute("INSERT INTO prices VALUES (?,?,20,20,20,20,1)", (t, d))
        c.execute("INSERT INTO features VALUES (?,?,?,?,5e7)", (t, d, rng.normal() + (0.5 if i % 2 else -0.5), rng.normal()))
ts.init(c)
n = ts.baseline(c, cfg, sessions=25)
check("the baseline scores past sessions once (scaling only)", n == 25 and ts.baseline(c, cfg, sessions=25) == 0, n)
check("baseline rows are labelled baseline, never prospective",
      c.execute("SELECT COUNT(*) FROM timing_shadow WHERE kind='baseline'").fetchone()[0] == 25)
lf = pd.read_sql(f"SELECT ticker, date, a, b FROM features WHERE date='{days[-1]}'", c)
storage.load_latest_features = lambda *a, **k: lf
t = ts.log(c, cfg)
check("today's mean probability is logged prospectively with a z-score and a suggested exposure",
      t["date"] == days[-1] and t["z"] is not None and t["exposure"] in ("full", "half"), t)
check("logging twice the same day writes once", (ts.log(c, cfg) or True)
      and c.execute("SELECT COUNT(*) FROM timing_shadow WHERE kind='prospective'").fetchone()[0] == 1)
old_lf = pd.read_sql(f"SELECT ticker, '2026-10-16' AS date, a, b FROM features WHERE date='{days[-1]}'", c)
storage.load_latest_features = lambda *a, **k: old_lf
ts.log(c, cfg)
check("a feature date before the registered start is logged as baseline, never prospective",
      c.execute("SELECT kind FROM timing_shadow WHERE date='2026-10-16'").fetchone()[0] == "baseline")
ev = ts.evaluate(c)
check("before the sample the call is INTERIM", ev["call"] == "INTERIM" and ev["need"] == 120, ev)
# a planted series that leads SPY: evaluation finds it
c2 = sqlite3.connect(":memory:")
c2.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
ts.init(c2)
d2 = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=200)]
r = rng.normal(0, 0.01, 200)
px = 500 * np.cumprod(1 + r)
for d, p in zip(d2, px):
    c2.execute("INSERT INTO prices VALUES ('SPY',?,?,?,?,?,1)", (d, p, p, p, p))
for i, d in enumerate(d2[:-22]):
    f = px[i + 21] / px[i + 1] - 1
    c2.execute("INSERT INTO timing_shadow VALUES (?,?,?,?,?,?,?,?)", (d, "x", "h", 100, 0.5, f * 50, "full" if f > 0 else "half", "prospective"))
ev2 = ts.evaluate(c2)
check("a z that leads the market passes at the fixed sample", ev2["with_outcome"] >= 120 and ev2["corr"] > 0.9
      and ev2["call"].startswith("PASS"), ev2)
c3 = sqlite3.connect(":memory:")
c3.row_factory = sqlite3.Row
e = ts.register(c3, cfg)
check("the rule is registered and locked, with the model's hash", e["status"] == "REGISTERED" and ts.model_hash(cfg) in e["spec"])

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
