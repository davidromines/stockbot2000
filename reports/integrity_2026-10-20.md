# Data integrity — 2026-10-20 (Stage AD1)

## 1. Fill conventions

| layer | entry fill | exit fill |
|---|---|---|
| simulator / backtests | next open | next open after the triggering close |
| paper engine (original record) | signal-day close | triggering close |
| paper record, restated (`paper_trades_restated`) | next open | next open |
| live slots | market order at or after the open | market order when a 5-minute check fires |

Restated: 31,202 of 35,304 closed paper trades (88%); the rest exit on the newest bar and have no next open yet. Decision layers (allocator, prospective test, funnel honest column) read the restated record. The paper engine's own convention is unchanged (a separate, careful change: it must defer orders across daily runs).

## 2. Corporate actions

219 restated trades (0.70%) carry the corporate-action flag (an implausible one-trade move consistent with an adjusted/unadjusted price mismatch). Most frequent: VZ 89, CMCSA 29, CTVA 9, ARE 9, MRP 5. Flagged trades are excluded from the restated statistics; the originals are kept.

## 3. Live ledger

Equity change -5.61; ledger realised -6.84 + unrealised +1.22; gap +0.01 (dividends, cash interest and fractional rounding are not in the trade ledger; to be matched against Robinhood's realised-P&L and dividend records).

## 4. Backups

Every expected forward/decision table present is in the nightly backup.

## 5. Survivorship dispersion (for risk-adjusted ranking)

4,188 of 8,613 backtest rows carry sd per trade. Run `survivorship_backtest.py --refill` once to complete it.

## 6. Prospective test

Entries from 2026-10-12: 3,187 trades (1592 still open, marked) on 3 pooled entry dates; the test needs 20 and is evaluated 15 sessions after the 20th. Latest stored session 2026-10-16.

## 7. Live fill quality

27 buys with a stored decision-time quote: average fill +0.025% against it.

## 8. Sign-in

Last full Robinhood sign-in 15 days ago (renewal warning from 20 days).

