"""prospective_eval: the registered rule, applied to synthetic samples (no database)."""
import runtime  # noqa: F401
import numpy as np
import pandas as pd
import prospective_eval as pe

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

rng = np.random.default_rng(1)
dates = [f"2026-11-{d:02d}" for d in range(1, 21)]
fams = ["good", "noise"]
rows = []
for d in dates:
    for f, mu in (("good", 3.0), ("noise", 0.0)):
        for _ in range(4):
            x = rng.normal(mu, 1.0)
            rows.append({"family": f, "entry_date": d, "net_pct": x + 0.5, "excess_pct": x, "is_open": 0})
df = pd.DataFrame(rows)
t = pe.decide(df, fams).set_index("family")
check("a real +3% family passes", bool(t.loc["good", "pass"]))
check("a zero-mean family does not pass", not bool(t.loc["noise", "pass"]))
few = df[df["entry_date"].isin(dates[:5])]
t2 = pe.decide(few, fams).set_index("family")
check("fewer than 12 own dates cannot pass", not bool(t2.loc["good", "pass"]) and "too few own dates" in t2.loc["good", "why"])
neg = df.copy(); neg["excess_pct"] -= 5.0
check("negative excess over SPY never passes", not pe.decide(neg, fams)["pass"].any())
sess = [f"2026-11-{d:02d}" for d in range(1, 29)]
first, ev = pe.window(df, sess)
check("window = first 20 pooled dates, evaluation 15 sessions later (none stored yet)", len(first) == 20 and ev is None)
sess2 = sess + [f"2026-12-{d:02d}" for d in range(1, 20)]
first, ev = pe.window(df, sess2)
check("evaluation date is 15 sessions after the 20th date", ev == sess2[sess2.index(dates[-1]) + 15])
check("empty family reports no trades, not a pass", not pe.decide(df[df.family == "good"], fams).set_index("family").loc["noise", "pass"])
print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
