Round 1 truncated at the 8,000-token output cap (nothing written); round 2 compact.
Module logic (period-date year-ago match, prior-only sd) correct. REAL BUG fixed by Claude:
project() compared ISO price dates ('2020-05-07') with compact 'YYYYMMDD' strings — '-'
sorts before every digit, so every trading day looked unavailable and NOTHING would have
been written on the real data; and _d() crashed on ISO dates. The test hid it by writing
prices as YYYYMMDD. Tests rebuilt with realistic fixtures (enough history for 4 prior
deltas, filing dates after quarter ends, ISO price dates).
