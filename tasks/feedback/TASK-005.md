The section is in the right place and the try/except is right, but it fails
acceptance criteria 1 and 2: the output reads "opened ?  weighting ?" and
contains neither the start date nor "not yet rankable".

The cause is the shape of what value_fund.status(conn) returns. It is NOT flat.
It returns:

    {
      "exists": True,
      "fund": {                  <- the database row, nested under this key
          "name": ..., "capital_usd": 100.0, "cash_usd": 100.0,
          "started_on": "2026-09-21", "last_review": None,
          "last_mark": None, "weighting": "equal", "status": "open",
      },
      "positions": [ ... ],      <- list of dicts
      "marks": 0,                <- int, the count of daily equity marks
      "equity": 100.0,
      "return": 0.0,             <- a FRACTION, so format with :+.2%
      "closed_trades": 0,
      "realised_pnl": 0.0,
    }

So the start date is s["fund"]["started_on"], not s["started_on"], and the
weighting is s["fund"]["weighting"]. That is why both print as "?".

Each position dict has keys: ticker, opened_on, entry_price, shares,
industry, thesis, score_at_entry.

Requirements 5 and 7 are also not met. The section must print, when the fund
exists:
  - start date and weighting (from s["fund"])
  - equity against capital with the percent return, e.g.
    "$100.00 on $100.00 (+0.00%)" using s["equity"], s["fund"]["capital_usd"]
    and s["return"]
  - the number of daily marks, s["marks"]
  - the number of open positions, len(s["positions"])
  - and when s["marks"] < 60, a line containing the words "not yet rankable"
    together with the mark count

Keep everything else you wrote, including the closing sentence, which is good.