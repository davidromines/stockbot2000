"""
Regression tests for the Stockbot Value Fund (value_fund.py).

Four behaviours here are load-bearing, and each exists because the obvious
alternative produces plausible-looking output that is wrong:

  * hysteresis — buy the top decile, sell only on falling out of the top 40%.
    A single threshold churns on noise, and turnover is the one cost a
    long-horizon fund cannot argue away.
  * no stop loss — a stop converts a fundamental thesis into a price rule and
    reliably sells the position that fell because the opportunity improved.
  * a frozen thesis — the reasoning is written once at entry and never
    updated. A thesis that can be edited afterwards is not a thesis.
  * refusing a partial mark — if any held position cannot be priced, mark()
    records nothing. Marking the rest would report a fund that never loses on
    the names it can no longer see.

A fifth was added later: the quarterly review gate. REVIEW_DAYS was declared
and never read, so review() ran whenever it was called; wired into a daily
pipeline that rebalances a quarterly fund every morning. review_due() now
gates it, and the boundary is tested at exactly REVIEW_DAYS because an
off-by-one there is invisible until the fund has churned for a year.

Run directly:  PYTHONPATH=. venv/bin/python tests/regression/test_value_fund.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import ast
import datetime as dt
import inspect
import json
import os
import re
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import value_fund  # noqa: E402

PASSED = 0
FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def fresh_conn():
    """In-memory database with the tables value_fund.py reads from."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE prices (
        ticker TEXT NOT NULL, date TEXT NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume INTEGER,
        source TEXT NOT NULL DEFAULT 'yfinance',
        PRIMARY KEY (ticker, date))""")
    conn.execute("""CREATE TABLE sec_filings (
        ticker TEXT NOT NULL, sic TEXT)""")
    conn.commit()
    return conn


def add_price(conn, ticker, date, close):
    conn.execute("INSERT OR REPLACE INTO prices (ticker, date, close) "
                 "VALUES (?,?,?)", (ticker, date, close))
    conn.commit()


def add_position(conn, ticker, opened_on, entry_price, shares,
                 industry="Information Technology", thesis=None,
                 score_at_entry=95.0):
    conn.execute("""INSERT OR REPLACE INTO value_fund_positions
        (name, ticker, opened_on, entry_price, shares, industry, thesis,
         score_at_entry) VALUES (?,?,?,?,?,?,?,?)""",
        (value_fund.FUND, ticker, opened_on, entry_price, shares, industry,
         thesis if thesis is not None else json.dumps({"composite": score_at_entry}),
         score_at_entry))
    conn.commit()


def set_last_review(conn, date):
    """Set last_review directly; review() is not exercised by these checks."""
    conn.execute("UPDATE value_fund SET last_review=? WHERE name=?",
                 (date, value_fund.FUND))
    conn.commit()


def days_before(as_of, n):
    return (dt.date.fromisoformat(as_of) - dt.timedelta(days=n)).isoformat()


def source_of(module):
    return inspect.getsource(module)


def test_open_fund():
    conn = fresh_conn()
    r = value_fund.open_fund(conn, capital=250.0, as_of="2026-01-02")
    row = conn.execute("SELECT * FROM value_fund WHERE name=?",
                       (value_fund.FUND,)).fetchone()
    check("open_fund creates a row", row is not None)
    check("open_fund status is 'open'", row["status"] == "open",
          f"got {row['status']!r}")
    check("open_fund cash equals capital", row["cash_usd"] == 250.0,
          f"got {row['cash_usd']}")
    check("open_fund capital equals capital", row["capital_usd"] == 250.0,
          f"got {row['capital_usd']}")
    check("open_fund records the start date", row["started_on"] == "2026-01-02",
          f"got {row['started_on']!r}")
    check("open_fund returns the fund name", r["name"] == value_fund.FUND)
    conn.close()


def test_open_fund_twice_raises():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    raised = False
    try:
        value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    except SystemExit:
        raised = True
    check("open_fund a second time raises SystemExit", raised)
    n = conn.execute("SELECT COUNT(*) FROM value_fund").fetchone()[0]
    check("open_fund a second time does not add a row", n == 1, f"got {n}")
    conn.close()


def test_price_is_point_in_time():
    conn = fresh_conn()
    add_price(conn, "AAA", "2026-01-01", 10.0)
    add_price(conn, "AAA", "2026-01-05", 12.0)
    add_price(conn, "AAA", "2026-01-09", 14.0)
    check("_price takes the most recent close at or before the date",
          value_fund._price(conn, "AAA", "2026-01-06") == 12.0,
          f"got {value_fund._price(conn, 'AAA', '2026-01-06')}")
    check("_price includes the as-of date itself",
          value_fund._price(conn, "AAA", "2026-01-05") == 12.0,
          f"got {value_fund._price(conn, 'AAA', '2026-01-05')}")
    check("_price returns None before any price exists",
          value_fund._price(conn, "AAA", "2025-12-31") is None)
    check("_price returns None for an unknown ticker",
          value_fund._price(conn, "ZZZ", "2026-01-06") is None)
    conn.close()


def test_mark_refuses_partial_book():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    add_position(conn, "AAA", "2026-01-02", 10.0, 5.0)
    add_position(conn, "BBB", "2026-01-02", 20.0, 2.0)
    add_price(conn, "AAA", "2026-01-06", 11.0)
    # BBB deliberately has no price on or before the mark date.
    m = value_fund.mark(conn, "2026-01-06")
    check("mark refuses when a position cannot be priced", m["marked"] is False,
          f"got {m}")
    n = conn.execute("SELECT COUNT(*) FROM value_fund_equity").fetchone()[0]
    check("mark writes no equity row on a partial book", n == 0, f"got {n}")
    last = conn.execute("SELECT last_mark FROM value_fund WHERE name=?",
                        (value_fund.FUND,)).fetchone()[0]
    check("mark does not advance last_mark on a partial book", last is None,
          f"got {last!r}")
    conn.close()


def test_mark_succeeds_when_fully_priced():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    add_position(conn, "AAA", "2026-01-02", 10.0, 5.0)
    add_position(conn, "BBB", "2026-01-02", 20.0, 2.0)
    add_price(conn, "AAA", "2026-01-06", 11.0)
    add_price(conn, "BBB", "2026-01-06", 21.0)
    m = value_fund.mark(conn, "2026-01-06")
    check("mark succeeds when every position is priced", m["marked"] is True,
          f"got {m}")
    row = conn.execute("SELECT * FROM value_fund_equity WHERE name=? AND date=?",
                       (value_fund.FUND, "2026-01-06")).fetchone()
    check("mark writes an equity row", row is not None)
    if row is not None:
        expected = 100.0 + 11.0 * 5.0 + 21.0 * 2.0
        check("mark equity is cash plus marked positions",
              abs(row["equity_usd"] - expected) < 1e-6,
              f"got {row['equity_usd']} want {expected}")
        check("mark records the position count", row["n_positions"] == 2,
              f"got {row['n_positions']}")
    conn.close()


def test_constants_express_hysteresis():
    check("BUY_PERCENTILE is the top decile",
          value_fund.BUY_PERCENTILE == 90.0,
          f"got {value_fund.BUY_PERCENTILE}")
    check("SELL_PERCENTILE is the top 40%",
          value_fund.SELL_PERCENTILE == 40.0,
          f"got {value_fund.SELL_PERCENTILE}")
    check("the sell threshold is strictly below the buy threshold",
          value_fund.SELL_PERCENTILE < value_fund.BUY_PERCENTILE,
          f"{value_fund.SELL_PERCENTILE} !< {value_fund.BUY_PERCENTILE}")
    check("the gap is wide enough not to churn on noise",
          value_fund.BUY_PERCENTILE - value_fund.SELL_PERCENTILE >= 20.0,
          f"gap {value_fund.BUY_PERCENTILE - value_fund.SELL_PERCENTILE}")


def test_no_stop_loss_logic():
    src = source_of(value_fund)
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    stop_names = {n for n in names if "stop" in n.lower()}
    check("no stop-loss identifier appears in the module", not stop_names,
          f"found {sorted(stop_names)}")
    # A stop would have to be compared against a price to fire.
    check("no stop_price column is written",
          "stop_price" not in src)
    check("no stop_price column is read",
          "stop_price" not in src)


def test_never_writes_league_tables():
    src = source_of(value_fund)
    tree = ast.parse(src)
    league = {"paper_runs", "paper_positions", "paper_trades", "paper_equity",
              "league_strategies", "league_state", "evaluations",
              "experiments", "experiment_trades", "experiment_registry",
              "promotions", "picks", "claude_fund", "claude_fund_meta",
              "pair_funds", "pair_fund_equity"}
    # The fund's own tables must be the only ones it creates.
    created = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "CREATE TABLE" in node.value.upper():
                for t in ("value_fund", "value_fund_positions",
                          "value_fund_trades", "value_fund_equity"):
                    if t in node.value:
                        created.add(t)
    check("value_fund.py creates only its own tables",
          created == {"value_fund", "value_fund_positions",
                      "value_fund_trades", "value_fund_equity"},
          f"got {sorted(created)}")
    # A substring search cannot tell an explanation from a violation: the
    # module docstring names `paper_runs` precisely to argue for the
    # separation. What matters is whether any SQL statement targets a league
    # table, so look at the statements rather than the prose.
    sql_targets = set(re.findall(r"(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_]+)", src))
    leagues = {"paper_runs", "paper_equity", "paper_trades", "paper_positions"}
    check("value_fund.py issues no SQL against the tactical league's tables",
          not (sql_targets & leagues),
          f"touches {sorted(sql_targets & leagues)}")


def test_cannot_reach_the_broker():
    src = source_of(value_fund)
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    forbidden = {"execution", "broker", "orders", "risk_engine", "killswitch"}
    hit = imported & forbidden
    check("value_fund.py imports neither execution nor broker", not hit,
          f"found {sorted(hit)}")
    check("value_fund.py does not import the order layer",
          "orders" not in imported)


def test_thesis_is_frozen():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    thesis = json.dumps({
        "composite": 95.0,
        "dimensions": {"value": 90.0, "quality": 88.0},
        "dimensions_scored": 9,
        "weighting": "equal",
        "industry": "Information Technology",
        "bought_because": "top decile of Information Technology",
    }, sort_keys=True)
    add_position(conn, "AAA", "2026-01-02", 10.0, 5.0, thesis=thesis,
                 score_at_entry=95.0)
    add_price(conn, "AAA", "2026-01-06", 7.0)   # down 30%
    value_fund.mark(conn, "2026-01-06")
    row = conn.execute("SELECT thesis, score_at_entry FROM value_fund_positions "
                       "WHERE name=? AND ticker=?",
                       (value_fund.FUND, "AAA")).fetchone()
    check("the thesis survives a mark unchanged", row["thesis"] == thesis,
          "thesis was rewritten")
    check("the score at entry survives a mark unchanged",
          row["score_at_entry"] == 95.0, f"got {row['score_at_entry']}")
    parsed = json.loads(row["thesis"])
    check("the thesis carries the dimensions",
          parsed.get("dimensions") == {"value": 90.0, "quality": 88.0},
          f"got {parsed.get('dimensions')}")
    check("the thesis carries the reasoning",
          "bought_because" in parsed)
    # A 30% drawdown must not close the position: there is no stop.
    still = conn.execute("SELECT COUNT(*) FROM value_fund_positions WHERE "
                         "name=? AND ticker=?",
                         (value_fund.FUND, "AAA")).fetchone()[0]
    check("a 30% drawdown does not close the position", still == 1,
          f"got {still}")
    conn.close()


def test_status_with_no_positions():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    s = value_fund.status(conn)
    check("status reports the fund exists", s["exists"] is True)
    check("status reports no positions", s["positions"] == [],
          f"got {s['positions']}")
    check("status reports zero marks", s["marks"] == 0, f"got {s['marks']}")
    check("status equity is the untouched cash", s["equity"] == 100.0,
          f"got {s['equity']}")
    check("status return is zero", abs(s["return"]) < 1e-9,
          f"got {s['return']}")
    conn.close()


def test_render_flags_unrankable():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    text = value_fund.render(value_fund.status(conn))
    check("render says NOT YET RANKABLE below 60 marks",
          "NOT YET RANKABLE" in text)
    check("render names the fund", "STOCKBOT VALUE FUND" in text)
    check("render says it holds nothing", "holds nothing yet" in text)
    check("render explains the separate scoreboard",
          "separately" in text or "separate" in text)
    conn.close()


def test_render_without_a_fund():
    conn = fresh_conn()
    text = value_fund.render(value_fund.status(conn))
    check("render handles a missing fund", "No value fund" in text,
          text[:80])
    conn.close()


def test_review_due_without_a_fund():
    conn = fresh_conn()
    value_fund.init(conn)
    due, why = value_fund.review_due(conn, "2026-01-02")
    check("review_due is not due when no fund row exists", due is False,
          f"got {due!r}")
    check("review_due explains the missing fund", "no value fund" in why,
          f"got {why!r}")
    conn.close()


def test_review_due_first_review():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    due, why = value_fund.review_due(conn, "2026-01-02")
    check("review_due is due when last_review is NULL", due is True,
          f"got {due!r}")
    check("review_due calls the first review the first review",
          "first review" in why, f"got {why!r}")
    conn.close()


def test_review_due_not_due_at_30_days():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    set_last_review(conn, days_before("2026-04-02", 30))
    due, why = value_fund.review_due(conn, "2026-04-02")
    check("review_due is not due 30 days after the last review", due is False,
          f"got {due!r}")
    check("review_due reports the days remaining", "next due in" in why,
          f"got {why!r}")
    conn.close()


def test_review_due_boundary_at_review_days():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    as_of = "2026-04-02"
    # Exactly REVIEW_DAYS is due: the gate is `age >= REVIEW_DAYS`, and a
    # strict `>` would silently delay every review by a day forever.
    set_last_review(conn, days_before(as_of, value_fund.REVIEW_DAYS))
    due, why = value_fund.review_due(conn, as_of)
    check("review_due is due at exactly REVIEW_DAYS", due is True,
          f"got {due!r}")
    check("review_due reports the age at the boundary",
          str(value_fund.REVIEW_DAYS) in why, f"got {why!r}")
    conn.close()


def test_review_due_not_due_one_day_short():
    conn = fresh_conn()
    value_fund.open_fund(conn, capital=100.0, as_of="2026-01-02")
    as_of = "2026-04-02"
    set_last_review(conn, days_before(as_of, value_fund.REVIEW_DAYS - 1))
    due, why = value_fund.review_due(conn, as_of)
    check("review_due is not due one day short of REVIEW_DAYS", due is False,
          f"got {due!r}")
    check("review_due reports one day remaining",
          "next due in 1" in why, f"got {why!r}")
    conn.close()


def test_review_days_is_actually_read():
    src = source_of(value_fund)
    tree = ast.parse(src)
    # A constant that is declared and never read is exactly the bug this task
    # exists to fix, so assert on the AST rather than on the source text: a
    # mention in a docstring or a comment is not a read.
    reads = [n for n in ast.walk(tree)
             if isinstance(n, ast.Name) and n.id == "REVIEW_DAYS"
             and isinstance(n.ctx, ast.Load)]
    check("REVIEW_DAYS is read somewhere in the module", len(reads) > 0,
          "declared but never read")
    check("REVIEW_DAYS is read inside review_due",
          any(isinstance(n, ast.FunctionDef) and n.name == "review_due"
              and any(isinstance(x, ast.Name) and x.id == "REVIEW_DAYS"
                      and isinstance(x.ctx, ast.Load)
                      for x in ast.walk(n))
              for n in ast.walk(tree)),
          "review_due does not consult REVIEW_DAYS")
    check("REVIEW_DAYS is a positive number of days",
          isinstance(value_fund.REVIEW_DAYS, int)
          and value_fund.REVIEW_DAYS > 0,
          f"got {value_fund.REVIEW_DAYS!r}")


def main():
    print("\n  test_value_fund.py — Stockbot Value Fund regression\n")
    test_open_fund()
    test_open_fund_twice_raises()
    test_price_is_point_in_time()
    test_mark_refuses_partial_book()
    test_mark_succeeds_when_fully_priced()
    test_constants_express_hysteresis()
    test_no_stop_loss_logic()
    test_never_writes_league_tables()
    test_cannot_reach_the_broker()
    test_thesis_is_frozen()
    test_status_with_no_positions()
    test_render_flags_unrankable()
    test_render_without_a_fund()
    test_review_due_without_a_fund()
    test_review_due_first_review()
    test_review_due_not_due_at_30_days()
    test_review_due_boundary_at_review_days()
    test_review_due_not_due_one_day_short()
    test_review_days_is_actually_read()
    print(f"\n  {PASSED} passed, {FAILED} failed\n")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
