"""
REGRESSION: the defects that let bad data reach a decision.

  staleness circularity        freshness measured against the table being refreshed
  liquidity-floor omission     a floor applied on one path and not another
  unknown market-cap acceptance  an unmeasured value treated as an acceptable one

The third is the one that cost real money. TNON had no market cap on record, a
"reject if below the floor" test waved it through as unmeasured, and the
position closed -29%. A missing measurement is not an average one.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_data_integrity.py
"""
import runtime  # noqa: F401
import inspect
import sqlite3
import tempfile

import storage
from risk_engine import RiskEngine, load_limits
from signals import Signal

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- 1. STALENESS CIRCULARITY ----------------------------------------------
# The defect: `as_of` defaulted to MAX(date) over the same table being advanced.
# Level the universe and nothing is ever behind, so nothing is fetched.
conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
storage.init_db(conn)
for t in ("A", "B", "C"):
    conn.execute("INSERT INTO ingest_state (ticker, first_date, last_date, row_count,"
                 " status, attempts, updated_at) VALUES (?,?,?,?, 'done', 0, '2026-01-01')",
                 (t, "2020-01-01", "2026-09-11", 100))
conn.commit()

level = storage.stale_tickers(conn, ["A", "B", "C"], as_of="2026-09-11")
check("a level universe reports nothing stale against its own max", len(level) == 0)

ahead = storage.stale_tickers(conn, ["A", "B", "C"], as_of="2026-09-14")
check("an EXTERNAL reference exposes all three as stale", len(ahead) == 3,
      f"got {len(ahead)} — this is the bug: without an outside reference the "
      f"database freezes at its own newest bar")

check("stale_tickers accepts an as_of parameter at all",
      "as_of" in inspect.signature(storage.stale_tickers).parameters)
check("backfill exposes last_market_session for that reference",
      hasattr(__import__("backfill"), "last_market_session"))

import backfill
src = inspect.getsource(backfill.last_market_session)
check("the market-session probe EXCLUDES today (no partial bars as closes)",
      "today" in src and "<" in src,
      "asked during market hours it would otherwise store in-progress bars")

# --- 2. UNKNOWN MARKET CAP MUST BE REJECTED --------------------------------
E = RiskEngine(load_limits())
PORT = {"equity": 100.0, "buying_power": 100.0, "daily_pnl": 0.0,
        "drawdown_percent": 0.0, "positions": {}}


def sig(**kw):
    base = dict(symbol="AAPL", action="BUY", strategy="regression",
                reason="regression", notional_value=20.0, confidence=0.9,
                session="2026-09-22")
    base.update(kw)
    return Signal(**base)


GOOD = {"price": 50.0, "dollar_volume_20": 20e6, "market_cap": 5e9}

check("known-good passes (otherwise every rejection below is vacuous)",
      E.validate(sig(), PORT, GOOD, {}).approved)

r = E.validate(sig(), PORT, {**GOOD, "market_cap": None}, {})
check("UNKNOWN market cap is REJECTED — the TNON case", not r.approved,
      "an unmeasured value must not be treated as acceptable")

r = E.validate(sig(), PORT, {**GOOD, "market_cap": 3.5e6}, {})
check("a $3.5M nano-cap is rejected", not r.approved)

# --- 3. LIQUIDITY FLOOR MUST APPLY EVERYWHERE ------------------------------
r = E.validate(sig(), PORT, {**GOOD, "dollar_volume_20": None}, {})
check("UNKNOWN liquidity is REJECTED", not r.approved)

r = E.validate(sig(), PORT, {**GOOD, "dollar_volume_20": 100.0}, {})
check("an illiquid name is rejected", not r.approved)

# The omission was structural: the floor lived on one code path and not another.
import conviction
panel_src = inspect.getsource(conviction._load_panel)
check("the conviction path applies min_dollar_volume, not just min_price",
      "min_dollar_volume" in panel_src,
      "this floor was missing from the fundamental screens entirely")
check("the conviction path still applies min_price", "min_price" in panel_src)

# --- 4. A MISSING QUOTE MUST FAIL CLOSED -----------------------------------
check("no quote at all is rejected rather than assumed",
      not E.validate(sig(), PORT, None, {}).approved)

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
