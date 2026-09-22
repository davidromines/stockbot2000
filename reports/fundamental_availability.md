# Fundamental availability audit

Generated: 2026-09-22T06:43:50Z
Database: `data/market_data.db`

## Verdict

**FAIL — correctness defects found.**

- 3 fundamentals rows have a filing date *before* the period they report.

## fundamentals

| metric | value |
|---|---|
| total rows | 212933 |
| with filed date | 212933 |
| missing filed date | 0 |
| negative lag rows | 3 |

Rows with a NULL `filed` cannot be used point-in-time at all and must be excluded from any value screen.

### Filing lag (filed - period), days

| metric | value |
|---|---|
| min | -237 |
| median | 40.0 |
| max | 4018 |
| rows measured | 212933 |
| unparseable dates | 0 |

### Negative lag examples

| ticker | filed | period | lag_days |
|---|---|---|---|
| LGNZZ | 2014-12-01 | 2014-12-31 | -30 |
| PW-PA | 2024-05-10 | 2024-12-31 | -235 |
| SDCH | 2014-02-05 | 2014-09-30 | -237 |

### Coverage by filing year

| year | rows | distinct tickers |
|---|---|---|
| 2009 | 592 | 304 |
| 2010 | 2170 | 800 |
| 2011 | 6112 | 2313 |
| 2012 | 9784 | 2444 |
| 2013 | 10101 | 2545 |
| 2014 | 10666 | 2684 |
| 2015 | 11218 | 2824 |
| 2016 | 11376 | 2919 |
| 2017 | 12176 | 3049 |
| 2018 | 12746 | 3205 |
| 2019 | 13266 | 3355 |
| 2020 | 13997 | 3570 |
| 2021 | 15805 | 4034 |
| 2022 | 17074 | 4278 |
| 2023 | 17815 | 4431 |
| 2024 | 18452 | 4618 |
| 2025 | 19406 | 4892 |
| 2026 | 10177 | 5062 |

## daily_fundamentals

| metric | value |
|---|---|
| total rows | 10185236 |
| min days_since_filing | 2 |
| max days_since_filing | 5280 |
| negative or NULL lag | 0 |
| negative lag | 0 |
| NULL lag | 0 |

Negative or NULL `days_since_filing` rows are look-ahead: the value cannot be shown to have been public on the row's own date.
