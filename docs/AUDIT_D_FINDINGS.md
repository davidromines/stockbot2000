# Addendum F, Phase D: survivorship and execution realism (2026-10-13)

Read-only. Code: `audit_survivorship.py` (D1), `audit_execution.py` (D2); 9 checks in `tests/regression/test_audit_phase_d.py`.
Reports: `reports/audit_survivorship_2026-10-13.md`, `reports/audit_execution_2026-10-13.md`.

## D1: dependence on the synthetic dead companies

- A typical ranked strategy trades synthetic companies for **37 %** of its trades (90th percentile 54 %).
- Positive per-trade net: survivors only 94 %, with the synthetic dead companies (what the ranking uses) 88 %, worst case (every unpriced death a total loss) **55 %** of 1,221 strategies.
- **409 strategies (33 %) are positive as_is and non-positive in the worst case**: their verdict rests on an assumption the data cannot identify. 14 of the 40 best-scored strategies with survivorship data are in that group.
- Ordering: rank correlation as_is vs worst case +0.67; top-50 overlap 30 of 50.
- Generator configuration (v4, v5, v5c, v5c plus fundamentals and volume): of 288 strategies re-run under two or more, **21 % change sign**; median spread 0.31 points per trade. This overstates generator-only sensitivity because later configurations also let fundamental strategies trade the dead companies.
- Slots 1, 2 and 5 hold Lab-search funds, which are scored on paper only and have no survivorship backtest; slots 3 and 4 are positive as_is (+0.46 %, +0.05 %), slot 4 negative in the worst case (−0.09 %).
- **Paid delisted data: not yet.** It would settle the assumption that decides 33 % of verdicts, but no strategy has 20 independent forward entry dates, so forward evidence, not the survivorship prior, is the binding constraint. Revisit if a family passes the prospective test and its verdict then hangs on this assumption.

## D2: execution realism

- Paper and live share the signal function; the paper engine fills at the **signal-day close** and live fills at the open (median 0.17 % above the prior close): the restated next-open basis describes live timing, the original basis does not. Already restated beside the originals (G1).
- Live fills vs the same-session open: entries +0.39 % worse on average (standard error 0.60), exits +0.45 % (0.33); fills vs the decision quote +0.03 % (28 orders, worst 0.26 %). Too few trades to say whether the modelled round-trip cost is adequate; no evidence it is not.
- **Paper measures a rule over up to 20 names; the slot buys one** (the first liquid candidate). The fund took the slot's name on only 41 % of the signal sessions checked, because a full research-mode fund cannot buy more. Live results are one draw from what the paper fund averages.
- The ranking's forward basis (same-close, open positions counted) and the honest basis differ without a consistent direction (−0.49 % vs +0.02 %, rank correlation +0.61, 11 of 72 funds positive on one and not the other): a swap would reorder rather than uniformly correct.
- No price stop, partial fill or unfilled order has occurred live, so those paths are covered by tests only. No new code defect was found in D2; the known defects (same-close paper fills, gross-as-net) were already restated or corrected, and the ranking basis stays an owner decision (decision 3 in `docs/AUDIT_BC_FINDINGS.md`).
