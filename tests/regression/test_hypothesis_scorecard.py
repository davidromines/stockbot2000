"""hypothesis_scorecard: scoring thresholds and the append-only table (synthetic data)."""
import runtime  # noqa: F401
import sqlite3
import pandas as pd
import hypothesis_scorecard as hs

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE knowledge_entries (entry_id TEXT, source_type TEXT, original_claim TEXT, data_available TEXT, long_short TEXT, holding_period TEXT)")
c.execute("CREATE TABLE knowledge_lineage (entry_id TEXT, lineage_id TEXT)")
c.execute("CREATE TABLE knowledge_lineage_stats (as_of TEXT, lineage_id TEXT, independent_sources INT, test_count INT, holdout_tests INT, variant_count INT, strategy_count INT)")
c.execute("CREATE TABLE strategy_hold (strategy_key TEXT, avg_hold_days REAL)")
c.execute("CREATE TABLE strategy_correlation (key_a TEXT, key_b TEXT, corr REAL)")
for i, (st, claim, da) in enumerate([("ACADEMIC_PAPER", "x" * 40, "YES"), ("PRACTITIONER_RESEARCH", "", "NO")]):
    c.execute("INSERT INTO knowledge_entries VALUES (?,?,?,?,?,?)", (f"e{i}", st, claim, da, "long-only", ""))
    c.execute("INSERT INTO knowledge_lineage VALUES (?,?)", (f"e{i}", f"L{i}:close"))
c.execute("INSERT INTO knowledge_lineage_stats VALUES ('2026-10-01','L0:close',3,5,0,2,2)")
c.execute("INSERT INTO knowledge_lineage_stats VALUES ('2026-10-01','L1:close',1,300,0,2,2)")
c.execute("INSERT INTO strategy_hold VALUES ('a', 40)"); c.execute("INSERT INTO strategy_hold VALUES ('b', 2)")
m = pd.DataFrame({"strategy_key": ["a", "b"], "lineage_id": ["L0:close", "L1:close"], "sb_zero": [0.01, -0.02], "sb_as_is": [0.02, 0.0], "fw_n": [0, 0], "fw_mean": [None, None]})
sc = hs.scorecard(c, m).set_index("lineage")
check("an academic, multi-source, long-hold, worst-case-positive lineage outscores a practitioner short-hold loser", sc.loc["L0:close", "total"] > sc.loc["L1:close", "total"] + 6)
check("rationale needs a claim and an academic source for 2", sc.loc["L0:close", "s_rationale"] == 2 and sc.loc["L1:close", "s_rationale"] == 0)
check("hundreds of prior tests score 0 on validation", sc.loc["L1:close", "s_validation"] == 0 and sc.loc["L0:close", "s_validation"] == 2)
check("short holding period scores 0 on cost robustness", sc.loc["L1:close", "s_cost"] == 0 and sc.loc["L0:close", "s_cost"] == 2)
check("every dimension is 0 to 2", all(sc[c_].between(0, 2).all() for c_ in sc.columns if c_.startswith("s_")))
hs.init(c); hs.init(c)
check("table creation is idempotent", c.execute("SELECT COUNT(*) FROM hypothesis_scorecard").fetchone()[0] == 0)
print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
