27 of 31 checks pass. Four fail, all from one misunderstanding about where the
trial count comes from.

`stop_conditions.evaluate` gets its trial count from
`multiple_testing.count(conn)["total_trials"]`, and that function does NOT read
a `trial_ledger` table. It counts rows in `evaluations`, plus `promotions`,
plus backtest and sweep records — look at multiple_testing.count() directly.
So creating a trial_ledger table and inserting into it leaves total_trials at
0, and the "above threshold" case can never fire.

There are two clean ways to drive it; use the SECOND, it is simpler and does
not depend on that function's internals:

  1. Insert enough rows into `evaluations` — impractical for a million.

  2. Pass a cfg whose threshold is low. `_cfg()` merges
     `cfg["search"]["stop_conditions"]` over DEFAULTS, so:

         cfg = {"lab": {"search_start": "2006-01-01"},
                "search": {"stop_conditions": {"max_trials": 0}}}

     With max_trials 0, ANY trial count trips the condition, and with
     max_trials set very high it cannot. That tests the comparison, which is
     the behaviour that matters, without needing a million rows.

Apply the same approach to the other three failures:

- "any single condition is sufficient": build a cfg where exactly one
  threshold is trippable and the others are not, then assert len(reasons) == 1.
- "thresholds come from config": assert `_cfg(cfg)["max_trials"]` returns the
  overridden value and that an unspecified key still falls back to DEFAULTS.
- "render says DO NOT SEARCH": drive stop=True via the cfg as above, then
  assert the string appears in render(result).

Note the evaluate() signature is evaluate(conn, cfg) and it reads
cfg["lab"]["search_start"], so every cfg you build must include that key or it
will raise.

Everything else in the file is good — keep it.