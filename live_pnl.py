"""
What the system has actually made: the real account's slot trades, and nothing else.

Owner, 2026-09-26: a P&L summed across every paper fund is not what the system
does — only the strategies holding slots are invested in. So the headline is the
real Robinhood account: every LIVE slot trade since LIVE was armed, gross, costs
and net side by side, closed and open. Paper funds, backtests and trades the
owner placed by hand (not in slot_trades) are not in it.

    gross  (exit - entry) x quantity, from the broker's fill prices
    costs  regulatory fees on sells (SEC fee + FINRA TAF, rates in config costs:);
           commission is $0; the spread is already inside the fill prices, so it
           is not charged twice
    net    gross - costs
    open   marked at the trader's latest LIVE quote (slot_marks); costs not yet paid

Read-only.

    ./venv/bin/python live_pnl.py [--mode LIVE]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys

from universe import load_config


def _name(conn, strategy_key: str) -> str:
    if strategy_key and strategy_key.startswith("paper:"):
        try:
            r = conn.execute("SELECT label, name FROM paper_runs WHERE run_id=?", (strategy_key[6:],)).fetchone()
            if r and (r[0] or r[1]):
                return r[0] or r[1]
        except sqlite3.Error:
            pass
    return strategy_key or "?"


def sell_fees(notional: float, quantity: float, cfg: dict) -> float:
    c = cfg.get("costs", {})
    sec = notional * float(c.get("sec_fee_per_million_usd", 0.0)) / 1e6
    taf = min(quantity * float(c.get("finra_taf_per_share_usd", 0.0)), float(c.get("finra_taf_cap_usd", 1e9)))
    return sec + taf


def compute(conn, cfg: dict, mode: str = "LIVE") -> dict:
    """Closed and open slot trades for `mode`, each OPEN paired with the next CLOSE of its slot."""
    rows = conn.execute("SELECT at, slot_id, strategy_key, symbol, action, quantity, price FROM slot_trades "
                        "WHERE mode=? ORDER BY at, id", (mode,)).fetchall()
    opened, closed = {}, []
    for at, slot, key, sym, action, qty, price in rows:
        if action == "OPEN":
            opened[slot] = {"slot": slot, "strategy": _name(conn, key), "symbol": sym, "quantity": float(qty),
                            "entry": float(price), "opened": at}
        elif action == "CLOSE" and slot in opened:
            o = opened.pop(slot)
            q = min(float(qty), o["quantity"])
            gross = (float(price) - o["entry"]) * q
            costs = sell_fees(float(price) * q, q, cfg)
            closed.append({**o, "quantity": q, "exit": float(price), "closed": at, "stake": o["entry"] * q,
                           "gross": gross, "costs": costs, "net": gross - costs,
                           "ret_pct": (float(price) / o["entry"] - 1) * 100})
    marks = {}
    try:
        for slot, sym, price in conn.execute("SELECT slot_id, symbol, price FROM slot_marks WHERE mode=? "
                                             "ORDER BY at, id", (mode,)):
            if price is not None:                 # a run with no quote writes NULL; keep the last real mark
                marks[(slot, sym)] = float(price)
    except sqlite3.Error:
        pass
    open_ = []
    for o in opened.values():
        m = marks.get((o["slot"], o["symbol"]))
        g = None if m is None else (m - o["entry"]) * o["quantity"]
        open_.append({**o, "stake": o["entry"] * o["quantity"], "mark": m, "gross": g,
                      "ret_pct": None if m is None else (m / o["entry"] - 1) * 100})
    tot = {k: sum(t[k] for t in closed) for k in ("stake", "gross", "costs", "net")}
    wins = sum(1 for t in closed if t["net"] > 0)
    unreal = [t["gross"] for t in open_ if t["gross"] is not None]
    return {"mode": mode, "since": rows[0][0][:10] if rows else None, "closed": closed, "open": open_,
            "closed_total": tot, "closed_n": len(closed), "wins": wins,
            "open_stake": sum(t["stake"] for t in open_), "open_gross": sum(unreal) if unreal else None}


def render(r: dict) -> list:
    """Short lines for a phone."""
    if not r["closed"] and not r["open"]:
        return ["no %s slot trades yet" % r["mode"]]
    t = r["closed_total"]
    L = ["since %s, %s slot trades only" % (r["since"], r["mode"]),
         "closed %d (%d won): gross %+.2f  costs %.2f  net %+.2f"
         % (r["closed_n"], r["wins"], t["gross"], t["costs"], t["net"])]
    if r["closed_n"]:
        L.append("  net %+.2f%% on $%.2f traded" % (100 * t["net"] / t["stake"] if t["stake"] else 0.0, t["stake"]))
    if r["open"]:
        og = "n/a" if r["open_gross"] is None else "%+.2f" % r["open_gross"]
        L.append("open %d ($%.2f): unrealized gross %s" % (len(r["open"]), r["open_stake"], og))
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="LIVE")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    r = compute(conn, cfg, a.mode)
    for t in r["closed"]:
        print(f"  CLOSED s{t['slot']} {t['symbol']:<5} {t['strategy'][:28]:<28} {t['entry']:>10.2f} -> "
              f"{t['exit']:>10.2f}  stake {t['stake']:>6.2f}  gross {t['gross']:+.3f}  costs {t['costs']:.4f}  "
              f"net {t['net']:+.3f}  {t['ret_pct']:+.2f}%")
    for t in r["open"]:
        m = "n/a" if t["mark"] is None else f"{t['mark']:.2f}"
        g = "n/a" if t["gross"] is None else f"{t['gross']:+.3f}"
        print(f"  OPEN   s{t['slot']} {t['symbol']:<5} {t['strategy'][:28]:<28} {t['entry']:>10.2f} mark {m}  "
              f"stake {t['stake']:.2f}  unrealized gross {g}")
    print("\n".join(render(r)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
