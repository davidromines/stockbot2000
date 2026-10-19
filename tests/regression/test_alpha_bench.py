"""alpha_bench (Stage AD4): registry, point-in-time cross sections, IC / basket / incremental value, the status rule, Holm,
the timing dial and the one-look guard. A synthetic market where ONE signal (book_to_market) carries real information."""
import runtime  # noqa: F401
import sqlite3

import numpy as np
import pandas as pd

import alpha_bench as ab

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

rng = np.random.default_rng(11)
ab.MIN_NAMES, ab.TOP_K = 40, 10
dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2019-01-01", periods=640)]
ab.DISCOVERY = (dates[260], dates[420])
ab.VALIDATION = (dates[421], dates[560])
N = 120
tick = [f"S{i:03d}" for i in range(N)]
q = rng.normal(0, 1, N)                                 # persistent: book_to_market carries it, nothing else does
c = sqlite3.connect(":memory:")
c.executescript("""CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT);
CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL);
CREATE TABLE daily_fundamentals (ticker TEXT, date TEXT, fcf_to_price REAL, earnings_yield REAL, book_to_market REAL,
  gross_profitability REAL, asset_growth REAL, accruals REAL);
CREATE TABLE daily_sue (ticker TEXT, date TEXT, sue REAL, sue_age REAL);
CREATE TABLE oos_predictions (ticker TEXT, date TEXT, fold INT, score REAL, label INT);""")
spy = 300.0
for k, d in enumerate(dates):
    c.execute("INSERT INTO prices VALUES ('SPY',?,?,?,?,?,1)", (d, spy, spy, spy, spy))
    spy *= 1 + 0.0003 + rng.normal(0, 0.008)
rows_p, rows_f, rows_fu, rows_s = [], [], [], []
for t, qq in zip(tick, q):
    c.execute("INSERT INTO symbols VALUES (?, 'common_stock', NULL)", (t,))
    px = 30.0
    for k, d in enumerate(dates):
        o = px
        px *= 1 + 0.0004 * qq + rng.normal(0, 0.015)
        rows_p.append((t, d, o, px, px, px, 1))
        rows_f.append((t, d, 5e7))
        rows_fu.append((t, d, rng.normal(), rng.normal(), float(qq) + rng.normal(0, 0.3), rng.normal(), rng.normal(), rng.normal()))
        rows_s.append((t, d, rng.normal(), float(k % 60)))
c.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", rows_p)
c.executemany("INSERT INTO features VALUES (?,?,?)", rows_f)
c.executemany("INSERT INTO daily_fundamentals VALUES (?,?,?,?,?,?,?,?)", rows_fu)
c.executemany("INSERT INTO daily_sue VALUES (?,?,?,?)", rows_s)
c.row_factory = sqlite3.Row

check("registry seeds twelve signals, once", ab.seed_registry(c) == 12 and ab.seed_registry(c) == 0)
orig = ab.SIGNALS[0]
ab.SIGNALS[0] = (orig[0], orig[1], orig[2] + " changed", orig[3])
try:
    ab.seed_registry(c); refused = False
except RuntimeError:
    refused = True
ab.SIGNALS[0] = orig
check("a changed definition under the same id is refused (needs a new signal_id)", refused)
regs = ab.register(c)
check("both experiments are pre-registered and locked", all(e["status"] == "REGISTERED" for e in regs) and len(regs) == 2)

c.row_factory = None
data = ab.load(c, ab.DISCOVERY[0], ab.VALIDATION[1])
check("wide matrices: one row per SPY session, one column per common stock", data["close"].shape == (640, N))
idx = ab.sample_dates(data["dates"], *ab.DISCOVERY, max(ab.HORIZONS))
check("formation every 5 sessions, after 252 sessions of history", idx[0] >= 252 and all(b - a == 5 for a, b in zip(idx, idx[1:])))
att = ab.attach(c, [data["dates"][i] for i in idx[:2]])
cs = ab.cross_section(data, att, idx[0], 20)
i = idx[0]
t0 = tick[0]
check("mom_12_1 uses only past closes", abs(cs.loc[t0, "mom_12_1"] - (data["close"].iloc[i - 21][t0] / data["close"].iloc[i - 252][t0] - 1)) < 1e-5)
exp_ex = (data["open"].iloc[i + 21][t0] / data["open"].iloc[i + 1][t0] - 1) - (
    data["spy"]["open"].iloc[i + 21] / data["spy"]["open"].iloc[i + 1] - 1)
check("the target is next open to next open, minus SPY over the same opens", abs(cs.loc[t0, "excess"] - exp_ex) < 1e-5)
check("sue_fresh keeps only SUE at most 20 sessions old", cs["sue_fresh"].notna().equals(cs["sue_age"] <= 20))

res = ab.bench(c, data=data, write_trials=True)
bm = res["signals"]["book_to_market"][20]
check("the informative signal has a positive IC in both windows", bm["discovery"]["ic"] > 0.05 and bm["validation"]["ic"] > 0.05, bm)
check("...a positive net basket", bm["validation"]["basket"] > 0)
check("...and adds information beyond the others (ablation)", bm["incremental_ic"] > 0)
noise_ic = [abs(res["signals"][s][20]["validation"]["ic"]) for s in ("earnings_yield", "gross_profitability", "neg_accruals")]
check("noise signals have ICs near zero", max(noise_ic) < 0.05, noise_ic)
check("Holm-adjusted p is never below the raw p", all(m["p_holm"] >= m["p"] - 1e-12 for by in res["signals"].values() for m in by.values()))
st = {m["status"] for by in res["signals"].values() for m in by.values()}
check("statuses come only from the pre-registered set", st <= {"VALIDATED", "REPLICATED", "NOT_SUPPORTED"}, st)
n = ab.trial_count(c)
check("every evaluation is appended to the trial ledger (12 signals x 3 horizons x 5 rows)", n == 12 * 3 * 5, n)
check("the registry carries each signal's best status", c.execute("SELECT COUNT(*) FROM alpha_signals WHERE status != 'DISCOVERED'").fetchone()[0] == 12)
check("a dependence map exists at h = 20", res["dependence"] is not None and res["dependence"]["value_corr"].shape == (12, 12))

# timing dial: plant an average score that leads SPY
sp = data["spy"]["open"].to_numpy()
fwd = np.r_[sp[21:] / sp[1:-20] - 1, np.full(21, np.nan)][:len(dates) - 1]
for k, d in enumerate(dates[:560]):
    s = 0.5 + (10 * fwd[k] if fwd[k] == fwd[k] else 0)
    c.execute("INSERT INTO oos_predictions VALUES ('X',?,?,?,0)", (d, 1 + k // 100, s))
td = ab.timing_dial(c)
check("a score that leads the market is detected by the timing test", td["corr"] > 0.5 and td["pass"], td)
check("the report renders", "Alpha bench" in ab.render(res, td, n) and "timing dial" in ab.render(res, td, n))
check("Newey-West t: zero for a zero-mean series, large for a constant positive one",
      abs(ab.nw_t(np.r_[np.ones(50), -np.ones(50)], 3)) < 1e-9 and ab.nw_t(np.ones(50) + rng.normal(0, 0.01, 50), 3) > 10)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
