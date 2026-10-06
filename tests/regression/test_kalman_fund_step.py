"""Regression tests for kalman_pair.step_fund and its hand-off from the main stepper.

The Kalman EWA/EWC fund used to call a function that does not exist and swallow
the error, so it never stepped; and paper_trading.step() traded it as a
classifier fund. These tests drive the real step_fund over the synthetic series
of test_kalman_pair.py, one revealed session at a time like the daily job, and
pin: fills at the next open, fresh entries only (a run in progress when the fund
opened is not inherited, a missed entry is not made late), exits always honoured,
one equity mark per stepped session, costs by liquidity tier, no write on missing
data, and cash and marks that accounting.py reconciles.
"""
import runtime  # noqa: F401
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import accounting  # noqa: E402
import costs as costs_mod  # noqa: E402
import kalman_pair as kp  # noqa: E402
import paper_trading as pt  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s  %s" % (name, detail))
        FAILED.append(name)


def near(a, b, tol=1e-9):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def synth(n=600, seed=7):
    rs = np.random.RandomState(seed)
    idx = pd.bdate_range("2006-07-03", periods=n).strftime("%Y-%m-%d")
    x = 100.0 * np.exp(np.cumsum(rs.normal(0, 0.01, n)))
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.8 * noise[i - 1] + rs.normal(0, 0.5)
    y = 1.5 * x + 10.0 + noise
    return pd.Series(x, index=idx), pd.Series(y, index=idx)


SIZE = 25.0
CFG = {"risk": {"position_size_usd": SIZE}}
OFFSET = 0.25
X, Y = synth()
DATES = list(X.index)
CLOSE = {"EWA": X, "EWC": Y}
KF = kp.kalman(X, Y, delta=kp.DEFAULT_PARAMS["delta"], ve=kp.DEFAULT_PARAMS["ve"])
POS = kp.positions(KF, entry_z=kp.DEFAULT_PARAMS["entry_z"]).to_numpy()


def cl(tk, i):
    return float(CLOSE[tk].iloc[i])


def opx(tk, i):
    return cl(tk, i) + OFFSET


def new_db(features=True):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume REAL)")
    if features:
        conn.execute("CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL)")
    pt.init(conn)
    return conn


def reveal(conn, lo, hi, null_open=()):
    rows = []
    for i in range(lo, hi):
        for tk in ("EWA", "EWC"):
            c = cl(tk, i)
            o = None if (tk, i) in null_open else c + OFFSET
            rows.append((tk, DATES[i], o, c, c, c, 1e6))
        rows.append(("SPY", DATES[i], 100.0, 100.0, 100.0, 100.0, 1e6))
    conn.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()


def start_fund(start, features=True):
    conn = new_db(features)
    reveal(conn, 0, start + 1)
    kp.open_fund(conn)
    return conn


def step_to(conn, i, cfg=CFG, null_open=()):
    reveal(conn, i, i + 1, null_open)
    return kp.step_fund(conn, cfg)


def fund_row(conn):
    return conn.execute("SELECT * FROM paper_runs WHERE name=?", (kp.FUND_LABEL,)).fetchone()


def rid(conn):
    return fund_row(conn)["run_id"]


def positions_of(conn):
    return [tuple(r) for r in conn.execute(
        "SELECT ticker, entry_date, entry_price, shares, stop_price, days_held "
        "FROM paper_positions WHERE run_id=?", (rid(conn),))]


def trades_of(conn):
    return conn.execute("SELECT * FROM paper_trades WHERE run_id=? ORDER BY entry_date, exit_date",
                        (rid(conn),)).fetchall()


def equity_of(conn):
    return conn.execute("SELECT * FROM paper_equity WHERE run_id=? ORDER BY date",
                        (rid(conn),)).fetchall()


def fund_recon(conn):
    rows = accounting.paper_funds(conn, costs_mod.CostModel(CFG))
    mine = [r for r in rows if r["fund_id"] == rid(conn)]
    return mine[0] if mine else None


def run_of(lo, hi, val):
    return all(int(POS[i]) == val for i in range(lo, hi + 1))


# --------------------------------------------------------------------------- #
def test_premise():
    check("premise: run A is +1 on 224-226, flat on 223 and 227-228",
          POS[223] == 0 and run_of(224, 226, 1) and POS[227] == 0 and POS[228] == 0)
    check("premise: run B is -1 on 386-389, flat 390-393, -1 at 394, flat 395-396",
          run_of(386, 389, -1) and run_of(390, 393, 0) and POS[394] == -1 and run_of(395, 396, 0))
    check("premise: flat on 385", POS[385] == 0)
    check("premise: the series carries 600 sessions", len(DATES) == 600)


def test_fresh_targets():
    d = ["2020-01-%02d" % (i + 1) for i in range(10)]

    t, s = kp._fresh_targets(np.array([0, 0, 1, 1, 1, 0, 0, -1, -1, 0]), d, d[3])
    check("fresh: a run that began before started_on is masked to its end, the next is live",
          list(t) == [0, 0, 0, 0, 0, 0, 0, -1, -1, 0], list(t))
    check("fresh: only the live run's first session is a start",
          [i for i in range(10) if s[i]] == [7], [i for i in range(10) if s[i]])

    t, s = kp._fresh_targets(np.array([0, 0, 1, 1, 1, 0, 0, -1, -1, 0]), d, d[2])
    check("fresh: a run beginning exactly on started_on is live",
          list(t) == [0, 0, 1, 1, 1, 0, 0, -1, -1, 0], list(t))
    check("fresh: starts at both run beginnings", [i for i in range(10) if s[i]] == [2, 7],
          [i for i in range(10) if s[i]])

    t, s = kp._fresh_targets(np.array([1, 1, 1, 0, 0, 1, 1, 0]), d[:8], d[1])
    check("fresh: a run in progress at the first bar is not inherited",
          list(t) == [0, 0, 0, 0, 0, 1, 1, 0] and [i for i in range(8) if s[i]] == [5],
          (list(t), list(s)))

    t, s = kp._fresh_targets(np.zeros(10, dtype=int), d, d[2])
    check("fresh: all flat gives no targets and no starts", not t.any() and not s.any())

    t, s = kp._fresh_targets(np.array([1, 1, -1, -1, 0]), d[:5], d[2])
    check("fresh: a direct flip is a new run, live from started_on",
          list(t) == [0, 0, -1, -1, 0] and [i for i in range(5) if s[i]] == [2], (list(t), list(s)))


def test_kalman_of():
    mine = {"strategy": json.dumps({"pair": "EWA/EWC", "mode": "long_leg",
                                    "family": kp.FUND_FAMILY})}
    check("kalman_of: the fund's own strategy JSON", bool(pt._kalman_of(mine)))
    check("kalman_of: another family is not it",
          not pt._kalman_of({"strategy": json.dumps({"family": "rotation"})}))
    check("kalman_of: the literal 'model' is not it", not pt._kalman_of({"strategy": "model"}))
    check("kalman_of: no strategy is not it",
          not pt._kalman_of({"strategy": None}) and not pt._kalman_of({"strategy": ""}) and
          not pt._kalman_of({}))
    check("kalman_of: a JSON list is not it", not pt._kalman_of({"strategy": "[1, 2]"}))


def test_dollar_volume():
    conn = new_db()
    conn.executemany("INSERT INTO features VALUES (?,?,?)",
                     [("EWC", "2020-01-02", 1e6), ("EWC", "2020-01-06", 5e6),
                      ("EWC", "2020-01-10", None), ("EWA", "2020-01-02", 9e9)])
    conn.commit()
    check("dollar_volume: the latest value at or before the day",
          near(kp._dollar_volume(conn, "EWC", "2020-01-07"), 5e6))
    check("dollar_volume: exactly on a feature date", near(kp._dollar_volume(conn, "EWC", "2020-01-02"), 1e6))
    check("dollar_volume: nothing yet is 0.0 (widest tier)",
          kp._dollar_volume(conn, "EWC", "2019-12-31") == 0.0)
    check("dollar_volume: a NULL value is 0.0", kp._dollar_volume(conn, "EWC", "2020-01-11") == 0.0)
    check("dollar_volume: other tickers do not leak", near(kp._dollar_volume(conn, "EWA", "2020-01-07"), 9e9))
    bare = new_db(features=False)
    check("dollar_volume: no features table is 0.0", kp._dollar_volume(bare, "EWC", "2020-01-07") == 0.0)


# --------------------------------------------------------------------------- #
def drive_a(conn):
    """Open at 223 (done by the caller), step 224..228; returns the 225 result and the trade."""
    step_to(conn, 224)
    step_to(conn, 225)
    step_to(conn, 226)
    step_to(conn, 227)
    step_to(conn, 228)
    trades = trades_of(conn)
    return trades[0] if trades else None


def test_run_a():
    conn = start_fund(223)
    check("A: the fund starts on the session it was opened", fund_row(conn)["started_on"] == DATES[223],
          fund_row(conn)["started_on"])

    r224 = step_to(conn, 224)
    eq = equity_of(conn)
    check("A: 224 is flat (the 223 close said 0)",
          r224 is not None and "flat" in r224 and not positions_of(conn), r224)
    check("A: 224 books one equity mark at capital",
          len(eq) == 1 and eq[0]["date"] == DATES[224] and near(eq[0]["equity_usd"], 100.0) and
          eq[0]["open_positions"] == 0, [tuple(r) for r in eq])

    r225 = step_to(conn, 225)
    pos = positions_of(conn)
    px = opx("EWC", 225)
    check("A: 225 enters EWC (the +1 side) at the 225 open",
          len(pos) == 1 and pos[0][0] == "EWC" and pos[0][1] == DATES[225] and near(pos[0][2], px),
          pos)
    check("A: the entry note names the fill", r225 is not None and "ENTER EWC @ %.2f" % px in r225, r225)
    shares = SIZE / px
    check("A: sized at position_size_usd", len(pos) == 1 and near(pos[0][3] * px, SIZE))
    check("A: no stop price, days_held 0 on entry day",
          len(pos) == 1 and pos[0][4] is None and pos[0][5] == 0, pos)
    check("A: entry cash is capital less the size", near(fund_row(conn)["cash_usd"], 100.0 - SIZE))
    e = equity_of(conn)[-1]
    check("A: 225 equity = cash + shares x close",
          near(e["equity_usd"], 100.0 - SIZE + shares * cl("EWC", 225)) and e["open_positions"] == 1,
          tuple(e))

    step_to(conn, 226)
    check("A: 226 holds, days_held 1",
          len(positions_of(conn)) == 1 and positions_of(conn)[0][5] == 1, positions_of(conn))
    row = fund_recon(conn)
    check("A: mid-hold the fund reconciles in accounting.py",
          row is not None and row["recon_status"] == "RECONCILED" and near(row["cash_drift_usd"], 0.0)
          and near(row["mark_diff_usd"], 0.0), None if row is None else (
              row["recon_status"], row["cash_drift_usd"], row["mark_diff_usd"]))

    step_to(conn, 227)
    check("A: 227 holds, days_held 2",
          len(positions_of(conn)) == 1 and positions_of(conn)[0][5] == 2, positions_of(conn))

    r228 = step_to(conn, 228)
    check("A: 228 exits (the 227 close said 0)", not positions_of(conn) and "EXIT EWC" in (r228 or ""), r228)
    trades = trades_of(conn)
    check("A: exactly one closed trade", len(trades) == 1, len(trades))
    t = trades[0]
    exit_px = opx("EWC", 228)
    gross = shares * (exit_px - px)
    cost = float(costs_mod.CostModel(CFG).round_trip(shares * px, 0.0, shares))
    check("A: trade fills at the 228 open, entry on 225",
          t["ticker"] == "EWC" and t["entry_date"] == DATES[225] and t["exit_date"] == DATES[228] and
          near(t["entry_price"], px) and near(t["exit_price"], exit_px), tuple(t))
    check("A: reason 'e crossed zero'", t["exit_reason"] == "e crossed zero", t["exit_reason"])
    check("A: gross = shares x (exit - entry)", near(t["gross_pnl_usd"], gross), (t["gross_pnl_usd"], gross))
    check("A: cost is the round trip at the widest tier (liquidity unknown)",
          near(t["costs_usd"], cost), (t["costs_usd"], cost))
    check("A: net = gross - costs", near(t["net_pnl_usd"], gross - cost))
    check("A: pnl_pct from the fills", near(t["pnl_pct"], (exit_px / px - 1.0) * 100.0))
    check("A: cash after the exit = 75 + proceeds - cost",
          near(fund_row(conn)["cash_usd"], 100.0 - SIZE + shares * exit_px - cost))

    r229 = step_to(conn, 229)
    eq = equity_of(conn)
    check("A: 229 flat again", r229 is not None and "flat" in r229 and not positions_of(conn), r229)
    check("A: one equity mark per stepped session (224-229), none for 223",
          [r["date"] for r in eq] == DATES[224:230], [r["date"] for r in eq])
    check("A: final equity = capital + gross - costs", near(eq[-1]["equity_usd"], 100.0 + gross - cost))
    check("A: last_step_on is the newest session", fund_row(conn)["last_step_on"] == DATES[229])
    row = fund_recon(conn)
    check("A: after the exit the fund reconciles in accounting.py",
          row is not None and row["recon_status"] == "RECONCILED" and near(row["cash_drift_usd"], 0.0)
          and row["closed_trades"] == 1,
          None if row is None else (row["recon_status"], row["cash_drift_usd"], row["closed_trades"]))


def test_costs_by_tier():
    cm = costs_mod.CostModel(CFG)

    unknown = start_fund(223)
    t_unknown = drive_a(unknown)
    known = start_fund(223)
    known.execute("INSERT INTO features VALUES ('EWC', ?, 2e8)", (DATES[100],))
    known.commit()
    t_known = drive_a(known)
    nofeat = start_fund(223, features=False)
    t_nofeat = drive_a(nofeat)

    check("tier: all three runs closed a trade", None not in (t_unknown, t_known, t_nofeat))
    if None in (t_unknown, t_known, t_nofeat):
        return
    px = t_unknown["entry_price"]
    shares = t_unknown["shares"]
    want_known = float(cm.round_trip(shares * px, 2e8, shares))
    want_unknown = float(cm.round_trip(shares * px, 0.0, shares))
    free = float(cm.round_trip(shares * px, None, shares))
    check("tier: a known $200M/day liquidity is charged its own tier",
          near(t_known["costs_usd"], want_known), (t_known["costs_usd"], want_known))
    check("tier: unknown liquidity is charged the widest tier, not nothing",
          near(t_unknown["costs_usd"], want_unknown) and t_unknown["costs_usd"] > free,
          (t_unknown["costs_usd"], want_unknown, free))
    check("tier: unknown costs more than a liquid name", t_unknown["costs_usd"] > t_known["costs_usd"])
    check("tier: a database without a features table costs the same as an empty one",
          near(t_nofeat["costs_usd"], want_unknown), (t_nofeat["costs_usd"], want_unknown))


def test_run_b_masked():
    conn = start_fund(387)
    for i in range(388, 395):
        r = step_to(conn, i)
        if positions_of(conn) or "ENTER" in (r or ""):
            check("B: no entry on %s while the inherited run 386-389 plays out" % DATES[i], False, r)
            break
    else:
        check("B: the run in progress at opening (386-389) is never entered, nor the gap after it", True)
    check("B: flat marks all along", [r["open_positions"] for r in equity_of(conn)] == [0] * 7 and
          all(near(r["equity_usd"], 100.0) for r in equity_of(conn)))

    r395 = step_to(conn, 395)
    pos = positions_of(conn)
    check("B: the first fresh run (394) is entered at the 395 open, on the EWA (-1) side",
          len(pos) == 1 and pos[0][0] == "EWA" and pos[0][1] == DATES[395] and
          near(pos[0][2], opx("EWA", 395)), (pos, r395))
    r396 = step_to(conn, 396)
    trades = trades_of(conn)
    check("B: exits at the 396 open with 'e crossed zero'",
          len(trades) == 1 and trades[0]["ticker"] == "EWA" and trades[0]["exit_date"] == DATES[396] and
          near(trades[0]["exit_price"], opx("EWA", 396)) and trades[0]["exit_reason"] == "e crossed zero",
          (None if not trades else tuple(trades[0]), r396))


def test_run_b_control():
    conn = start_fund(385)
    step_to(conn, 386)
    check("B2: 386 flat (385 close said 0)", not positions_of(conn))
    r387 = step_to(conn, 387)
    pos = positions_of(conn)
    check("B2: opened one session earlier, the 386-389 run is live and entered at the 387 open",
          len(pos) == 1 and pos[0][0] == "EWA" and near(pos[0][2], opx("EWA", 387)), (pos, r387))
    for i in (388, 389, 390):
        step_to(conn, i)
    pos = positions_of(conn)
    check("B2: held through 388-390 (days_held 3 on 390)",
          len(pos) == 1 and pos[0][5] == 3 and not trades_of(conn), pos)
    step_to(conn, 391)
    trades = trades_of(conn)
    check("B2: exits at the 391 open",
          len(trades) == 1 and trades[0]["exit_date"] == DATES[391] and not positions_of(conn),
          None if not trades else tuple(trades[0]))


def test_run_starting_on_open_day():
    conn = start_fund(224)
    check("C: started_on is 224", fund_row(conn)["started_on"] == DATES[224])
    r225 = step_to(conn, 225)
    pos = positions_of(conn)
    check("C: a run that began on the opening session is live and entered at the 225 open",
          len(pos) == 1 and pos[0][0] == "EWC" and near(pos[0][2], opx("EWC", 225)), (pos, r225))
    check("C: no equity mark for the session before the first step",
          [r["date"] for r in equity_of(conn)] == [DATES[225]], [r["date"] for r in equity_of(conn)])


def test_missed_entry_not_made_late():
    conn = start_fund(223)
    step_to(conn, 224)
    reveal(conn, 225, 227)
    r226 = kp.step_fund(conn, CFG)
    check("D: 225 never stepped; at 226 the run is two sessions old and is not entered late",
          r226 is not None and "ENTER" not in r226 and not positions_of(conn), r226)
    step_to(conn, 227)
    step_to(conn, 228)
    check("D: nothing entered and nothing to exit afterwards",
          not positions_of(conn) and not trades_of(conn))
    check("D: flat marks for 224, 226, 227, 228, none for 225",
          [r["date"] for r in equity_of(conn)] == [DATES[224], DATES[226], DATES[227], DATES[228]] and
          all(near(r["equity_usd"], 100.0) for r in equity_of(conn)),
          [r["date"] for r in equity_of(conn)])


def test_late_exit_honoured():
    conn = start_fund(223)
    for i in (224, 225, 226):
        step_to(conn, i)
    check("E: held EWC into 226", len(positions_of(conn)) == 1)
    reveal(conn, 227, 230)
    r229 = kp.step_fund(conn, CFG)
    trades = trades_of(conn)
    check("E: sessions 227-228 were never stepped; the exit is made at the 229 open",
          len(trades) == 1 and trades[0]["exit_date"] == DATES[229] and
          near(trades[0]["exit_price"], opx("EWC", 229)) and trades[0]["exit_reason"] == "e crossed zero" and
          not positions_of(conn), (None if not trades else tuple(trades[0]), r229))
    check("E: marks only for the stepped sessions",
          [r["date"] for r in equity_of(conn)] == [DATES[224], DATES[225], DATES[226], DATES[229]],
          [r["date"] for r in equity_of(conn)])
    row = fund_recon(conn)
    check("E: still reconciles after a late exit",
          row is not None and row["recon_status"] == "RECONCILED", None if row is None else row["recon_status"])


def test_idempotent_session():
    conn = start_fund(223)
    step_to(conn, 224)
    step_to(conn, 225)
    before = ([tuple(r) for r in equity_of(conn)], positions_of(conn), trades_of(conn),
              fund_row(conn)["cash_usd"], fund_row(conn)["last_step_on"])
    again = kp.step_fund(conn, CFG)
    after = ([tuple(r) for r in equity_of(conn)], positions_of(conn), trades_of(conn),
             fund_row(conn)["cash_usd"], fund_row(conn)["last_step_on"])
    check("F: a second step on the same session does nothing", again is None and before == after, again)


def test_missing_open():
    conn = start_fund(223)
    step_to(conn, 224)
    res = step_to(conn, 225, null_open={("EWC", 225)})
    check("G: a NULL open on the needed fill steps nothing", res is None, res)
    check("G: and writes nothing (no position, no mark, last_step_on unchanged)",
          not positions_of(conn) and [r["date"] for r in equity_of(conn)] == [DATES[224]] and
          fund_row(conn)["last_step_on"] == DATES[224] and near(fund_row(conn)["cash_usd"], 100.0))
    conn.execute("UPDATE prices SET open=? WHERE ticker='EWC' AND date=?", (opx("EWC", 225), DATES[225]))
    conn.commit()
    res = kp.step_fund(conn, CFG)
    check("G: retried once the open is there", res is not None and "ENTER EWC" in res and
          len(positions_of(conn)) == 1, res)

    other = start_fund(223)
    step_to(other, 224)
    res = step_to(other, 225, null_open={("EWA", 225)})
    check("G2: a NULL open on the leg not being traded does not block the entry",
          res is not None and "ENTER EWC" in res and len(positions_of(other)) == 1, res)

    held = start_fund(223)
    for i in (224, 225, 226, 227):
        step_to(held, i)
    res = step_to(held, 228, null_open={("EWC", 228)})
    check("G3: a NULL open on the exit fill keeps the position and writes nothing",
          res is None and len(positions_of(held)) == 1 and not trades_of(held) and
          fund_row(held)["last_step_on"] == DATES[227], res)
    held.execute("UPDATE prices SET open=? WHERE ticker='EWC' AND date=?", (opx("EWC", 228), DATES[228]))
    held.commit()
    res = kp.step_fund(held, CFG)
    check("G3: the exit is made when the open arrives",
          res is not None and "EXIT EWC" in res and len(trades_of(held)) == 1 and not positions_of(held), res)


def test_no_data_and_closed():
    empty = new_db()
    res = kp.step_fund(empty, CFG)
    check("H: no prices at all steps nothing", res is None and len(equity_of(empty)) == 0, res)

    two = new_db()
    reveal(two, 0, 2)
    res = kp.step_fund(two, CFG)
    check("H2: fewer than three sessions steps nothing", res is None and len(equity_of(two)) == 0, res)

    conn = start_fund(223)
    conn.execute("UPDATE paper_runs SET status='closed'")
    conn.commit()
    res = step_to(conn, 224)
    check("I: a closed fund is left alone",
          res is None and len(equity_of(conn)) == 0 and fund_row(conn)["last_step_on"] is None, res)


def test_no_cash_to_enter():
    conn = start_fund(223)
    big = {"risk": {"position_size_usd": 150.0}}
    step_to(conn, 224, cfg=big)
    res = step_to(conn, 225, cfg=big)
    check("K: an entry the cash cannot fund is declined and said so",
          res is not None and "no cash to enter EWC" in res and not positions_of(conn), res)
    e = equity_of(conn)[-1]
    check("K: the mark is flat at capital", e["date"] == DATES[225] and near(e["equity_usd"], 100.0) and
          e["open_positions"] == 0, tuple(e))


def test_signal_changed():
    conn = start_fund(385)
    step_to(conn, 386)
    conn.execute("INSERT INTO paper_positions (run_id, ticker, entry_date, entry_price, shares, "
                 "stop_price, days_held) VALUES (?,?,?,?,?,?,?)",
                 (rid(conn), "EWC", DATES[385], 50.0, 0.4, None, 1))
    conn.execute("UPDATE paper_runs SET cash_usd=80 WHERE run_id=?", (rid(conn),))
    conn.commit()
    res = step_to(conn, 387)
    trades = trades_of(conn)
    pos = positions_of(conn)
    exit_px = opx("EWC", 387)
    cost = float(costs_mod.CostModel(CFG).round_trip(0.4 * 50.0, 0.0, 0.4))
    check("M: the held EWC leg is sold on 387 with reason 'signal changed'",
          len(trades) == 1 and trades[0]["ticker"] == "EWC" and trades[0]["exit_reason"] == "signal changed" and
          near(trades[0]["exit_price"], exit_px) and near(trades[0]["costs_usd"], cost),
          (None if not trades else tuple(trades[0]), res))
    check("M: the other leg (EWA) is bought in the same step at the 387 open",
          len(pos) == 1 and pos[0][0] == "EWA" and near(pos[0][2], opx("EWA", 387)) and
          near(pos[0][3] * pos[0][2], SIZE), pos)
    want_cash = 80.0 + 0.4 * exit_px - cost - SIZE
    check("M: cash = 80 + proceeds - cost - new size", near(fund_row(conn)["cash_usd"], want_cash),
          (fund_row(conn)["cash_usd"], want_cash))
    e = equity_of(conn)[-1]
    check("M: the mark is cash + the new leg at its close",
          near(e["equity_usd"], want_cash + pos[0][3] * cl("EWA", 387)), tuple(e))


# --------------------------------------------------------------------------- #
def test_main_stepper_skips_fund():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, "
                 "low REAL, close REAL, volume REAL)")
    pt.init(conn)
    conn.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)",
                     [("ZZZ", d, 10.0, 10.0, 10.0, 10.0, 1e6) for d in ("2026-10-01", "2026-10-02")])
    conn.commit()
    kp.open_fund(conn)
    conn.execute("INSERT INTO paper_runs (run_id, name, strategy, capital_usd, cash_usd, started_on, "
                 "created_at) VALUES ('ctl', 'ctl_model', 'model', 100, 100, '2026-10-01', "
                 "'2026-10-01T00:00:00Z')")
    conn.commit()
    market = pd.DataFrame({"date": ["2026-10-02"], "ticker": ["ZZZ"], "close": [10.0],
                           "dollar_volume_20": [5e7], "atr_14": [0.5], "score": [50.0]})
    cfg = {"risk": {"position_size_usd": 20.0, "max_open_positions": 5,
                    "stop_loss_type": "fixed_pct", "stop_loss_fixed_pct": 5.0},
           "labeling": {"horizon_days": 5}}
    saved = pt._latest_scores
    pt._latest_scores = lambda c, g: market
    try:
        pt.step(conn, cfg)
    except Exception as exc:
        check("main stepper: runs with the Kalman fund in the book", False, repr(exc))
        return
    finally:
        pt._latest_scores = saved

    kid = rid(conn)
    k_pos = conn.execute("SELECT COUNT(*) FROM paper_positions WHERE run_id=?", (kid,)).fetchone()[0]
    k_eq = conn.execute("SELECT COUNT(*) FROM paper_equity WHERE run_id=?", (kid,)).fetchone()[0]
    k_tr = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE run_id=?", (kid,)).fetchone()[0]
    k_row = conn.execute("SELECT cash_usd, last_step_on FROM paper_runs WHERE run_id=?", (kid,)).fetchone()
    check("main stepper: leaves the Kalman fund with no positions, trades or marks",
          k_pos == 0 and k_eq == 0 and k_tr == 0, (k_pos, k_eq, k_tr))
    check("main stepper: and its cash and last_step_on are untouched",
          near(k_row["cash_usd"], 100.0) and k_row["last_step_on"] is None, tuple(k_row))
    c_pos = conn.execute("SELECT ticker FROM paper_positions WHERE run_id='ctl'").fetchall()
    c_row = conn.execute("SELECT last_step_on FROM paper_runs WHERE run_id='ctl'").fetchone()
    check("main stepper: still trades and steps an ordinary fund",
          [r["ticker"] for r in c_pos] == ["ZZZ"] and c_row["last_step_on"] == "2026-10-02",
          ([r["ticker"] for r in c_pos], tuple(c_row)))


def main():
    test_premise()
    test_fresh_targets()
    test_kalman_of()
    test_dollar_volume()
    test_run_a()
    test_costs_by_tier()
    test_run_b_masked()
    test_run_b_control()
    test_run_starting_on_open_day()
    test_missed_entry_not_made_late()
    test_late_exit_honoured()
    test_idempotent_session()
    test_missing_open()
    test_no_data_and_closed()
    test_no_cash_to_enter()
    test_signal_changed()
    test_main_stepper_skips_fund()

    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
