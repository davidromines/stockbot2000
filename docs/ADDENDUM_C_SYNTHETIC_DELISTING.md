# Addendum C — Synthetic delisting returns for FINSABER

Supplied by the user on 2026-09-24 and reproduced verbatim below. Integration
against the existing survivorship work, and the questions to settle before
code, are in `ROADMAP_INTEGRATION.md`, Stage J.

**Status: PLANNED — entered 2026-09-24. Not to be built until the user says
so.** It depends on the FINSABER CSV being downloaded (Phase 13 step H6,
awaiting an explicit go-ahead).

---

need you to build a Python module that generates synthetic delisting returns to fill gaps in the FINSABER S&P 500 dataset (`all_sp500_prices_2000_2024_delisted_include.csv`). This is for a survivorship-bias-corrected backtest, so the synthetic data must reproduce known empirical patterns of real delistings—not generic random returns.
Critical requirement: data provenance tagging.
Every row in the output database must be explicitly tagged as either `real` or `synthetic`. This is non-negotiable. Downstream code (backtests, analysis, reporting) must be able to filter, exclude, or separately report on synthetic rows at will. Never silently mix synthetic data with real data.
Context on the data:
The FINSABER CSV has columns: `date, symbol, open, high, low, close, adjusted_close, volume`. It includes delisted symbols with price history up to (but not including) the delisting event. The delisting return itself is missing.
The empirical patterns you must reproduce:

1. Delisting returns are not normal. They are heavily left-skewed and fat-tailed. Key statistics from the academic literature (Shumway 1997, Shumway & Warther 1999, Beaver, McNichols & Price 2007):
   * NYSE/AMEX average delisting return for performance-related delistings: -41.7%
   * NASDAQ average: -16.3%
   * ~25% of delisting episodes have returns below -96%
   * ~5% have returns below -99%
   * A meaningful fraction (mergers, acquisitions) are positive, typically +10% to +40%
2. Delisting returns depend on the reason. Use these categories with approximate probability weights for S&P 500 constituents (adjust if you find better data):
   * Merger/Acquisition (~60-70% of S&P 500 delistings): positive return, typically +10% to +40%, low variance. Model as normal or lognormal centered around +20%.
   * Bankruptcy/Liquidation (~5-10%): return near -100%. Model as a point mass at -1.0 or a tight distribution between -0.95 and -1.0.
   * Performance-related delisting (~15-25%): use the Shumway-style empirical distribution. A mixture model works well: ~70% mass in [-0.6, -0.1], ~25% mass in [-0.99, -0.6], ~5% mass at -1.0.
   * Voluntary/Other (~5-10%): small positive or slightly negative, roughly N(0, 0.1).
3. Time variation. Delisting return severity varies with the business cycle and market conditions. During 2008-2009 and 2000-2002, performance delistings were more severe and more frequent. You may condition the mixture weights on the VIX level or trailing 12-month market return if you can fetch that data; otherwise, note this as a limitation.
4. The "reverse split trap." Failing companies often do reverse splits shortly before delisting. If your synthetic generator produces a raw return without accounting for this, you will create fake +900% gains. Ensure the adjusted_close series is used for return calculation, or explicitly detect and handle splits in the raw data before generating delisting returns.

What I want you to produce:

1. A Python module `synthetic_delisting.py` with:
   * A function `classify_delisting(symbol, last_date, price_history)` that assigns a probable delisting reason based on available signals (price level, volatility, recent returns, volume decline). Use heuristics if you have no metadata; document them clearly.
   * A function `generate_delisting_return(reason, date, market_context=None)` that samples from the appropriate distribution.
   * A function `apply_to_finsaber(df, seed=42)` that takes the FINSABER DataFrame, detects the last trading day for each delisted symbol, generates a delisting return, and appends a synthetic final row or adjusts the final return.
   * Full docstrings with citations for each distributional assumption.
2. Data provenance tagging (mandatory):
   * Add two columns to the output DataFrame: `data_source` and `is_synthetic`.
      * `data_source`: string, one of `"finsaber_real"`, `"synthetic_delisting"`, or `"synthetic_imputed_price"` (if you impute any prices rather than just delisting returns).
      * `is_synthetic`: boolean, `True` for any row not sourced directly from the FINSABER CSV.
   * Every row that came from FINSABER must be tagged `data_source="finsaber_real"` and `is_synthetic=False`.
   * Every row you generate must be tagged `data_source="synthetic_delisting"` and `is_synthetic=True`.
   * Add a `synthetic_reason` column (nullable) that records the inferred delisting category (`merger`, `bankruptcy`, `performance`, `voluntary`) for synthetic rows. Leave null for real rows.
   * Add a `synthetic_seed` column (nullable) recording the random seed used, so any synthetic row can be regenerated.
   * Never overwrite or modify a real row's price data. If you need to adjust the final real row (e.g., to append a synthetic delisting return as a new row), keep the original real row intact and append a new synthetic row with its own date.
3. A validation script that:
   * Runs the generator and produces summary statistics of the synthetic delisting returns.
   * Compares these to the target empirical statistics listed above.
   * Plots the distribution (histogram + QQ plot against the Shumway empirical distribution if you can approximate it).
   * Flags any synthetic return that looks implausible (e.g., a "bankruptcy" with a +50% return).
   * Verifies provenance integrity: asserts that no row with `is_synthetic=False` has a null `data_source`, and that no row with `data_source="synthetic_delisting"` has `is_synthetic=False`. Fail loudly if the tagging is inconsistent.
4. A backtesting integration helper with:
   * A function `load_backtest_data(path, include_synthetic=True, synthetic_mode="as_is")` where `synthetic_mode` accepts:
      * `"as_is"` — use synthetic rows as generated.
      * `"exclude"` — drop all synthetic rows (this reproduces the survivorship-biased baseline for comparison).
      * `"zero"` — replace synthetic delisting returns with -100% (worst-case stress test).
      * `"optimistic"` — replace synthetic delisting returns with 0% (best-case stress test).
   * This lets me run the same strategy under four different data assumptions and compare results directly.
5. A README section documenting:
   * Every assumption made and its source.
   * Known limitations (e.g., "we cannot observe delisting reasons in FINSABER, so we infer them from price behavior").
   * How to run sensitivity tests (e.g., re-run the backtest with all delistings forced to -100% and with all forced to -30% to bound the strategy's performance).
   * A clear statement of what fraction of the final dataset is synthetic, broken down by symbol and by year, so I always know how much of any given result rests on imputed data.

Constraints:

* Do not use a generic stochastic process (GBM, Heston, etc.) for delisting returns. Use empirical mixture distributions or bootstrapping from published summary statistics.
* Do not invent data you cannot justify. If you must guess a parameter, say so explicitly and make it a configurable argument.
* The output must be reproducible with a random seed.
* Assume the user (me) will run this against the FINSABER CSV and then backtest a trading strategy on the result.
* Provenance tagging is not optional. If you cannot determine whether a row is real or synthetic, tag it as synthetic and flag it for review.

Optional, if you can find or approximate it:
Bootstrapping from actual delisting returns would be better than parametric sampling. If you can locate a public source of individual delisting returns (even a small sample), use it to build an empirical CDF and sample from that instead.
Ask me clarifying questions before writing code if anything is ambiguous.
