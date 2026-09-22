Requirements 1 to 4 are correct — candidates() now defaults limit to None and
the docstring explains the alphabetical cut. Keep all of that.

Requirement 5 is not met, and acceptance criterion 2 fails with a KeyError.

coverage() currently returns:

    {'as_of': '2026-09-21', 'eligible': 5251}

It must return a dict containing these two keys with these exact names:

    "universe"      count of DISTINCT tickers in sec_filings where ticker is
                    not null and first_tradeable is not null and
                    first_tradeable <= as_of
    "common_stock"  how many of those tickers satisfy is_common_stock()

You may keep "as_of" and "eligible" as well — extra keys are fine. What
matters is that both "universe" and "common_stock" are present, because
requirement 7 prints both and the acceptance check reads both by name.

The distinction is the point of the function: "universe" is everything that
filed, "common_stock" is the subset the fund may actually buy. Collapsing
them into a single "eligible" count loses exactly the comparison a reader
needs — how much of what filed is investable.

Concretely, the check that must pass is:

    d = value_fund.coverage(c, '2026-09-21')
    print(d['universe'] > 5000, d['common_stock'] > 0,
          d['common_stock'] <= d['universe'])

and it must print: True True True

Also confirm requirement 7 prints BOTH numbers in the review output.