# TASK-057

- component: research
- priority: high
- state: IN_PROGRESS
- branch: ado/task-057
- created: 2026-09-29T02:05:00+00:00
- dependencies: none

## Objective
Create kalman_pair.py: Stage AA, the Kalman-filter ETF pair mean-reversion strategy (Chan, Algorithmic Trading, Wiley 2013, Example 3.3: EWA/EWC), as pure functions over price frames plus loaders, used for backtests and paper trading by other modules. Two declared modes: "spread" (long one ETF, short the other — research benchmark; this account cannot short) and "long_leg" (buy only the ETF the spread says is cheap — tradeable). Plus its regression test.

## Background
Prices: table prices(ticker TEXT, date TEXT 'YYYY-MM-DD', open REAL, high REAL, low REAL, close REAL, volume REAL), split/dividend adjusted. A trading day is a date present for SPY. Signals are computed on a day's close and fill at the NEXT session's open (the project's fill convention). Costs: charge `cost_bps` basis points of each leg's notional on entry AND on exit. Kalman filter (Chan eq. 3.5-3.13), with x = price of the first ETF augmented with a column of ones, y = price of the second: state beta (2x1, slope then intercept) starts at 0, P = 0 (2x2), Vw = delta/(1-delta) * I, Ve given. Each day t (in order): R = P + Vw; yhat = x_t . beta; Q = x_t R x_t' + Ve; e = y_t - yhat; K = R x_t' / Q; beta = beta + K e; P = R - K x_t R. Record slope, intercept, e and Q for day t using the beta BEFORE the update (the prediction).

## Relevant files
- `kalman_pair.py`
- `tests/regression/test_kalman_pair.py`
## Requirements
1. PAIRS = [("EWA","EWC"), ("GLD","GDX"), ("XLE","XOP"), ("EWU","EWG"), ("XLF","KBE"), ("SPY","RSP")] (declared before any result).
2. kalman(x, y, delta=0.0001, ve=0.001) -> pd.DataFrame indexed like x with columns slope, intercept, e, q (forecast error and its variance) computed as in Background; x and y are aligned pd.Series of closes without NaN.
3. positions(kf, entry_z=1.0) -> pd.Series in {-1, 0, +1}: from flat, enter long (+1) when e < -entry_z*sqrt(q) and enter short (-1) when e > entry_z*sqrt(q); exit long when e >= 0; exit short when e <= 0; otherwise carry the previous state. Position "+1 spread" means long y, short slope units of x.
4. load(conn, a, b, start, end) -> (close, open_): DataFrames indexed by date string with columns a and b, restricted to SPY's dates and dropping dates where either close is missing.
5. backtest(close, open_, a, b, params, start, end, cost_bps=5.0) -> dict. params: {"mode": "spread"|"long_leg", "delta": float, "ve": float, "entry_z": float}. The filter runs on closes from the first available date (warm-up included) but trades are counted only for signal days within [start, end]. A position change decided on day t fills at day t+1's open. mode "spread": a trade is one spread position from entry open to exit open; return = (leg y return - slope_at_entry * price_x_entry/price_y_entry * leg x return) sized so the gross notional is 1, minus costs on both legs. mode "long_leg": +1 spread means buy y only, -1 spread means buy x only (never short); return = that ETF's open-to-open return minus costs. Open trades at the end are closed at the last open. Return {"trades": list of dicts (entry_date, exit_date, side, ret_gross, ret_net), "n_trades", "mean_net", "mean_gross", "win_rate", "avg_hold" (sessions), "equity": pd.Series (compounded trade returns, one position at a time), "cagr", "max_drawdown" (positive fraction)}.
6. main(argv=None): --backtest --pair EWA,EWC --mode long_leg [--start 2006-07-01] [--end 2012-12-31] [--delta 0.0001 --ve 0.001 --entry-z 1.0] prints n_trades, mean gross and net per trade, win rate, avg hold, CAGR, max drawdown; --all runs every PAIRS entry in both modes over 2006-07-01..2012-12-31 and 2013-01-01..today and prints one line per (pair, mode, window). Import runtime first; sqlite3.connect("file:<market_data_path>?mode=ro", uri=True); from universe import load_config inside main.

## Constraints
1. Create ONLY kalman_pair.py and tests/regression/test_kalman_pair.py. Modify nothing else.
2. kalman_pair.py under 230 lines; test under 170 lines. pandas and numpy only.
3. The test uses synthetic prices: x a random walk (seeded numpy RandomState), y = 1.5 * x + 10 + stationary noise (AR(1) with coefficient 0.8), ~600 business days; plus an in-memory sqlite3 prices table for load().
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_kalman_pair.py exits 0.
2. The test checks: on the synthetic cointegrated pair the filter's slope converges near 1.5 (within 0.2 over the last 100 days); e has mean near 0; positions only take values -1/0/+1 and switch from 0 to +1 only when e < -sqrt(q); backtest trades fill at the open of the day after the signal day; mean_net < mean_gross; mode long_leg never records a short side; the spread return is exact on a hand-made move (long gains and short loses when y recovers against x; sized on both legs' notional) — changed in review 2026-09-29: a synthetic "must make money" check depends on noise vs filter settings, not on the code; max_drawdown is between 0 and 1; load() keeps only dates with both closes and SPY present.
3. At least 10 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
