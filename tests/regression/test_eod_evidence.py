"""eod_report evidence section (Stage AD9): the account against SPY today and since the start, and the progress of each
pre-registered test. Every line degrades alone; the section never raises."""
import runtime  # noqa: F401
import sqlite3

import eod_report as er

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
c.executescript("""CREATE TABLE live_equity (at TEXT, session TEXT, equity REAL, buying_power REAL);
CREATE TABLE minute_bars (ticker TEXT, ts TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
CREATE TABLE timing_shadow (date TEXT, at TEXT, model_hash TEXT, n INT, mean_score REAL, z REAL, exposure TEXT, kind TEXT);
CREATE TABLE paper_trades_restated (version TEXT, run_id TEXT, ticker TEXT, entry_date TEXT, net_pct REAL);""")
c.executemany("INSERT INTO live_equity VALUES (?,?,?,0)", [("2026-10-16T20:00:00", "2026-10-16", 80.0),
                                                           ("2026-10-19T14:00:00", "2026-10-19", 80.4),
                                                           ("2026-10-19T20:00:00", "2026-10-19", 80.8)])
c.executemany("INSERT INTO minute_bars VALUES ('SPY',?,?,?,?,?,1)", [("2026-10-19 09:30", 700, 700, 700, 700),
                                                                    ("2026-10-19 15:59", 703.5, 703.5, 703.5, 703.5)])
c.executemany("INSERT INTO timing_shadow VALUES (?,?,?,?,?,?,?,?)", [("2026-10-19", "x", "h", 1, 0.3, 0.1, "full", "prospective"),
                                                                    ("2026-09-01", "x", "h", 1, 0.3, None, None, "baseline")])
c.executemany("INSERT INTO paper_trades_restated VALUES ('v2','r','T',?,1.0)", [("2026-10-12",), ("2026-10-13",), ("2026-10-01",)])
c.commit()
check("SPY's move today comes from the collected minute bars", abs(er._spy_today(c, "2026-10-19") - 0.005) < 1e-12)
lines = er._section_evidence(c, "2026-10-19", "LIVE")
txt = " | ".join(lines)
check("today's account move is measured from the previous close, beside SPY", "today: account +1.00%, SPY +0.50%" in txt, txt)
check("the timing dial counts prospective sessions only", "timing dial (shadow): 1 of 120" in txt, txt)
check("the strategy-family test counts entry dates from its start", "2 of 20 entry dates" in txt, txt)
check("a missing table never raises: the section still returns", isinstance(er._section_evidence(sqlite3.connect(":memory:"),
                                                                                                 "2026-10-19", "LIVE"), list))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
