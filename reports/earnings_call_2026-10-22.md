# Earnings beat → in-the-money call — 2026-10-22 (`earnings_itm_call_v1`)

**Prediction, out of sample (2020 on, 50,441 reports):** beat rate 55% overall, 69% in the model's top fifth, 74% for the last-surprise rule alone.

Trades: 105 of 9,625 reports with an SEC release date and option data (75 without an exit quote, not counted). One call, delta 0.70-0.80, gap <= 5%, bought 5 sessions before the report at the ask, sold 1 session after at the bid.

| selection | trades | beat rate | mean per trade | median | win | t | years + | stock same days | vs leverage-matched stock | contract | $ per contract | pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| model top fifth (decides) | 16 | 94% | -4.1% | -3.0% | 50% | -0.3 | 4/7 | -0.8% | -6.4% | $2,560 | $-1,247 | no |
| last-surprise rule | 8 | — | — | — | — | — | —/— | — | — | — | — | no |
| every report | 30 | 83% | -10.8% | -35.5% | 40% | -1.0 | 2/7 | -1.9% | -2.7% | $2,388 | $-1,087 | no |

**FAIL** under the pre-registered rule (mean > 0, t >= 2.8, positive in at least half the years, better than the leverage-matched stock).

Caveats: a 'beat' is EPS against the same quarter a year earlier, not the analysts' consensus; trades need an SEC 8-K release date; option quotes are end-of-day; one test window (2020 on).
