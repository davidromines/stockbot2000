"""
End-to-end proof that a breached stop becomes a SELL the user actually sees.

The stop-loss path had never run with a non-empty sells list. Every sell field
in the order JSON, every SELL line in the rendered slate, and the red SELL block
in the Telegram formatter were written but never exercised, because no position
had breached its stop while the pipeline was watching.

Runs against a throwaway SQLite file seeded with the real TNON numbers — entry
$5.5401, stop $4.8753, and the $3.91 close that breached it — so nothing here
touches the production database.

Run:  PYTHONPATH=. venv/bin/python tests/test_sell_alert.py
"""
import runtime  # noqa: F401
import os
import tempfile

import daily_picks as dp
import notify
import orders
import storage
from universe import load_config

cfg = load_config()
tmp = os.path.join(tempfile.mkdtemp(), "sell_test.db")
conn = storage.connect(tmp)
storage.init_db(conn)
dp.init(conn)

# Real bars: TNON fell through its stop on 2026-09-16.
for d, c in (("2026-09-14", 5.5600), ("2026-09-15", 5.0600), ("2026-09-16", 3.9100)):
    conn.execute("INSERT INTO prices (ticker,date,open,high,low,close,volume,source) "
                 "VALUES ('TNON',?,?,?,?,?,1000,'test')", (d, c, c, c, c))
conn.execute("""INSERT INTO picks (pick_date,ticker,source,rank,price,stop_price,
                hold_days,rationale,entry_date,status)
                VALUES ('2026-09-11','TNON','lab_survivor',1,5.5401,4.8753,49,
                        'test',' 2026-09-14','open')""")
conn.commit()

fails = []

# 1. the stop is detected at all
sells = dp.check_sells(conn, cfg)
print(f"  1. check_sells          -> {len(sells)} sell(s)")
if len(sells) != 1 or sells[0]["ticker"] != "TNON":
    fails.append("check_sells did not flag the breached stop")
else:
    s = sells[0]
    print(f"     {s['ticker']} {s['pnl_pct']:+.1f}%  {s['reason']}")

# 2. it survives into the rendered slate
spec = {"date": "2026-09-16", "size": 20.0, "cap": 5, "keeping": [], "pending": [],
        "sells": sells, "buys": []}
text = orders.render(spec)
print("  2. orders.render        -> SELL line present:",
      "SELL  TNON" in text and "SELL FIRST" in text)
if "SELL  TNON" not in text:
    fails.append("rendered slate has no SELL line")

# 3. the JSON the notifier reads carries the sell detail
js = {"date": spec["date"], "size": spec["size"], "keeping": [],
      "sells": [{"side": "SELL", "ticker": x["ticker"], "source": x["source"],
                 "entry": x["entry"], "now": x["now"], "pnl_pct": x["pnl_pct"],
                 "reason": x["reason"]} for x in sells], "buys": []}
print("  3. order JSON           -> pnl_pct carried:",
      js["sells"][0].get("pnl_pct") is not None)
if js["sells"][0].get("pnl_pct") is None:
    fails.append("sell JSON lost pnl_pct")

# 4. the Telegram body renders a RED sell block with escaped markup
plain, html = notify.format_slate(js)
ok_red = notify.SELL_DOT in html and "SELL" in html
ok_esc = "<=" not in html          # the reason contains "<=", which must be escaped
print(f"  4. telegram format      -> red marker: {ok_red}   HTML escaped: {ok_esc}")
if not ok_red:
    fails.append("no red SELL marker in the Telegram body")
if not ok_esc:
    fails.append("unescaped '<' in the Telegram body — Telegram would 400 the message")

print()
print(plain)
print()
print("  RESULT:", "PASS" if not fails else "FAIL — " + "; ".join(fails))
conn.close()
raise SystemExit(0 if not fails else 1)
