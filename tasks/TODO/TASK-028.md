# TASK-028

- component: research
- priority: high
- state: TODO
- branch: ado/task-028
- created: 2026-09-25T15:40:00+00:00
- dependencies: none

## Objective
Create crypto_trend.py (Stage K3): the single simulation engine for low-turnover daily crypto strategies (trend_sma, tsmom, breakout) with a mandatory ATR stop, next-bar-open fills, spread costs, a deterministic null and buy-and-hold, plus its regression test.

## Background
Robinhood crypto costs ~1.9% round trip, so only low-turnover rules can survive. This engine is shared by backtests and the forward paper fund, so it must be exact. Inputs are numpy float arrays o, h, l, c of equal length N (daily bars, oldest first). A genome g is a dict: family in {"trend_sma", "tsmom", "breakout"}, n (int lookback), stop_atr (float > 0), optional atr_n (default 14). Entry signal at bar i uses data up to and including bar i: trend_sma: c[i] > mean(c[i-n+1..i]), defined for i >= n-1; tsmom: c[i] / c[i-n] - 1 > 0, defined for i >= n; breakout: c[i] > max(h[i-n..i-1]), defined for i >= n. Exit signal at bar i: trend_sma and tsmom: the entry condition is False (and defined); breakout: c[i] < min(l[i-m..i-1]) with m = max(2, n // 2), defined for i >= m. ATR at bar i = mean of true range over bars i-atr_n+1..i, true range = max(h-l, abs(h - c_prev), abs(l - c_prev)) with c_prev the previous close (bar 0 uses h-l); NaN until atr_n bars exist. FILLS: a signal at the close of bar i fills at o[i+1], never at c[i]. Entry: when flat, entry signal True at bar i, ATR[i] finite, i >= start_i, i+1 < N, and not waiting for reset: enter at bar e = i+1 at price o[e]; stop = o[e] - stop_atr * ATR[i]. While in a position, for each bar j from e onwards, in this order: (1) if l[j] <= stop: exit at bar j at price min(o[j], stop) (a gap below the stop fills at the open), reason "stop", and set waiting-for-reset; (2) else if the exit signal is True at bar j and j+1 < N: exit at bar j+1 at o[j+1], reason "signal". After an exit at bar x, the position is flat and entry checking resumes with the signal at bar x (so a fill at o[x+1] at the earliest). Waiting-for-reset is cleared at the first bar whose entry signal is False (defined); while set, no entry. At the end, a position still open is closed at c[N-1] with reason "end" if close_at_end, otherwise returned as open. COSTS: hs is a fraction charged per side: net = exit_px * (1 - hs) / (entry_px * (1 + hs)) - 1; gross = exit_px / entry_px - 1.

## Relevant files
- `crypto_trend.py`
- `tests/regression/test_crypto_trend.py`
## Requirements
1. FAMILIES = ("trend_sma", "tsmom", "breakout") and a function signals(o, h, l, c, g) returning (entry_bool_array, exit_bool_array, defined_bool_array) implementing the Background definitions; undefined bars are False in both signal arrays.
2. atr(h, l, c, n=14) returning the ATR array as defined in Background.
3. simulate(o, h, l, c, g, hs, start_i=0, close_at_end=True) returning {"trades": [...], "open": None or dict}; each trade dict has entry_i, exit_i, entry_px, exit_px, stop, reason, bars (= exit_i - entry_i), gross, net; the open dict has entry_i, entry_px, stop.
4. null_per_trade(o, trades, hs, lo_i, hi_i) returning the mean over trades of: the mean over every j in [lo_i, hi_i - bars] of o[j+bars] * (1 - hs) / (o[j] * (1 + hs)) - 1, using max(1, bars) as bars; trades with no valid j are skipped; returns None when no trade contributes.
5. buy_and_hold(o, c, lo_i, hi_i, hs) returning c[hi_i] * (1 - hs) / (o[lo_i] * (1 + hs)) - 1.
6. summarize(trades) returning {"trades": n, "gross_per_trade": mean gross, "net_per_trade": mean net, "win_rate": share with net > 0, "mean_bars": mean bars}, with None values when there are no trades.
7. A module docstring stating the fill convention (signal at close, fill at next open; stops fill at min(open, stop)) and the cost formula. Import runtime first, then numpy only.

## Constraints
1. Create ONLY the two files this task names. Modify nothing else.
2. No database, no network, no pandas in crypto_trend.py.
3. Keep crypto_trend.py under 230 lines and the test under 200 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does, then import crypto_trend.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_trend.py exits 0.
2. The test builds small synthetic price arrays by hand and checks: an entry fills at o[i+1], not c[i]; a signal exit fills at the next bar's open; a stop with the open below the stop fills at the open (gap-through); a stop with the open above the stop fills at the stop; no entry from a signal before start_i; after a stop no re-entry until the entry signal has been False once; close_at_end False returns an open position; net equals the Background cost formula for hs 0.01; null_per_trade on a constant-price series equals (1-hs)/(1+hs) - 1; buy_and_hold matches its formula.
3. At least 10 lines beginning with `  PASS`.
4. ./run_tests.sh reports ALL PASS.
