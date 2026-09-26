# TASK-035

- component: research
- priority: high
- state: TODO
- branch: ado/task-035
- created: 2026-09-26T02:30:00+00:00
- dependencies: TASK-034

## Objective
Create factory_families_o.py (Stage O, Addendum E): register ten new strategy families translated from the Knowledge Library into strategy_factory's family registry, exactly as specified below, plus its regression test.

## Background
strategy_factory.py keeps families in a dict F and registers them with family(name, league, rationale, grid, build, data=("features",), available=True, missing=None, combo=False). It provides grammar helpers col(c), k(v), gt(a, b), lt(a, b), and_(*xs), rank(a), pct(a, n) and G(entry, exit_=None, stop=2.5, hold=20) which returns {"entry", "exit", "risk": {"stop_atr_multiple", "max_hold_days"}}; the exit defaults to never (stop or holding period only). There is no lag helper: define lag(a, n) = {"op": "lag", "args": [a], "n": int(n)} in this module. Columns available on the panel: log_dollar_volume, price_above_sma200 and the calendar columns cal_month, cal_dom, cal_tdom, cal_tdom_rev (1 = the month's last session), cal_pre_holiday, cal_post_holiday (0/1). Import strategy_factory as sf and call sf.family(...) at import time; strategy_factory.py will import this module at its end (a later one-line change, NOT part of this task), so this module must not import anything that imports strategy_factory at module level except strategy_factory itself. LIQ(q) below means gt(rank(col("log_dollar_volume")), k(q)) (the most liquid names, the closest this stock universe gets to "the index"); ILLIQ(q) means lt(rank(col("log_dollar_volume")), k(q)). FAMILIES TO REGISTER, name / league / grid / entry / exit / stop / hold:
1. turn_of_month / tactical / {"last": [1, 2], "stop": [2.0, 3.0]} / and_(lt(col("cal_tdom_rev"), k(p["last"] + 0.5)), LIQ(0.9)) / and_(gt(col("cal_tdom"), k(3.5)), lt(col("cal_tdom"), k(10))) / p["stop"] / 5.
2. pre_holiday / tactical / {"hold": [1, 2], "stop": [2.0, 3.0]} / and_(gt(col("cal_pre_holiday"), k(0.5)), LIQ(0.9)) / gt(col("cal_post_holiday"), k(0.5)) / p["stop"] / p["hold"].
3. payday / tactical / {"hold": [2, 3], "stop": [2.0, 3.0]} / and_(gt(col("cal_dom"), k(13.5)), lt(col("cal_dom"), k(15.5)), LIQ(0.9)) / none / p["stop"] / p["hold"].
4. january_illiquid / tactical / {"q": [0.2, 0.3], "stop": [3.0, 5.0]} / and_(gt(col("cal_month"), k(11.5)), lt(col("cal_tdom_rev"), k(1.5)), ILLIQ(p["q"])) / and_(gt(col("cal_month"), k(1.5)), lt(col("cal_month"), k(2.5))) / p["stop"] / 30.
5. seasonality_12m / momentum / {"q": [0.9, 0.95], "stop": [3.0, 4.0]} / gt(rank(lag(pct(col("close"), 21), 231)), k(p["q"])) / none / p["stop"] / 21.
6. liquidity_premium / tactical / {"q": [0.1, 0.2], "hold": [40, 60], "stop": [3.0, 5.0]} / ILLIQ(p["q"]) / none / p["stop"] / p["hold"].
7. small_cap / fundamental / {"q": [0.2]} / lt(rank(col("market_cap")), k(p["q"])) / none / 3.0 / 60; data ("features", "daily_fundamentals", "market_cap"), available=False, missing="market_cap is not projected into daily_fundamentals; log_dollar_volume ranks liquidity, not size".
8. rd_intensity / fundamental / {"q": [0.8]} / gt(rank(col("rd_to_assets")), k(p["q"])) / none / 3.0 / 60; data ("features", "daily_fundamentals", "R&D expense"), available=False, missing="R&D expense is not tagged in sec_facts / statements.py and not on the daily panel".
9. short_interest / fundamental / {"q": [0.2]} / lt(rank(col("short_interest_ratio")), k(p["q"])) / none / 3.0 / 20; data ("features", "short interest"), available=False, missing="no short-interest data source in this project".
10. capm_alpha / momentum / {"q": [0.8]} / gt(rank(col("alpha_252")), k(p["q"])) / none / 3.0 / 20; data ("features", "risk_metrics"), available=False, missing="risk_metrics holds monthly beta/idiosyncratic volatility but no alpha on the daily panel".
Each family also needs a one-sentence rationale naming the published effect (e.g. turn of the month: Ariel 1987, Lakonishok & Smidt 1988; pre-holiday: Ariel 1990; payday: Ma & Pratt / Quantpedia payday anomaly; January effect: Keim 1983 / Reinganum; 12-month seasonality: Heston & Sadka 2008; illiquidity premium: Amihud 2002; size: Banz 1981; R&D: Chan, Lakonishok & Sougiannis 2001; short interest: Asquith, Pathak & Ritter 2005; CAPM alpha: Jensen 1968), and where the encoding deviates from the source the rationale says so in a few words (the index effects are traded here on the most liquid decile of stocks, the January small-cap effect on the least liquid names).
KNOWLEDGE maps each family name to the Knowledge Library entry ids it translates: turn_of_month -> ["qc_library:b2e0400834cd", "pwb_coded:8b0022f2370f"]; pre_holiday -> ["qc_library:9eb436f81ad0"]; payday -> ["pwb_coded:336bb3426a28"]; january_illiquid -> ["qc_library:2ff4bfc415b4"]; seasonality_12m -> ["pwb_coded:153777789290"]; liquidity_premium -> ["qc_library:6450e56a750e"]; small_cap -> ["qc_library:57785be8f6f4", "pwb_coded:4386f6dde875"]; rd_intensity -> ["pwb_coded:ff2022843d1f"]; short_interest -> ["pwb_coded:e43bdc6be336"]; capm_alpha -> ["qc_library:0939e67287ee"].

## Relevant files
- `factory_families_o.py`
- `tests/regression/test_factory_families_o.py`
- `strategy_factory.py`
## Requirements
1. factory_families_o.py registers exactly the ten families above via sf.family with the given league, grid, entry, exit, stop and hold, the data/available/missing arguments for families 7-10, and the rationale text.
2. It defines lag(a, n), LIQ(q), ILLIQ(q), NEW_FAMILIES (tuple of the ten names in order) and KNOWLEDGE (dict as above).
3. Registering is idempotent: importing the module twice does not duplicate or change F.
4. A module docstring states: Stage O translations from the Knowledge Library, templates not search (the freeze boundary of strategy_factory applies), encoding deviations stated per family.

## Constraints
1. Create ONLY factory_families_o.py and tests/regression/test_factory_families_o.py. Do NOT modify strategy_factory.py (it is given for reference).
2. No database, no network.
3. Keep factory_families_o.py under 200 lines and the test under 150 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does; import strategy_factory then factory_families_o.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_factory_families_o.py exits 0.
2. The test checks: all ten names are in strategy_factory.F; turn_of_month's first grid point builds a genome whose entry JSON contains "cal_tdom_rev" and "log_dollar_volume" and whose risk max_hold_days is 5; seasonality_12m's entry contains an op "lag" with n 231 wrapping an op "pct_change" with n 21; families 7-10 have data_available False and a non-empty missing reason; families 1-6 have data_available True; KNOWLEDGE has an entry for every name in NEW_FAMILIES; strategy_factory.grid_points works for each new family (at least one point each).
3. The test checks that tests/regression/test_freeze_boundary.py-style isolation holds: the strings "evolve" and "seeds" do not appear as imports in factory_families_o.py.
4. At least 9 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
