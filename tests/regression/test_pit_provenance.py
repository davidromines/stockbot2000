"""
REGRESSION: point-in-time provenance, and the ticker map that hid 212 large caps.

Three properties, all of which failed silently before being measured.

1. **A filed DATE is not an acceptance TIME.** The SEC stamps `filed` on a
   17:30 cutoff, not the 16:00 close, so 139,593 filings accepted in the 16:00
   hour carry the same filed date despite being untradeable that day. The first
   tradeable session must come from the acceptance timestamp and the real
   session calendar.

2. **Comparisons must replicate the step the real code performs.** Comparing
   `first_tradeable` against raw `filed + LAG_DAYS` reported 3,996 of 20,000
   filings as look-ahead. The pipeline snaps to the next SESSION via
   merge_asof, and against that the true figure is 2 — both SEC data oddities.
   Two false alarms in one day came from comparisons that skipped a step.

3. **212 issuers were mapped to preferred or warrant series.** JPMorgan as
   JPM-PM, Wells Fargo as WFC-PZ, AT&T as T-PC. JPM had 11,723 price bars and
   ZERO fundamental rows, so the conviction screens did not rank it poorly —
   they could not see it. A remap must never invent a security: BRK-A and BRK-B
   are both real common stock.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_pit_provenance.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import fix_ticker_map as ftm
import industry
import pit_facts

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE prices (ticker TEXT, date TEXT);
CREATE TABLE symbols (ticker TEXT, security_type TEXT);
CREATE TABLE sec_filings (adsh TEXT, cik INT, name TEXT, sic TEXT, form TEXT,
    period TEXT, filed TEXT, accepted TEXT, prevrpt INT, ticker TEXT,
    first_tradeable TEXT);
""")
# Sessions: Thu 2026-01-08, Fri 09, Mon 12 (weekend gap), Tue 13.
for d in ("2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13"):
    conn.execute("INSERT INTO prices VALUES ('SPY', ?)", (d,))
conn.commit()

# --- the acceptance-time rule ----------------------------------------------
cases = [
    ("2026-01-09 06:15:00.0", "2026-01-09", "before the open trades that session"),
    ("2026-01-09 09:29:00.0", "2026-01-09", "one minute before the bell still counts"),
    ("2026-01-09 09:31:00.0", "2026-01-12", "after the open waits for the next session"),
    ("2026-01-09 16:30:00.0", "2026-01-12", "after the close waits, and skips the weekend"),
    ("2026-01-09 21:00:00.0", "2026-01-12", "late evening waits"),
]
for accepted, expect, why in cases:
    got = pit_facts.first_tradeable_session(conn, accepted)
    check(f"{why}", got == expect, f"accepted {accepted[:16]} -> {got}, expected {expect}")

check("a weekend gap is crossed using real sessions, not weekday arithmetic",
      pit_facts.first_tradeable_session(conn, "2026-01-09 17:00:00.0") == "2026-01-12",
      "holidays must be handled by observation, never by assumption")
check("an unparsable stamp returns None rather than a guess",
      pit_facts.first_tradeable_session(conn, "") is None)
check("a malformed stamp returns None",
      pit_facts.first_tradeable_session(conn, "not-a-date-at-all") is None)

# --- annotate, then the knowable query --------------------------------------
rows = [("a1", 1, "AAA CORP", "6021", "10-K", "20251231", "2026-01-09 16:30:00.0", 0, "AAA"),
        ("a2", 1, "AAA CORP", "6021", "10-K/A", "20251231", "2026-01-12 08:00:00.0", 0, "AAA"),
        ("b1", 2, "BBB INC", "7372", "10-Q", "20250930", "2026-01-08 07:00:00.0", 1, "BBB")]
for r in rows:
    conn.execute("INSERT INTO sec_filings (adsh,cik,name,sic,form,period,accepted,"
                 "prevrpt,ticker) VALUES (?,?,?,?,?,?,?,?,?)", r)
conn.commit()
pit_facts.annotate(conn)

k = pit_facts.knowable(conn, "2026-01-09")
check("only filings tradeable by the date are returned",
      {x["adsh"] for x in k} == {"b1"},
      f"{sorted(x['adsh'] for x in k)} — a1 was accepted after the close")
k2 = pit_facts.knowable(conn, "2026-01-12")
check("later dates see more", {x["adsh"] for x in k2} == {"a1", "a2", "b1"})

check("a SUPERSEDED filing is included by default",
      any(x["adsh"] == "b1" for x in pit_facts.knowable(conn, "2026-01-12")),
      "it is what the market had at the time; excluding it substitutes what we "
      "now believe for what was known")
check("superseded filings can be excluded deliberately",
      all(x["adsh"] != "b1" for x in
          pit_facts.knowable(conn, "2026-01-12", include_superseded=False)))

# --- industry classification is point-in-time -------------------------------
c1 = industry.classify_as_of(conn, "AAA", "2026-01-12")
check("SIC 6021 classifies as finance", c1["division"] == "finance", str(c1))
check("finance is flagged for special accounting", bool(c1["special_accounting"]))
check("SIC 7372 classifies as services",
      industry.classify_as_of(conn, "BBB", "2026-01-12")["division"] == "services")
check("an unclassified ticker reports unknown, never a default bucket",
      industry.classify_as_of(conn, "ZZZ", "2026-01-12")["division"] == "unknown",
      "a silent default would rank a company against peers it has nothing to do with")
check("a classification is not visible before its filing was tradeable",
      industry.classify_as_of(conn, "AAA", "2026-01-08")["sic"] is None)
check("an unclassified ticker has no peers rather than a fallback group",
      industry.peers(conn, "ZZZ", "2026-01-12") == [])

check("division_of refuses to guess on junk input",
      industry.division_of("banana")[0] == "unknown"
      and industry.division_of(None)[0] == "unknown")

# --- the ticker remap is narrow --------------------------------------------
conn.executescript("""
INSERT INTO symbols VALUES ('JPM','common_stock');
INSERT INTO symbols VALUES ('JPM-PM','preferred');
INSERT INTO symbols VALUES ('BRK-A','common_stock');
INSERT INTO symbols VALUES ('BRK-B','common_stock');
INSERT INTO symbols VALUES ('ORPH','common_stock');
INSERT INTO sec_filings (adsh,ticker,name) VALUES ('c1','JPM-PM','J P MORGAN');
INSERT INTO sec_filings (adsh,ticker,name) VALUES ('c2','BRK-A','BERKSHIRE');
INSERT INTO sec_filings (adsh,ticker,name) VALUES ('c3','ORPH-PX','ORPHAN PFD');
""")
conn.commit()
p = {x["from"]: x["to"] for x in ftm.plan(conn)}
check("a preferred series IS remapped to its common stock",
      p.get("JPM-PM") == "JPM", str(p))
check("BRK-A is NOT remapped — both classes are real common stock",
      "BRK-A" not in p,
      "mapping it to 'BRK' would invent a security that does not trade")
check("a dashed ticker whose base is common stock remaps",
      p.get("ORPH-PX") == "ORPH")

res = ftm.apply(conn, dry_run=True)
check("a dry run changes nothing", res["updated"] == 0
      and conn.execute("SELECT ticker FROM sec_filings WHERE adsh='c1'"
                       ).fetchone()[0] == "JPM-PM")

ftm.apply(conn, dry_run=False)
check("applying the repair rewrites the ticker",
      conn.execute("SELECT ticker FROM sec_filings WHERE adsh='c1'").fetchone()[0] == "JPM")
check("the original is preserved for audit",
      conn.execute("SELECT ticker_raw FROM sec_filings WHERE adsh='c1'"
                   ).fetchone()[0] == "JPM-PM")
check("BRK-A is untouched by the repair",
      conn.execute("SELECT ticker FROM sec_filings WHERE adsh='c2'").fetchone()[0] == "BRK-A")

ftm.apply(conn, dry_run=False)
check("re-running does not overwrite the audit trail",
      conn.execute("SELECT ticker_raw FROM sec_filings WHERE adsh='c1'"
                   ).fetchone()[0] == "JPM-PM",
      "a second run must not record the repaired value as the original")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
