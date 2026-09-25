"""
Regression tests for leagues.py — Phase 13 H8 tiers and standings.

The tier function is the whole promotion decision for a league, and it is pure,
so it is tested directly against the four boundaries the spec names. The rest
covers the two places a wrong answer would be silent: fund_ref's prefix mapping
(a mis-mapped key reads another fund's accounting and reports it as this one's)
and evidence()'s session count (a count taken from the wrong table would make a
fund look seasoned when it is not).

Run: PYTHONPATH=. venv/bin/python tests/regression/test_leagues.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import accounting
import league
import leagues
import paper_trading
import strategy_objects as so

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))
        FAILED.append(name)


# The league config from the task. Kept here rather than read from config.yaml
# so the boundary arithmetic is visible in the test that asserts it.
LC = {"min_forward_sessions": 20, "min_closed_trades": 10,
      "established_sessions": 60, "max_drawdown_pct": 15}


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def ev(**kw):
    base = {"has_forward_record": True, "sessions": 30, "closed_trades": 12,
            "net_usd": 5.0, "max_drawdown_pct": 3.0}
    base.update(kw)
    return base


def test_tier():
    check("tier: no forward record -> INSUFFICIENT_SAMPLE",
          leagues.tier({"has_forward_record": False}, LC) == "INSUFFICIENT_SAMPLE")
    check("tier: net None -> INSUFFICIENT_SAMPLE",
          leagues.tier(ev(net_usd=None), LC) == "INSUFFICIENT_SAMPLE")
    check("tier: 19 sessions -> INSUFFICIENT_SAMPLE",
          leagues.tier(ev(sessions=19), LC) == "INSUFFICIENT_SAMPLE")
    check("tier: 9 closed trades -> INSUFFICIENT_SAMPLE",
          leagues.tier(ev(closed_trades=9), LC) == "INSUFFICIENT_SAMPLE")
    check("tier: net -1 -> NOT_ELIGIBLE",
          leagues.tier(ev(net_usd=-1.0), LC) == "NOT_ELIGIBLE")
    check("tier: net 0 -> NOT_ELIGIBLE (not positive)",
          leagues.tier(ev(net_usd=0.0), LC) == "NOT_ELIGIBLE")
    check("tier: drawdown 16 > 15 -> NOT_ELIGIBLE",
          leagues.tier(ev(max_drawdown_pct=16.0), LC) == "NOT_ELIGIBLE")
    check("tier: drawdown exactly 15 -> ELIGIBLE (limit is inclusive)",
          leagues.tier(ev(max_drawdown_pct=15.0), LC) == "ELIGIBLE")
    check("tier: 30 sessions, net 5, dd 3 -> ELIGIBLE",
          leagues.tier(ev(), LC) == "ELIGIBLE")
    check("tier: 60 sessions -> ESTABLISHED",
          leagues.tier(ev(sessions=60), LC) == "ESTABLISHED")
    check("tier: 59 sessions -> ELIGIBLE",
          leagues.tier(ev(sessions=59), LC) == "ELIGIBLE")


def test_fund_ref():
    c = conn()
    leagues.init(c)
    check("fund_ref: paper: prefix",
          leagues.fund_ref(c, "paper:abc") == ("paper", "abc"))
    check("fund_ref: pair: prefix",
          leagues.fund_ref(c, "pair:spy_tlt") == ("pair", "spy_tlt"))
    check("fund_ref: value: prefix",
          leagues.fund_ref(c, "value:stockbot_value_fund") == ("value", "stockbot_value_fund"))
    check("fund_ref: crypto: prefix",
          leagues.fund_ref(c, "crypto:crypto_paper_fund") == ("crypto", "crypto_paper_fund"))
    check("fund_ref: unknown key with no link row -> None",
          leagues.fund_ref(c, "fx_momentum_deadbeef") is None)
    c.execute("INSERT INTO factory_paper_link VALUES (?,?,?,?)",
              ("fx_momentum_deadbeef", 1, "run123", "2026-09-24"))
    c.commit()
    check("fund_ref: factory link row -> (paper, run_id)",
          leagues.fund_ref(c, "fx_momentum_deadbeef") == ("paper", "run123"))
    check("fund_ref: link is version-specific",
          leagues.fund_ref(c, "fx_momentum_deadbeef", 2) is None)
    c.close()


def test_max_dd():
    c = conn()
    leagues.init(c)
    # paper_runs / paper_equity are created by paper_trading.init, not by
    # leagues.init — the fixture has to bring them in or the inserts below
    # fail with "no such table: paper_runs".
    paper_trading.init(c)
    c.execute("INSERT INTO paper_runs (run_id, name, strategy, capital_usd, cash_usd, "
              "started_on, created_at) VALUES ('r1','t','model',100,100,'2026-01-01','x')")
    for d, e in (("2026-01-01", 100.0), ("2026-01-02", 110.0), ("2026-01-03", 99.0)):
        c.execute("INSERT INTO paper_equity VALUES ('r1',?,?,?,?,0)", (d, e, e, e))
    c.commit()
    dd = leagues._max_dd(c, "paper", "r1")
    check("_max_dd: 100,110,99 -> 10.0", dd is not None and abs(dd - 10.0) < 0.01,
          f"got {dd}")
    check("_max_dd: no equity rows -> None",
          leagues._max_dd(c, "paper", "nope") is None)
    c.close()


def test_evidence():
    c = conn()
    leagues.init(c)
    paper_trading.init(c)
    c.execute("INSERT INTO paper_runs (run_id, name, strategy, capital_usd, cash_usd, "
              "started_on, created_at) VALUES ('r1','t','model',100,100,'2026-01-01','x')")
    for i in range(25):
        d = f"2026-01-{i + 1:02d}"
        c.execute("INSERT INTO paper_equity VALUES ('r1',?,?,?,?,0)", (d, 100.0, 100.0, 100.0))
    c.execute("INSERT INTO fund_accounting (as_of, fund_kind, fund_id, capital_usd, "
              "gross_usd, costs_realized, costs_open, costs_usd, net_usd, equity_restated, "
              "closed_trades, cost_basis, reconciled, accounting_version, computed_at) "
              "VALUES ('2026-01-25','paper','r1',100,7.5,1.0,0.5,1.5,6.0,106.0,12,"
              "'modeled',1,1,'2026-01-25')")
    c.commit()
    e = leagues.evidence(c, "paper:r1")
    check("evidence: has_forward_record", e.get("has_forward_record") is True)
    check("evidence: net_usd from fund_accounting", e.get("net_usd") == 6.0,
          f"got {e.get('net_usd')}")
    check("evidence: sessions == paper_equity row count", e.get("sessions") == 25,
          f"got {e.get('sessions')}")
    check("evidence: closed_trades from fund_accounting", e.get("closed_trades") == 12)
    check("evidence: no accounting row -> net None, NO_ACCOUNTING",
          leagues.evidence(c, "paper:missing").get("net_usd") is None
          and leagues.evidence(c, "paper:missing").get("recon_status") == "NO_ACCOUNTING")
    check("evidence: unknown key -> no forward record",
          leagues.evidence(c, "fx_nothing") == {"has_forward_record": False})
    c.close()


def test_family_of():
    c = conn()
    leagues.init(c)
    league.register(c, "fx_crash_b", "Crash Buyer 20d b · stop 2.5",
                    {"family": "crash_buyer", "entry_rule": "x", "exit_rule": "y"})
    check("family_of: strips ' · ' suffix and sibling letter",
          leagues.family_of(c, "fx_crash_b") == "crash_buyer_20d",
          f"got {leagues.family_of(c, 'fx_crash_b')}")
    league.register(c, "fx_crash_a", "Crash Buyer 20d a",
                    {"family": "crash_buyer", "entry_rule": "x", "exit_rule": "y"})
    check("family_of: lettered siblings share one family",
          leagues.family_of(c, "fx_crash_a") == leagues.family_of(c, "fx_crash_b"))
    # A strategy_meta family wins over the name, so a renamed strategy keeps its
    # concentration family rather than silently becoming a new one.
    so.init(c)
    so.register(c, {"strategy_key": "fx_meta", "name": "Something Else Entirely",
                    "family": "meta_family", "genome": {"entry": "a", "exit": "b"}})
    check("family_of: strategy_meta family wins",
          leagues.family_of(c, "fx_meta") == "meta_family",
          f"got {leagues.family_of(c, 'fx_meta')}")
    c.close()


def test_league_of():
    c = conn()
    leagues.init(c)
    cfg = {"leagues": {"tactical": {}, "value": {}},
           "league_families": {"value": "value", "crypto": "crypto"}}
    league.register(c, "fx_tac", "Tactical Thing",
                    {"family": "momentum", "entry_rule": "x", "exit_rule": "y"})
    check("league_of: unmapped family -> tactical",
          leagues.league_of(c, cfg, "fx_tac") == "tactical")
    league.register(c, "fx_val", "Value Thing",
                    {"family": "value", "entry_rule": "x", "exit_rule": "y"})
    check("league_of: mapped family -> its league",
          leagues.league_of(c, cfg, "fx_val") == "value")
    c.close()


def test_standings():
    c = conn()
    leagues.init(c)
    paper_trading.init(c)
    cfg = {"leagues": {"tactical": LC}, "league_families": {}}
    c.execute("INSERT INTO paper_runs (run_id, name, strategy, capital_usd, cash_usd, "
              "started_on, created_at) VALUES ('r1','t','model',100,100,'2026-01-01','x')")
    for i in range(25):
        c.execute("INSERT INTO paper_equity VALUES ('r1',?,?,?,?,0)",
                  (f"2026-01-{i + 1:02d}", 100.0, 100.0, 100.0))
    c.execute("INSERT INTO fund_accounting (as_of, fund_kind, fund_id, capital_usd, "
              "gross_usd, costs_realized, costs_open, costs_usd, net_usd, equity_restated, "
              "closed_trades, cost_basis, reconciled, accounting_version, computed_at) "
              "VALUES ('2026-01-25','paper','r1',100,7.5,1.0,0.5,1.5,6.0,106.0,12,"
              "'modeled',1,1,'2026-01-25')")
    league.register(c, "paper:r1", "Paper One",
                    {"family": "momentum", "entry_rule": "x", "exit_rule": "y"})
    league.transition(c, "paper:r1", league.PAPER, "migrated forward record")
    c.commit()
    st = leagues.standings(c, cfg)
    rows = st.get("tactical", [])
    check("standings: the live strategy appears", len(rows) == 1, f"got {len(rows)}")
    if rows:
        r = rows[0]
        check("standings: tier computed from accounting",
              r["tier"] == "ELIGIBLE", f"got {r['tier']}")
        check("standings: rank assigned", r["rank"] == 1)
        check("standings: net carried through", r["net_usd"] == 6.0)
    # A strategy with no forward record must not be ranked at all — ranking it
    # would put an unmeasured strategy above a measured one.
    league.register(c, "fx_none", "No Record",
                    {"family": "momentum", "entry_rule": "x", "exit_rule": "y"})
    league.transition(c, "fx_none", league.DISCOVERED, "generated")
    st2 = leagues.standings(c, cfg)
    check("standings: DISCOVERED strategy excluded from the pool",
          all(r["strategy_key"] != "fx_none" for r in st2.get("tactical", [])))
    c.close()


def main():
    print("\n  leagues.py regression")
    print("  " + "-" * 60)
    for fn in (test_tier, test_fund_ref, test_max_dd, test_evidence,
               test_family_of, test_league_of, test_standings):
        fn()
    print("  " + "-" * 60)
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
