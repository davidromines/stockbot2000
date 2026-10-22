# Options without the $100 cap — 2026-10-22 (`options_liquid_v1`)

One long call or put per trade, bought at the ask and sold at the bid, 2020 onward. A = no price cap; B = no cap and an entry gap of at most 5% of the mid (the test that decides).

| strategy | A: trades | A: mean | B: trades | B: mean | B: median | B: win | B: t | B: years + | B: contract (median) | B: $ per contract | pass |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 52-week high breakout call | 581 | -5.7% | 254 | -2.5% | -33.8% | 38% | -0.4 | 2/7 | $655 | $-89 | no |
| Insider buying call | 391 | +9.7% | 194 | +22.3% | -39.6% | 34% | +1.9 | 5/7 | $535 | $+205 | no |
| Rising-IV call | 359 | -16.5% | 164 | -9.4% | -39.7% | 35% | -1.1 | 1/4 | $705 | $-116 | no |
| Expensive-call call | 842 | -5.3% | 393 | +5.1% | -13.5% | 45% | +1.0 | 5/7 | $650 | $+67 | no |
| Expensive-put put | 859 | -8.9% | 473 | -1.9% | -23.3% | 33% | -0.3 | 1/7 | $790 | $+31 | no |
| Oversold call (mean reversion) | 511 | -9.9% | 115 | +9.3% | -32.3% | 41% | +0.7 | 4/7 | $435 | $+286 | no |
| Post-earnings drift call | 79 | -6.4% | 62 | -14.4% | -60.4% | 32% | -1.1 | 2/7 | $930 | $-716 | no |
| Stock signal → call | 768 | -14.3% | 235 | +2.0% | -21.4% | 37% | +0.3 | 3/7 | $640 | $-65 | no |
| Stock signal → call (cheap IV) | 606 | -12.3% | 201 | +4.6% | -17.3% | 37% | +0.7 | 3/7 | $680 | $-92 | no |
| Steep-smirk put | 610 | -19.9% | 292 | -18.3% | -45.3% | 29% | -2.9 | 1/7 | $825 | $-226 | no |

**Under B: 0 of 10 pass.** No long call/put strategy makes money by more than noise even when only tight-gap contracts are bought.
