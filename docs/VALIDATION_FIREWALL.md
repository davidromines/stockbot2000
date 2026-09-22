# Validation firewall

Phase 6 section 9. For every stage of the promotion ladder: what it may see,
what it must never see, and how that is enforced.

**Six gates are not evidence of a sound method.** This project ran four searches
through this ladder and every one produced an artifact. The ladder caught none
of them; measurement did, afterwards. So this document is not a description of a
working system — it is a specification of what each stage is *allowed* to know,
written so violations become findable.

---

## The rule the whole thing rests on

```text
No stage may see information that did not exist at the moment it claims to
be deciding.
```

Two kinds of violation, and they are not equally visible:

| | |
|---|---|
| **Temporal leakage** | using a future price, filing, or delisting. Loud once looked for — `tests/regression/test_lookahead.py` pins the known cases. |
| **Selection leakage** | using knowledge of a *later stage's outcome* to make an *earlier stage's* decision. Silent. Nothing in the data looks wrong; the choice was simply informed by something it should not have been. |

The second is why this document exists. Re-running a search after seeing that
its survivors failed validation, and keeping the version whose survivors passed,
is selection leakage even though every individual number is honest.

---

## Stage 01 — Search (2006–2019)

| | |
|---|---|
| **Input** | price and feature rows inside the search window, from the tradeable universe |
| **Transformation** | evolutionary rule synthesis; fitness = risk-adjusted, cost-net excess over the price×horizon null |
| **Output** | scored genomes in `strategies` / `evaluations` |
| **May see** | anything dated on or before each simulated decision, within the window |
| **MUST NEVER see** | any bar after `search_end`; validation or sealed results; forward paper results; which structures previously survived |

**Enforcement:** window bounds in `load_training_frame`; next-open fills in
`simulator.py`; exits priced off the unfiltered series.

**Known weakness — not enforced.** Nothing prevents a human re-running the
search after seeing later-stage outcomes. That is selection leakage and it is
currently governed by discipline alone. Phase 6 §11–12 (experiment registry and
pre-registration) is the mechanical fix, and until it exists this is the widest
hole in the ladder.

---

## Stage 02 — Shortlist

| | |
|---|---|
| **Input** | stage-01 evaluations for one run |
| **Transformation** | structural and behavioural deduplication, degeneracy rejection, diversity caps |
| **Output** | `promotions(stage='shortlist')` |
| **May see** | search-window scores and rule structure |
| **MUST NEVER see** | validation or sealed performance; forward results; any out-of-window data |

**Enforcement:** `genome.shape()` erases constants so one idea cannot occupy the
list; `is_degenerate()` rejects comparisons fixed before data arrives; Jaccard
overlap on actual entry rows catches what syntax cannot.

**Why it exists:** one search filled 199 of 200 slots with a single rule, and
the fix for that produced 60 "distinct" rules that were one rule with 60 dead
branches.

---

## Stage 03 — Validation (2020–2022)

| | |
|---|---|
| **Input** | shortlisted genomes; price/feature rows in the validation window |
| **Transformation** | re-simulate; score against the validation-window null; apply gates |
| **Output** | `promotions(stage='validation')` |
| **May see** | validation-window data; the search-window score |
| **MUST NEVER see** | the sealed window; forward paper results; live results |

**Enforcement:** window bounds; gates in `config.yaml` calibrated by
`control.py` against random genomes.

**Gate calibration is itself a leak risk.** Gates are set from a measured 95th
percentile of noise. If that measurement were taken on the same window the
strategies are judged on, the gate would be tuned to the data. It is currently
measured on the validation window — **this should move to a dedicated
calibration window**, and is recorded here as an open defect rather than a
solved problem.

---

## Stage 04 — Sealed holdout (2023–present)

| | |
|---|---|
| **Input** | one validated strategy, once |
| **Transformation** | simulate on the sealed window; apply the deflated-Sharpe correction using the true cumulative trial count |
| **Output** | `promotions(stage='sealed')` |
| **May see** | the sealed window, exactly once per strategy |
| **MUST NEVER see** | be re-run for any reason — not for early stopping, not for ranking, not for "just checking" |

**Enforcement:** `_already()` refuses a second attempt and records the refusal.
Uniquely, a `void` decision does NOT permit a retry at this stage — voiding a
sealed result would make re-testing free, which is the whole thing the seal
prevents.

**Not enforced:** the sealed window is readable by any process with a database
handle. Phase 6 §10 requires filesystem or permission enforcement, and
`truth_set.py` provides the mechanism (read-only snapshots) but the sealed range
is not yet carved out into its own.

---

## Stage 05 — Paper trading (forward)

| | |
|---|---|
| **Input** | a frozen strategy, from its start date forward |
| **Transformation** | daily simulated execution at next-open fills, costs charged |
| **Output** | `paper_runs` / `paper_equity` / `paper_trades` |
| **May see** | only data dated on or before each simulated day |
| **MUST NEVER see** | anything at all about its own future; and **it must never be modified retrospectively** |

**Enforcement:** the daily stepper advances one session at a time;
`pair_funds.py` replays from inception so a missed day self-heals rather than
being back-filled by hand.

**This is the only stage with no survivorship bias and no look-ahead**, because
the dates had not happened when the rule was written. It is therefore the
strongest evidence the system can produce, and the slowest.

---

## Stage 06 — Funded

| | |
|---|---|
| **Input** | a paper strategy meeting promotion criteria |
| **Transformation** | capital allocation, risk validation, order construction |
| **Output** | real orders; `picks`, `orders`, `fills` |
| **May see** | live account state, current quotes |
| **MUST NEVER see** | — but must never *bypass* `risk_engine.validate()` or the kill switches |

**Enforcement:** `execution.py` is the only path to a broker; the risk engine
sizes every order; six kill switches fail closed.

---

## What flows backward, and must not

```text
                 search → shortlist → validation → sealed → paper → funded
  forbidden:       ↑          ↑            ↑          ↑        ↑
                   └──────────┴────────────┴──────────┴────────┘
                         no later result may inform an earlier stage
```

Concretely, all of these are violations even though each individual number is
honest:

* re-running a search because its survivors failed validation
* adjusting a gate after seeing which strategies it rejected
* choosing a holding period because it performed better in the sealed window
* selecting which paper funds to report by their forward results
* re-deriving a "consensus" hypothesis after testing the first one

The last is why `consensus.py` writes its hypothesis to disk **before** scoring
and warns loudly on re-derivation.

---

## Open defects in the firewall

Stated rather than fixed, because an undocumented weakness is worse than a known one.

1. **No mechanical barrier against re-running a search after seeing later
   results.** Needs the experiment registry (Phase 6 §11–12).
2. **Gate calibration uses the validation window.** Should use a dedicated
   calibration window.
3. **The sealed window is not physically separated.** Any process with a
   database handle can read it. Needs Phase 6 §10.
4. **The trial counter is not incremented by promotion decisions**, only by
   evaluations — so continuous re-ranking is multiple testing that the
   correction currently cannot see.
5. **Seed ancestry is classified retrospectively** for the 1.03M strategies
   generated before `ancestry.py` existed, by literal and structural inference
   rather than recorded parentage. Imperfect, and labelled as such.
