"""stop_adopt (owner 2026-10-21, option (a)): a variant is opened only where the 6x cell passed the pre-registered rule,
and slots.assess refuses every strategy registered from a research-only experiment while its parent stays eligible."""
import runtime  # noqa: F401
import sqlite3

import ranking
import slots
import stop_adopt as sa

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)


def cell(d, t, years):
    return {"d_mean": d, "t": t, "d_by_year": years, "n": 1000}


rows = [
    {"strategy": "fx_a@v1", "stop": 3.0, "base_mean": 0.01,
     "stops": {"6.0": cell(0.004, 6.0, {"2016": 0.01, "2017": 0.002, "2018": 0.001, "2019": -0.001}),
               "4.0": cell(0.002, 3.0, {"2016": 0.01, "2017": 0.002, "2018": 0.001, "2019": 0.001})}},
    {"strategy": "fx_b@v1", "stop": 3.0, "stops": {"6.0": cell(0.004, 2.0, {"2016": 0.01, "2017": 0.01})}},   # t < 2.58
    {"strategy": "fx_c@v1", "stop": 3.0, "stops": {"6.0": cell(0.004, 5.0, {"2016": -0.01, "2017": -0.01,
                                                                           "2018": 0.03})}},              # most years lose
    {"strategy": "fx_d@v1", "stop": 3.0, "stops": {"4.0": cell(0.003, 4.0, {"2016": 0.01})}},             # no 6x cell
]
w = sa.winners(rows)
check("only the strategy whose 6x cell passed (t >= 2.58 and a gain in most years) gets a variant", set(w) == {"fx_a@v1"},
      sorted(w))
check("the winner carries its own stop and the measured gain", w["fx_a@v1"]["own_stop"] == 3.0
      and w["fx_a@v1"]["d_mean"] == 0.004)

# slots.assess: a variant registered from the research-only experiment is never eligible; its parent still is
c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
c.execute("CREATE TABLE league_strategies (strategy_key TEXT, version INT, name TEXT, source_ref TEXT, parent_key TEXT)")
c.execute("INSERT INTO league_strategies VALUES ('paper:var1', 1, 'A · stop 6x ATR', 'stop_width_slots_v1', 'fx_a')")
c.execute("INSERT INTO league_strategies VALUES ('fx_a', 1, 'A', NULL, NULL)")
c.commit()
G = {"entry": {"op": "gt"}, "exit": {"op": "lt"}, "risk": {"stop_atr_multiple": 6.0, "max_hold_days": 60}}
real_rank, real_genome = ranking.rank, slots.genome_for
ranking.rank = lambda conn, cfg: [{"strategy_key": k, "version": 1, "passes_gate": True, "gate": "", "score": 0.05}
                                  for k in ("fx_a", "paper:var1")]
slots.genome_for = lambda conn, key, ver: G
try:
    out = {r["strategy_key"]: r for r in slots.assess(c, {})}
    check("the parent is eligible", out["fx_a"]["eligible"], out["fx_a"]["reasons"])
    check("the wider-stop variant is not eligible, and says why", not out["paper:var1"]["eligible"]
          and any("research only" in x for x in out["paper:var1"]["reasons"]), out["paper:var1"]["reasons"])
    out2 = {r["strategy_key"]: r for r in slots.assess(c, {"slots": {"research_only_sources": []}})}
    check("with the list emptied by the owner, the variant competes like any other", out2["paper:var1"]["eligible"],
          out2["paper:var1"]["reasons"])
    check("the exclusion is not a selection rule (the rules fingerprint ignores it)",
          slots.rules_fingerprint({}) == slots.rules_fingerprint({"slots": {"research_only_sources": ["x"]}}))
finally:
    ranking.rank, slots.genome_for = real_rank, real_genome
check("no league table: nothing is excluded and nothing fails", slots._research_only(sqlite3.connect(":memory:"),
                                                                                     ["stop_width_slots_v1"]) == {})

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
