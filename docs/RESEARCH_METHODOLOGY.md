# Research methodology

Phase 6 §29. How this project decides whether a result is real. Each rule
below exists because the project broke it once; the incident is named so the
rule can be checked against what it was written to prevent.

**Default assumption: no edge until proven otherwise.** Every apparent edge
found so far has turned out to be a measurement artifact. The machinery here
exists to make a positive result harder to dismiss, not to produce one.

---

## 1. What counts as evidence

| evidence | what it can establish | what it cannot |
|---|---|---|
| backtest | a hypothesis worth testing forward; the failure of an idea | an edge: survivorship bias, multiple testing and fitting all inflate it |
| forward paper record | the only measurement with no survivorship bias and no look-ahead | significance, until it clears the league's sample floors (60 marks to rank) |
| live fills | what execution really costs | anything about skill: one trade (TNON) proves nothing either way |
| a citation | provenance: a reason to test | a result. Everything enters the library at HYPOTHESIS |

Backtests **admit** strategies to paper trading. Only forward evidence
**qualifies** them (`factory_pipeline.py`).

## 2. Measure against the right null

- **Never against zero.** Random entry and a 5-day hold was profitable in every
  window tested, because the market rose. Scoring against zero let 57% of random
  strategies through validation.
- **The null is a surface over entry price and holding period**
  (`benchmark.py`). A flat null paid a 45-day hold 30x for drift it did not
  earn, and handed anything that bought cheap stocks a free excess. The first 66
  "survivors" were a price filter (`sma_200 < 8`).
- **Matched universe.** Compare a strategy with what it could actually buy, not
  only with SPY (`baselines.py`, Phase 6 §16).
- **Buy-and-hold is a second mandatory benchmark** where it applies. ETF
  switching beat the random null on every pair and lost to doing nothing on
  every pair.
- **Random control** (`random_control.py`, `control.py`): the gate's
  false-positive rate is measured by pushing random genomes through it. Re-run
  `control.py --calibrate` after any change to fitness, the simulator or a gate.

## 3. Execution realism

- **Fills at the next open.** A signal read at a close cannot trade at that
  close. The look-ahead was worth 0.287 points per trade and turned the
  classifier from gross +$1.63 to gross -$58.77.
- **Exits priced off the unfiltered series.** A filter that decides what you
  may buy must never decide what you may sell. Ignoring this inflated the Lab's
  profit by 71%.
- **Costs always**, from one model (`costs.py`): spread by liquidity tier,
  slippage, fees. Unknown liquidity pays the widest spread, never zero.
- **Report gross, costs and net side by side.** Net P&L in dollars is the
  headline. AUC, win rate and Sharpe are diagnostics.
- **State the fill convention and position count** with any per-trade return.
  Both move it by more than the entire claimed edge.

## 4. Data integrity

- **Point-in-time or nothing.** Filings are used from their first tradeable
  session (`pit_facts.py`), market cap from the filing's shares and that day's
  price, the universe from the listing directory as it stood
  (`pit_universe.py`).
- **Absence is never zero, and unknown blocks.** An unknown market cap,
  liquidity or correlation is a rejection, not an average (TNON).
- **Freshness is measured against an independent reference**, never against the
  table being refreshed. Freshness gates protect only the tables they name.
- **Survivorship bias is enumerated, not assumed away**: 22.6% of the knowable
  2008 universe is priceable here, 83.7% of 2024. Synthetic dead companies are
  for stress bounds only (the generator fails its realism gate).
- **Two datasets must agree** before a result is trusted (`dataset_compare.py`).

## 5. Multiple testing

- **The trial counter is append-only** and never reset. Deleting failed trials
  does not delete the contamination: it destroys the denominator.
- **Label, never delete.** Voided survivors are marked, not removed.
- **Search is frozen by default** (`search.mode: FROZEN`). Lifting the freeze
  is a human edit to config; no code can lift it (`factory.py`).
- **More search is not the fix.** The binding constraint is the data (5
  delistings in 2006-2019 against 9,029 companies that existed), and a bigger
  search finds the same holes faster.

## 6. Separate the questions

- **Ranking skill is not tradeable edge.** The classifier ranks (AUC 0.63, 31 of
  31 folds) and loses money. `model_calibration.py` answers four questions
  separately: ranking, calibration, economic value, net performance.
- **Do not optimise on the measurement.** `signal_decay.py` reports a shape
  across horizons and recommends none. A better-looking horizon, threshold or
  band is a hypothesis for a pre-registered forward test.
- **Regimes are defined before results** (`regimes.py`, `config.yaml`
  `regimes:`). Breaking results down by an after-the-fact regime is
  cherry-picking.

## 7. Provenance of a finding

- **When survivors agree on an exact constant, find where the constant came
  from** before calling it a discovery. 231 of 455 survivors carried the seed's
  literal `40`: inheritance, not convergence.
- **Seeds are explicit** (`seed_mode: NONE`). Every strategy carries ancestry,
  and a seed-derived strategy is never classed as an independent discovery.
- **A refuted encoding is not a refuted publication.** Only a FAITHFUL encoding
  may be marked REFUTED.
- **Evidence is computed from the database, never typed in**, so a retraction
  cannot be outlived by a stale copy.

## 8. Verification

- **A check that skips a step the pipeline performs will invent a bug.** Two
  false alarms came from checks that did not snap to the next session.
- **Every measurement bug gets a regression test** (`tests/regression/`).
  `./run_tests.sh` is the gate; a pass means known failures did not recur, not
  that the system is right.
- **Nothing is overwritten.** Restatements live beside originals with a
  version (`accounting.py`). Forward curves with holes keep the hole.

## Where the procedure lives

| step | document / module |
|---|---|
| lock an experiment before running it | `docs/EXPERIMENT_PROTOCOL.md`, `experiment_registry.py` |
| what each stage may see | `docs/VALIDATION_FIREWALL.md` |
| what each table holds | `docs/DATA_DICTIONARY.md` |
| the standing status | `research_integrity.py` (daily), `phase6_report.py` |
