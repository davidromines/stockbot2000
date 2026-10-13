# Phase D2: execution realism

Computed 2026-10-13 06:18 UTC, read-only. 37 LIVE slot trades since 2026-09-24 (21 opens, 16 closes, 4 by stand-ins).

## Lifecycle comparison (code-verified; file references in the right-hand column)

| rule | backtest simulator | paper engine (feeds the ranking) | live slot trader | source |
|---|---|---|---|---|
| signal date | newest completed bar | newest completed bar | newest completed bar (shares `paper_trading._genome_signals`) | `paper_trading.py`, `slot_trader._signals` |
| entry fill | next open | **close of the signal session** (no next-open) | first run after the open, ~13:35 UTC, market dollar order | `simulator.py`; `paper_trading.py:616`; `slot_trader.py` |
| strategy exit fill | next open after a trigger | **the triggering close** | next morning's run, at the market | same |
| price stop | ATR stop on the close, filled at the next open | stop checked on closes | checked every 5 min in market hours, no resting stop at the broker | `stop_plans.py`, `slot_trader.monitor` |
| names per signal | all that fire, capped by positions | up to 20 per fund (research mode), most liquid first | **one name per slot**: first candidate by dollar volume not already held | `paper_trading.py`, `slot_trader.trade` |
| cash and settlement | none | none | settled funds and the day-trade limit (limited margin) | `account_rules.py` |
| costs | modelled spread and slippage | modelled; stored beside `pnl_pct`, not deducted in it | actual fills | `costs.py` |
| overlapping names | n/a | the same ticker may sit in many funds | one slot per ticker | `slot_trader.trade` (`taken`) |
| hidden look-ahead | none found | none found: signals use the newest stored session; partial bars are dropped (`backfill.completed_bars`) and the freshness gate fails on data newer than the market | quotes are used for the order only | verified in code |

## E1. Live fills against the next-open assumption

Entries (20 with a stored open): fill vs the same session's open median -0.38 %, mean +0.39 %, 90th percentile +2.66 %; vs the prior close median +0.17 % (this is the gap the same-close paper fill never sees). Exits (15): fill vs open median -0.80 %, vs prior close median -0.17 %.
Signed so that positive means worse than the open: entries +0.39 % (standard error 0.60), exits +0.45 % (standard error 0.33). Both means are within 1.4 standard errors of zero: with this few trades the data cannot separate a systematic shortfall from the random move in the minutes after the open, and neither can show that the modelled round-trip cost is adequate. What is clear: live entries happen at the open, not at the prior close (median +0.17 % above it, spread up to several percent), so the restated next-open basis is the right description of live timing and the original signal-day-close basis is not.

## E2. Fill against the decision-time quote

28 filled orders carry a decision quote: adverse move quote-to-fill mean +0.03 %, median +0.01 %, worst +0.26 %. Orders before the quote was stored (the first week) have none.

## E3. Does the paper fund take the name the slot bought?

17 non-stand-in live entries with a paper fund behind the slot: the fund took the same name on the signal session in 7 (41%); on those signal sessions the fund itself bought a median of 0 names (a research-mode fund holding its 20 positions cannot buy more, while a slot that is empty buys the first liquid name that fires). The paper record averages a rule over up to 20 names entered at once; the slot holds one. The live result of a rule is one draw from the distribution the paper fund measures, with idiosyncratic variance the paper average hides, and the two entry sets only partly coincide.

## E4. The basis the ranking reads for forward evidence

173 funds with >= 20 honest trades. Ranking basis (accounting net per trade, same-close fills, open positions counted at marks): mean -0.49 % vs honest basis (next-open, closed trades) +0.02 %; rank correlation +0.61; 11 of the 72 funds that look positive on the ranking basis are non-positive on the honest basis.

## Defects found, status

| # | defect | evidence | status |
|---|---|---|---|
| 1 | Paper engine fills at the signal-day close and its `pnl_pct` is gross | A1; E1 | restated beside the originals (`paper_trades_restated`, daily); the engine itself is unchanged because the forward record is frozen on entry |
| 2 | The ranking reads the same-close basis and counts open positions in `n` | E4; B3 | **not changed**: E4 shows the two bases differ without a consistent direction (open marks and pending stop-outs push opposite ways), so swapping would reorder rather than uniformly correct; it is owner decision 3 (replace the ranking estimate) after the prospective test |
| 3 | Live buys one name per rule; paper measures the rule over up to 20 | E3 | design difference, recorded; no code change |
| 4 | No price stop has fired live yet | slot trade reasons | stop behaviour (intraday check, gaps) is untested in the real account: unknown |

## What could be wrong with this analysis

- 37 live trades over 13 sessions; the fill statistics are indicative. Prices are adjusted for later dividends, which can shift the vs-open ratios by a few hundredths of a percent.
- The decision quote is stored only from the middle of the live period.
- Parity looks at the fund's entries on the signal session only; a name can enter a fund later at a different price.
- No stop-out, partial fill or unfilled order has occurred live, so those paths are covered by `tests/regression/test_live_paths.py`, not by live evidence.
