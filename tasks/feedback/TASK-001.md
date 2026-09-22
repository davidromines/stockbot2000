Right database now, and the self-consistency check correctly caught the failure.
One defect remains, and it was caused by missing context rather than by you —
the schema is now included in this request.

WRONG COLUMN NAME. Every query used `p.symbol`. The `prices` table's column is
`ticker`, not `symbol`. The schema is supplied above; use it rather than
inferring column names.

Specifically:
  prices(ticker, date, open, high, low, close, volume, source)
  symbols(ticker, name, exchange, security_type, first_seen, last_seen,
          is_active, data_quality)
  delistings — check the schema for its ticker column name
  daily_fundamentals(ticker, date, has_fundamentals, ...)

Join on `ticker`, not `symbol`.

Keep everything else. The startup log line naming the database and the prices
row count is exactly right, and the consistency assertions did their job — they
turned a silent wrong answer into a visible error, which is the behaviour this
project wants.