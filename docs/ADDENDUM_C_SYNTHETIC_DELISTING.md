# Addendum C — Survivorship-bias-free universe reconstruction (revision 2)

**Revision 2, 2026-09-24.** Supersedes revision 1 (same day), which narrowed
the request to appending a delisting return to S&P 500 names in FINSABER. The
user corrected the scope: the goal is to reconstruct the full US equity
universe, including the ~7,000 delisted companies with no free price history,
with conditional synthetic price histories rigorously tagged as synthetic.
Revision 1 remains in git history. Revision 1 also assumed merger delisting
returns of about +20%, which was wrong — see the spec below.

Integration, the feasibility statement, the verified free sources, the staged
plan and the clarifying questions are in `ROADMAP_INTEGRATION.md`, Stage J.

**Status: PLANNED — not to be built until the user confirms the staged plan
and answers the clarifying questions, as this spec itself requires.**

Synthetic data here is for survivorship-bias correction, not a substitute for
real data. Results that rest on it carry wider error bars.

---

The user's specification, verbatim:

I need you to design and build a system that reconstructs a survivorship-bias-free historical price database for US equities, using conditional synthetic data to fill gaps where real data is unavailable. This is for a backtesting system I intend to trust, so the synthetic portions must be empirically grounded, reproducible, and rigorously tagged as synthetic.
Read this framing carefully before proposing anything.
The goal is NOT to fill the last row for S&P 500 delistings. The goal is to reconstruct a historical price universe for the full US equity market (roughly 1990–2024) that includes the approximately 7,000 delisted companies for which no free price history exists. Real delisting data cannot be obtained for free. Therefore we will generate conditional synthetic price histories for the missing symbols, grounded in empirical regularities observable from the symbols we do have data for. Every synthetic row must be tagged. Real rows must never be modified. The output must support backtests that can toggle synthetic data on and off and stress-test the delisting assumption.
This is a legitimate use of synthetic data for bias correction, not a substitute for real data. Your plan must state that distinction explicitly.
The data landscape:

* What I have: FINSABER S&P 500 CSV (`all_sp500_prices_2000_2024_delisted_include.csv`), which includes ~253 MB of daily OHLCV for S&P 500 constituents, including those that were later delisted, up to (but not including) their delisting events. Columns: `date, symbol, open, high, low, close, adjusted_close, volume`.
* What I'm missing: Price histories for the full US equity universe, especially the ~7,000 delisted companies outside the S&P 500. Also missing: delisting dates, delisting reasons, and delisting returns for most symbols.
* What I might be able to obtain for free (investigate and use if viable): symbol lists from SEC EDGAR filings metadata, the FinanceDatabase project's delisted-ticker list, historical exchange listing data, and any other free structured sources you can identify. These give the universe, not the prices.

Required architecture — two layers:
Layer A — Universe reconstruction.
Identify every US-listed common stock that existed at any point between 1990 and 2024, including delisted ones. For each symbol, produce a record with: symbol, company name (if known), exchange, sector (if known), approximate IPO date, approximate delisting date (if delisted), delisting reason (if known), and a provenance flag for each field indicating whether it came from a real source or was imputed. Where delisting reasons are unknown, leave them null rather than guessing—Layer B will infer them.
Layer B — Conditional synthetic price history generation.
For every symbol in the universe that lacks real price data, generate a synthetic daily OHLCV history conditioned on everything known about that symbol, calibrated to empirical regularities observed in the real data I have. Do not use a generic stochastic process (GBM, Heston, etc.). Use cohort-based empirical sampling.
Cohort definition — symbols should be grouped by combinations of:

* Sector (if known)
* Market-cap bucket at IPO or first observation
* Exchange (NYSE, NASDAQ, AMEX)
* Decade of IPO
* Delisting reason class: `merger`, `bankruptcy`, `performance`, `voluntary`, `unknown` — inferred from price behavior where not known

Empirical calibration — for each cohort, compute from real data (FINSABER and any other free real data you can assemble):

* Distribution of daily returns (mean, variance, skew, kurtosis)
* Distribution of annualized volatility
* Distribution of maximum drawdowns
* Correlation with the broader market
* Distribution of time-to-delisting from IPO
* Distribution of delisting returns, by reason class

Then generate synthetic paths that match these distributions. For symbols with partial real history (e.g., FINSABER delisted names that have data up to the delisting date), generate only the missing tail—do not overwrite real data.
Delisting return patterns (empirical, cited):
From Shumway (1997), Shumway & Warther (1999), Beaver, McNichols & Price (2007):

* NYSE/AMEX performance delistings: mean -41.7%
* NASDAQ performance delistings: mean -16.3%
* ~25% of episodes below -96%
* ~5% below -99%
* Merger/acquisition delistings: typically near zero as a delisting return, because the takeover premium is already in the price path before trading stops. Make this configurable; the previous plan's +20% assumption was wrong for this reason.
* Voluntary delistings: small, roughly N(0, 0.1)

Model each reason class as a mixture distribution or bootstrap from empirical quantiles. Do not use a normal distribution for performance or bankruptcy delistings.
Time variation: Delisting severity varies with the cycle. 2000–2002 and 2008–2009 saw more severe performance delistings. Condition the mixture weights on trailing market returns or VIX levels if you can source them; otherwise document this as a limitation.
Reverse-split trap: Failing companies often reverse-split before delisting. If your generator produces a raw return without handling this, you'll create fake +900% gains. Use `adjusted_close` where available, and explicitly detect and handle splits in raw data.
Mandatory data provenance tagging:
Every row in the output database must carry:

* `is_synthetic`: boolean. `True` for any generated row, `False` only for rows sourced directly from real data.
* `data_source`: string. One of `"real_finsaber"`, `"real_other"`, `"synthetic_path"`, `"synthetic_delisting"`.
* `cohort_id`: nullable string, present only for synthetic rows, identifying the cohort used.
* `generation_method`: nullable string, describing the sampling method.
* `synthetic_reason`: nullable string, inferred delisting reason for synthetic rows.
* `synthetic_seed`: nullable integer, so any synthetic row can be regenerated.

Never overwrite or modify a real row. If you need to append a synthetic delisting observation to a real symbol's history, keep the real rows intact and append a new row tagged as synthetic. If a symbol has partial real history, fill only the missing portion.
Add a validation check that asserts: no `is_synthetic=False` row has a null `data_source`; no `data_source="synthetic_*"` row has `is_synthetic=False`; every synthetic row has a non-null `synthetic_seed`. Fail loudly on inconsistency.
Deliverables:

1. Universe construction script — assembles the full symbol list from available free sources, produces the Layer A records with per-field provenance.
2. Cohort analysis script — computes empirical statistics from real data, organized by cohort, and saves them as a versioned artifact so synthetic generation is reproducible and auditable.
3. Synthetic path generator — samples from cohort statistics to produce synthetic OHLCV histories for missing symbols, with all provenance tags.
4. Integration script — merges real FINSABER data with synthetic data into a single tagged DataFrame. Real rows pass through untouched. Synthetic rows are appended. Output as parquet or similar.
5. Backtest loader — a function `load_backtest_data(path, synthetic_mode=...)` supporting:
   * `"as_is"` — use synthetic rows as generated
   * `"exclude"` — drop all synthetic rows (survivorship-biased baseline for comparison)
   * `"zero"` — replace synthetic delisting returns with -100%
   * `"optimistic"` — replace synthetic delisting returns with 0%
   * `"real_only"` — use only rows where `is_synthetic=False` for every field
6. Validation and sensitivity harness:
   * Compare aggregate statistics of the synthetic universe (returns, volatility, drawdowns, delisting returns) against the real subset. Flag systematic bias.
   * QQ plots for return distributions.
   * Report the synthetic share of the final dataset by year, by sector, and by symbol, so I always know how much of any result rests on imputed data.
   * Confirm provenance tagging integrity.
7. README documenting every assumption with citations, every known limitation, and a clear statement that synthetic data is being used for survivorship-bias correction—not as a substitute for real data—and that results carry wider error bars because of it.

Constraints:

* Do not use generic stochastic processes for price or delisting returns. Use empirical sampling from real cohorts.
* Do not invent data. If a parameter must be guessed, expose it as a configurable argument with a documented default and cite the basis.
* Everything must be reproducible with a random seed.
* Provenance tagging is not optional. If provenance is uncertain for a field, tag it as synthetic and flag it for review.
* Before writing code, produce a staged plan: Stage 1 universe reconstruction; Stage 2 cohort analysis; Stage 3 synthetic path generation; Stage 4 provenance and integration; Stage 5 validation and sensitivity harness. Confirm the plan with me before building.

Before you write any code, ask me clarifying questions. I'd rather answer five questions than debug a misaligned build.
One last thing: the previous plan you sketched for this project was too narrow—it addressed only S&P 500 delisting returns. The scope here is the full US equity universe. If you believe that scope is infeasible with free data, say so explicitly and propose what is feasible, rather than quietly narrowing the plan.
Notes on using this prompt:
The last paragraph is deliberate. Claude will likely feel the pull to narrow scope back to something tractable, and you want that pressure to surface as an explicit statement rather than a silent compromise. If it tells you the full universe is infeasible, that's useful information—you can then negotiate down to "full universe from 2000 onward" or "all delisted S&P 1500 names" with eyes open.
Also watch for Claude proposing a specific free source for the symbol universe. SEC EDGAR is real and accessible; FinanceDatabase is real; other sources it names may or may not exist. Ask it to verify each source is currently accessible before the plan depends on it.
This response is AI-generated, for reference only.
