"""
REGRESSION: the point-in-time universe must come from the historical record.

The first version of this module read `symbols.first_seen` and returned ZERO
knowable securities for every historical date — because that column records when
our own daily snapshots first saw a ticker (2026-09-08 onward), not when the
company listed. It is the wrong source and it fails silently, returning an empty
universe rather than an error.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_pit_universe.py
"""
import runtime  # noqa: F401
import inspect

import pit_universe as pit
import storage
from universe import load_config

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


src = inspect.getsource(pit.get_available_securities)
check("the universe is built from historical_listings",
      "historical_listings" in src,
      "symbols.first_seen records OUR first sighting, not the listing date")
check("it does NOT rely on symbols.first_seen",
      "first_seen" not in src,
      "that column starts at 2026-09-08 and returns an empty historical universe")

cfg = load_config()
conn = storage.connect(cfg["database"]["market_data_path"])
pit.init(conn)

snap, lag = pit.nearest_snapshot(conn, "2012-06-29")
check("a historical date resolves to a real snapshot", bool(snap), str(snap))
check("the snapshot is at or BEFORE the date", snap <= "2012-06-29", str(snap))
check("snapshot lag is reported", lag is not None and lag >= 0, str(lag))

u = pit.get_available_securities(conn, "2012-06-29")
check("a 2012 universe is non-empty", len(u) > 100, f"{len(u)} securities")
check("every row carries its snapshot provenance",
      all("snapshot_date" in x and "snapshot_lag_days" in x for x in u[:20]))

# A date before any snapshot must say "cannot answer", not "nothing existed".
snap_old, _ = pit.nearest_snapshot(conn, "1999-01-01")
check("a pre-record date returns no snapshot rather than a false empty universe",
      snap_old is None, str(snap_old))

# The lever that matters.
priced = pit.get_available_securities(conn, "2012-06-29", with_prices_only=True)
check("with_prices_only returns a SUBSET of the knowable universe",
      0 < len(priced) < len(u), f"{len(priced)} of {len(u)}")

c = pit.coverage(conn, "2012-06-29")
check("coverage separates knowable from priced",
      c["knowable"] > c["priced"] > 0, str(c))
check("blind == knowable - priced", c["blind"] == c["knowable"] - c["priced"])
check("coverage in 2012 is materially below 100%",
      c["coverage_pct"] < 60,
      "if this ever reads near 100% the survivorship hole has been filled — "
      "verify that before believing it")

# The direction of the bias: coverage must improve toward the present, because
# survivors keep their history and the dead do not.
c08 = pit.coverage(conn, "2008-06-30")
c24 = pit.coverage(conn, "2024-06-28")
check("coverage is far worse in 2008 than 2024",
      c08["coverage_pct"] < c24["coverage_pct"] - 20,
      f"2008 {c08['coverage_pct']}% vs 2024 {c24['coverage_pct']}%")

conn.close()
print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
