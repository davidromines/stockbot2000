"""slots: the monthly review (Stage AD2.3, owner H2 2026-10-19) — hard vs soft releases, grandfathering on a rule change,
replacement only at the review and only by a margin of switching cost + uncertainty, once per month; risk-adjusted order."""
import runtime  # noqa: F401
import sqlite3

import slots
import strategy_diversity

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

CFG = {"slots": {"count": 3, "review": {"cadence": "monthly", "max_replacements": 2, "min_hold_sessions": 0,
                                        "switching_cost": 0.004, "se_multiple": 1.0, "se_fallback": 0.01}},
       "ranking": {"evidence_mode": "backtest_first"}}
FP = slots.rules_fingerprint(CFG)


def row(key, score, eligible=True, reasons=(), gate=None, se=0.005, fam=None):
    return {"strategy_key": key, "version": 1, "score": score, "eligible": eligible, "reasons": list(reasons),
            "passes_gate": gate is None, "gate": gate, "family": fam or key, "forward_trades": 0, "score_se": se,
            "risk_adj": None if score is None else score / 0.05, "sd_20": 0.05}


def db(days):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
    for d in days:
        c.execute("INSERT INTO prices VALUES ('SPY',?,1,1,1,1,1)", (d,))
    slots.init(c)
    return c


def assign(c, slot, key, rules):
    import json
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason, evidence) "
              "VALUES ('2026-10-01T09:00:00+00:00',?,'ASSIGN',?,1,20,'LIVE','t',?)", (slot, key, json.dumps({"rules": rules})))


strategy_diversity.lookup = lambda *a, **k: None
slots._idle_check = lambda conn, cfg, s: (lambda r: "")
OCT = [f"2026-10-{d:02d}" for d in (1, 2, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16)]

# --- a mid-month day: only hard failures release ---------------------------------------------------------------
c = db(OCT)
assign(c, 1, "drift", FP); assign(c, 2, "halted", FP); assign(c, 3, "gate_new", None)
slots._today = lambda: "2026-10-19"
rows = [row("drift", -0.01, False, ["predicted to lose: score -1.00% per 20 sessions held"]),
        row("halted", 0.02, False, ["strategy kill switch: owner"]),
        row("gate_new", 0.02, False, ["loses money in the worst-case survivorship mode (-0.085% per trade)"],
            gate="loses money in the worst-case survivorship mode (-0.085% per trade)"),
        row("star", 0.09)]
slots.assess = lambda conn, cfg: rows
p = slots.plan(c, CFG)
rel = {s_: why for s_, h, why in p["release"]}
check("mid-month: no review", p["review_month"] is None)
check("a kill switch releases at once (hard)", 2 in rel and "kill switch" in rel[2], rel)
check("score drift waits for the review (soft): the holder keeps its slot", 1 not in rel and 1 in p["keep"])
check("a gate failed because the rules changed since assignment is grandfathered", 3 not in rel and 3 in p["keep"])
check("the deferred releases are listed with their reasons", {d[0] for d in p["deferred"]} == {1, 3}, p["deferred"])
check("the freed slot is refilled from the eligible pool", [a[1]["strategy_key"] for a in p["assign"]] == ["star"])
check("no score-based replacement between reviews", not any("replaced by" in w for _, _, w in p["release"]))

# the same gate under the CURRENT rules is a real (data) failure: hard
c = db(OCT)
assign(c, 3, "gate_new", FP)
rows = [rows[2], row("star", 0.09)]
p = slots.plan(c, CFG)
check("the same gate under the current rules releases at once", [s_ for s_, _, _ in p["release"]] == [3], p["release"])

# --- the month's first session: the review ---------------------------------------------------------------------
c = db(OCT)
for i, k in enumerate(("a", "b", "weak"), 1):
    assign(c, i, k, FP)
slots._today = lambda: "2026-11-02"
rows = [row("a", 0.05), row("b", 0.04), row("weak", 0.010), row("small_edge", 0.014), row("big_edge", 0.030)]
slots.assess = lambda conn, cfg: rows
p = slots.plan(c, CFG)
check("the month's first session is a review", p["review_month"] == "2026-11")
reps = [(s_, why) for s_, h, why in p["release"] if "replaced by" in why]
check("at the review a challenger better by more than the margin replaces the weakest holder",
      len(reps) == 1 and reps[0][0] == 3 and "big_edge" in reps[0][1], p["release"])
check("the margin = switching cost + 1 SE of the difference (0.4% + 0.71%) is stated",
      "monthly review 2026-11" in reps[0][1] and "+1.11%" in reps[0][1], reps)
rows2 = [row("a", 0.05), row("b", 0.04), row("weak", 0.010), row("small_edge", 0.014)]
slots.assess = lambda conn, cfg: rows2
check("a challenger inside the margin does not", not [w for _, _, w in slots.plan(c, CFG)["release"] if "replaced" in w])
slots.assess = lambda conn, cfg: rows
out = slots.apply(c, CFG, mode="SIMULATION")
check("apply records the review month", out.get("review_month") == "2026-11")
check("...and the new holder carries the rules fingerprint", slots.current(c, CFG)[3]["rules"] == FP)
check("the review happens once per month", slots.review_month(c, CFG, "2026-11-02") is None)
check("the next month has its own review", slots.review_month(c, CFG, "2026-12-01") == "2026-12")
check("daily cadence (the original rule) reviews every day",
      slots.review_month(c, {"slots": {"review": {"cadence": "daily"}}}, "2026-11-17") == "2026-11")

# --- fingerprint and ordering --------------------------------------------------------------------------------------
check("the fingerprint changes when the ranking rules change",
      slots.rules_fingerprint({**CFG, "ranking": {"evidence_mode": "blend"}}) != FP)
check("...and not for settings that are not rules", slots.rules_fingerprint({**CFG, "intraday": {"stage": "LIVE"}}) == FP)
hi_vol, lo_vol = {"score": 0.04, "risk_adj": 0.4}, {"score": 0.02, "risk_adj": 0.8}
check("raw order prefers the higher score", slots._rank_value(hi_vol) > slots._rank_value(lo_vol))
check("risk-adjusted order prefers the higher score per unit of risk",
      slots._rank_value(lo_vol, "risk_adjusted") > slots._rank_value(hi_vol, "risk_adjusted"))
check("release_kind: idle and drift are soft, a forward-pool loss is hard",
      slots.release_kind("no longer eligible: entry rule fired on 0 of the last 60 sessions", {}, FP, None) == "soft"
      and slots.release_kind("no longer in the forward pool", {}, FP, None) == "hard")

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
