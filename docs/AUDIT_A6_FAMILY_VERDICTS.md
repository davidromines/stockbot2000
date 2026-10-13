# Audit A6 — provisional verdicts for the eight forward-positive families (2026-10-13)

Source: `reports/audit_selection_2026-10-13.md` (A4–A5) and `reports/audit_forward_2026-10-13.md` (A1–A3).
Basis: net of modelled costs, next-open fills on adjusted prices (`paper_trades_restated`, v2_next_open), date-clustered
statistics, SPY subtracted where stated. Read-only; nothing here changes a slot, a ranking or a risk limit.

## Evidence classes used

| class | meaning |
|---|---|
| Unresolved | fewer than 20 independent entry dates (or no adjusted result) — the data cannot confirm or reject |
| Not supported | enough dates and the honest net result is not positive |
| Promising | enough dates, date-cluster t at the family luck level, bootstrap lower bound above zero (never reached) |

No family is called "eligible" or "supported" by this audit; the strongest label available is "Promising" and none earns it.

## Verdicts

| family | trades | indep. dates (prospective) | honest net % (all / prospective) | excess vs SPY % (prospective) | max-T adj p | class | what changed it from "looks positive" |
|---|---:|---:|---:|---:|---:|---|---|
| lab_search | 7,941 | 10 (9) | +0.90 / +0.48 | +0.19 | 1.00 | Unresolved | +1.63 % on 2,886 trades was a 09-24 replay created 09-27; remove it and the excess over SPY is +0.19 % on 9 dates. The t of 17 was trade-level on 5,560 trades that share ~10 dates. |
| momentum | 392 | 18 (17) | +1.71 / +0.70 | +0.56 | 0.99 | Unresolved | 71 retro trades at +6.27 %; prospective t +0.7 on 17 dates. Closest to 20 dates. |
| kf_seasonality | 624 | 8 (8) | +0.11 / +0.03 | −0.31 | 1.00 | Unresolved | Honest net ≈ 0; trails SPY. The earlier t of 7.1 was one-date clusters. |
| st_uptrend_pullback | 624 | 8 (7) | +0.19 / −1.38 | −2.00 | 1.00 | Not supported (provisional) | Prospective result is negative and below SPY; 37 % of trades were the replay. Only 7 dates, so not yet a rejection. |
| bollinger_reversion | 370 | 5 (4) | +0.45 / +1.30 | +0.41 | 0.62 | Unresolved | 4 prospective dates; the only family with a prospective cluster t near 2 (+2.0, df 3) — a df of 3 is not a result. |
| kf_mean_reversion | 123 | 7 (6) | +1.71 / +1.85 | +1.25 | 0.98 | Unresolved | Positive and above SPY, but 6 dates and t +1.4. Thin. |
| st_momentum_1d | 1,116 | 10 (9) | −0.39 / −0.25 | −0.57 | 1.00 | Not supported (provisional) | Negative on the honest basis and below SPY (t −2.0 on excess). |
| turn_of_month | 160 | 2 (2) | +1.86 / +1.86 | +0.51 | n/a | Unresolved | Two entry dates; calendar rule by construction clusters on few dates. |

Across all 31 families with >= 5 shared dates: effective independent tests ≈ 28; after Holm / BH none of 14 reported
families is significant (smallest adjusted p 0.744, lab_search, all trades). Removing the 09-24 replay leaves no family
with a max-T adjusted p below 0.14.

## What would change each verdict

| to move toward "Promising" a family needs | to be dropped |
|---|---|
| >= 20 independent entry dates of its own on the restated honest basis | prospective excess over SPY stays below zero at >= 20 dates |
| date-cluster t at or above the family-level luck bar (3.25 for 88 families; recomputed when the family count changes) | bootstrap upper bound of the absolute honest mean below zero |
| bootstrap lower bound of the absolute net mean above zero, AND a positive mean excess over SPY | — |
| max-T adjusted p <= 0.05 across the registered families | — |

## The prospective test (registered, not yet started)

`prospective_eval.py` registered `forward_families_prospective` v1 in `experiment_registry` on 2026-10-13 05:25 UTC. The
pass rule is the right-hand column above, fixed and unchangeable (the registry refuses edits to locked fields):

- 8 families, funds created before registration only; no additions, no redefinitions
- entries dated 2026-10-12 or later (first entries whose next-open fill is after registration)
- first 20 pooled independent entry dates, evaluated 15 sessions after the 20th; open positions marked at the newest open and included
- a family passes if: >= 12 own dates, mean excess over SPY > 0, max-T adjusted p <= 0.05, bootstrap lower bound > 0
- one evaluation; interim looks (`./venv/bin/python prospective_eval.py`) are labelled INTERIM and decide nothing
- expected evaluation window: about 20 trading days of entries + 15 sessions ≈ early-to-mid December 2026

A pass is evidence worth a longer test, not proof of profitability; it does not change any live setting.

## Limits of this verdict

- 4–18 effective dates, one market regime; p-values with 3–17 degrees of freedom are fragile.
- SPY is a crude benchmark for a stock-picking family (no beta or sector adjustment).
- The restated table leaves out trades that exit on the newest bar (mostly stop-outs), which flatters every family until restated.
- "Not supported (provisional)" is a statement about the data so far, not a final rejection.
