"""Stage N6: per-trade live feedback — expected vs realised, aggregated by strategy.

Read-only. Nothing here feeds back into a strategy; it exists so that a live
fill can be compared against the quote the trader actually saw, which is the
only way to tell an edge from an execution artifact.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import sqlite3
import sys
from datetime import timedelta, datetime, timezone

from universe import load_config

# A round trip is only meaningful if the CLOSE follows the OPEN; anything else
# is a data problem, not a trade, so we refuse to pair it.
_ACTIONS = ("OPEN", "CLOSE")


def _parse_ts(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _connect(path):
    # Read-only URI: this module must never be able to write to the database.
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


MARK_WINDOW_S = 900


def _expected_price(conn, symbol, created_at, mode="LIVE"):
    """
    The quote the trader saw: the latest same-mode mark of this symbol in the
    MARK_WINDOW_S before the order was created, else None.

    Marks are written only for positions already held, so a BUY usually has none
    near its order; an older mark (yesterday's, or another mode's) is not the price
    the decision saw and would invent slippage (SNDK: +263 bps from a stale mark).
    The engine does not yet store its decision-time quote; until it does, None
    means "not recorded", never zero.
    """
    t = _parse_ts(created_at) if created_at else None
    if t is None:
        return None
    lo = (t - timedelta(seconds=MARK_WINDOW_S)).isoformat()
    row = conn.execute(
        "SELECT price FROM slot_marks WHERE symbol = ? AND mode = ? AND at <= ? AND at >= ? "
        "ORDER BY at DESC LIMIT 1",
        (symbol, mode, created_at, lo),
    ).fetchone()
    return row[0] if row else None


def _slippage_bps(action, fill, expected):
    """Positive is always bad: paying up on an OPEN, receiving less on a CLOSE."""
    if fill is None or expected is None or fill == 0 or expected == 0:
        return None
    if action == "OPEN":
        return (fill / expected - 1.0) * 10000.0
    if action == "CLOSE":
        return (expected / fill - 1.0) * 10000.0
    return None


def trades(conn, mode="LIVE"):
    rows = conn.execute(
        "SELECT id, at, slot_id, strategy_key, symbol, action, quantity, price, "
        "signal_id FROM slot_trades WHERE mode = ? ORDER BY at, id",
        (mode,),
    ).fetchall()
    out = []
    for (tid, at, slot_id, key, symbol, action, qty, price, signal_id) in rows:
        created_at = None
        if signal_id:
            o = conn.execute(
                # A signal id is shared across SIMULATION / SHADOW / LIVE: match the mode,
                # or the delay is measured from another mode's earlier order (~700 s).
                "SELECT created_at FROM orders WHERE signal_id = ? AND mode = ? "
                "ORDER BY created_at LIMIT 1",
                (signal_id, mode),
            ).fetchone()
            created_at = o[0] if o else None
        expected = _expected_price(conn, symbol, created_at, mode)
        delay_s = None
        if created_at:
            t0, t1 = _parse_ts(created_at), _parse_ts(at)
            if t0 and t1:
                delay_s = (t1 - t0).total_seconds()
        out.append({
            "id": tid,
            "at": at,
            "slot_id": slot_id,
            "strategy_key": key,
            "symbol": symbol,
            "action": action,
            "quantity": qty,
            "fill": price,
            "expected": expected,
            "slippage_bps": _slippage_bps(action, price, expected),
            "delay_s": delay_s,
        })
    return out


def round_trips(conn, mode="LIVE"):
    """Pair each CLOSE with the most recent unmatched OPEN of the same slot+strategy."""
    rows = conn.execute(
        "SELECT id, at, slot_id, strategy_key, symbol, action, price, reason "
        "FROM slot_trades WHERE mode = ? ORDER BY at, id",
        (mode,),
    ).fetchall()
    open_by_key = {}
    out = []
    for (tid, at, slot_id, key, symbol, action, price, reason) in rows:
        if action not in _ACTIONS:
            continue
        k = (slot_id, key)
        if action == "OPEN":
            open_by_key[k] = (at, price, symbol)
            continue
        opened = open_by_key.pop(k, None)
        if not opened:
            continue
        o_at, o_price, o_symbol = opened
        if o_price in (None, 0) or price is None:
            continue
        t0, t1 = _parse_ts(o_at), _parse_ts(at)
        holding_days = (t1 - t0).total_seconds() / 86400.0 if (t0 and t1) else None
        out.append({
            "strategy_key": key,
            "symbol": o_symbol or symbol,
            "opened": o_at,
            "closed": at,
            "open_price": o_price,
            "close_price": price,
            "gross_return": price / o_price - 1.0,
            "holding_days": holding_days,
            "exit_reason": reason,
        })
    return out


def _mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def by_strategy(conn, mode="LIVE"):
    fills = trades(conn, mode)
    trips = round_trips(conn, mode)
    keys = sorted({f["strategy_key"] for f in fills} | {t["strategy_key"] for t in trips})
    out = {}
    for key in keys:
        kf = [f for f in fills if f["strategy_key"] == key]
        kt = [t for t in trips if t["strategy_key"] == key]
        # Slippage averages only over fills that have a mark to compare against;
        # including markless fills as zero would understate execution cost.
        slip = [f["slippage_bps"] for f in kf if f["expected"] is not None]
        rets = [t["gross_return"] for t in kt]
        reasons = {}
        for t in kt:
            r = t["exit_reason"] or "unknown"
            reasons[r] = reasons.get(r, 0) + 1
        out[key] = {
            "n_fills": len(kf),
            "mean_slippage_bps": _mean(slip),
            "mean_delay_s": _mean([f["delay_s"] for f in kf]),
            "n_round_trips": len(kt),
            "mean_gross_return": _mean(rets),
            "win_rate": (sum(1 for r in rets if r > 0) / len(rets)) if rets else None,
            "exit_reasons": reasons,
        }
    return out


def _fmt(value, spec="%.2f"):
    return "n/a" if value is None else spec % value


def render(conn, mode="LIVE"):
    stats = by_strategy(conn, mode)
    fills = trades(conn, mode)
    lines = ["LIVE FEEDBACK (%s)" % mode, ""]
    if not stats:
        lines.append("no slot trades")
    for key in sorted(stats):
        s = stats[key]
        lines.append(key[:72])
        lines.append("  fills %d  slip %s bps  delay %s s" % (
            s["n_fills"], _fmt(s["mean_slippage_bps"]), _fmt(s["mean_delay_s"], "%.0f")))
        lines.append("  round trips %d  gross %s  win %s" % (
            s["n_round_trips"], _fmt(s["mean_gross_return"], "%.4f"),
            _fmt(s["win_rate"], "%.2f")))
        if s["exit_reasons"]:
            reasons = ", ".join("%s=%d" % (r, c)
                                for r, c in sorted(s["exit_reasons"].items()))
            lines.append("  exits: %s" % reasons)
        lines.append("")
    worst = [f for f in fills if f["slippage_bps"] is not None]
    worst.sort(key=lambda f: f["slippage_bps"], reverse=True)
    lines.append("WORST SLIPPAGE")
    if not worst:
        lines.append("  none")
    for f in worst[:10]:
        lines.append("  %s %s %s %s bps" % (
            f["at"], f["strategy_key"][:20], f["symbol"], _fmt(f["slippage_bps"])))
    return "\n".join(line[:72] for line in lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Live slot trade feedback (read-only)")
    ap.add_argument("--mode", default="LIVE")
    args = ap.parse_args(argv)
    path = load_config()["database"]["market_data_path"]
    conn = _connect(path)
    try:
        print(render(conn, args.mode))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
