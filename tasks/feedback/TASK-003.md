Nearly there. You ADDED the SQL-based check — which is correct and passes —
but you also KEPT the old substring check, so the file now has both and the
old one still fails.

DELETE the check whose name is exactly:

    "value_fund.py never names a tactical league table"

It sits around line 229 and reads:

    check("value_fund.py never names a tactical league table", not touched,
          f"found {sorted(touched)}")

Delete that check AND the loop above it that builds the `touched` set (the
`for t in league: if t in low: touched.add(t)` block and the `touched = set()`
initialisation), since nothing else uses them.

Keep the new SQL-based check you added. Keep everything else unchanged.

After the deletion the file must print "RESULT: PASS" with zero failures.