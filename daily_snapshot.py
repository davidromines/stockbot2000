"""
One-page daily snapshot (owner, 2026-10-12): a single image, not a wall of text.

The owner's complaint: asking "is it working" got a 17-section text report
(`eod_report.py`) meant for debugging, not a glance-and-know answer. This renders
one portrait image — account P&L big and in color, each of the 5 slots as a small
card with its own sparkline, one plain-English line at the bottom — and sends it
as a Telegram photo instead of text.

A slot gets reassigned to a different strategy over time (`slots.py`), so a slot's
chart and $ figure are scoped to its CURRENT assignment only — mixing two
strategies' price history into one line would misrepresent both. No fee/cost
breakdown is shown anywhere on this page (the owner does not want it); every
number is already net.

    ./venv/bin/python daily_snapshot.py --mode LIVE --dry-run     # numbers only
    ./venv/bin/python daily_snapshot.py --mode LIVE --out x.png   # render, don't send
    ./venv/bin/python daily_snapshot.py --mode LIVE --send        # render and push to Telegram
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import os
import sqlite3
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

import killswitch
import live_pnl
import slots
from universe import load_config

GREEN = "#1a8754"
RED = "#c0392b"
GRAY = "#8a8f98"
CARD_GREEN = "#e7f6ec"
CARD_RED = "#fbeceb"
CARD_GRAY = "#f0f1f3"
SLOT_IDS = (1, 2, 3, 4, 5)


def _color(x) -> str:
    if x is None:
        return GRAY
    return GREEN if x > 0 else (RED if x < 0 else GRAY)


def _card_color(x) -> str:
    if x is None:
        return CARD_GRAY
    return CARD_GREEN if x > 0 else (CARD_RED if x < 0 else CARD_GRAY)


def _human_name(conn, strategy_key: str, version) -> str:
    """
    A name meant for a non-technical reader. Hand-named strategies already have
    one (`league_strategies.name` / `paper_runs.label`); a Lab-discovered survivor
    does not — its own "name" is the raw rule expression it evolved
    (`family='lab_search'`), e.g. "Lab 56f07a: ((rank(chaikin_osc) > 0.64 ...)".
    That is exactly the jargon this report exists to hide, so it is replaced with
    a short generic label instead of truncated (truncating just hides the jargon
    mid-word rather than removing it).
    """
    if not strategy_key:
        return "?"
    if strategy_key.startswith("paper:"):
        r = conn.execute("SELECT label, name, family FROM paper_runs WHERE run_id=?",
                         (strategy_key[6:],)).fetchone()
        if r:
            label, name, family = r
            if family == "lab_search":
                return f"Lab-discovered strategy ({(name or strategy_key)[-8:]})"
            if label or name:
                return label or name
        return "strategy"
    r = conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                     (strategy_key, version)).fetchone()
    return r[0] if r and r[0] else strategy_key


def collect(conn, cfg: dict, mode: str = "LIVE") -> dict:
    """All the numbers this report needs. No matplotlib here — keeps this testable."""
    out = {"mode": mode, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    out["kill_switch"] = killswitch.global_engaged()

    rows = conn.execute("SELECT at, session, equity FROM live_equity ORDER BY at").fetchall()
    if rows:
        start_equity = rows[0][2]
        latest_at, latest_session, latest_equity = rows[-1]
        today = [r for r in rows if r[1] == latest_session]
        today_start = today[0][2] if today else latest_equity
        out["account"] = {
            "equity": latest_equity,
            "pnl_usd": latest_equity - start_equity,
            "pnl_pct": (latest_equity / start_equity - 1) * 100 if start_equity else None,
            "today_pnl_usd": latest_equity - today_start,
            "today_pnl_pct": (latest_equity / today_start - 1) * 100 if today_start else None,
            "curve": [r[2] for r in rows],
            "since_date": rows[0][0][:10],
            "latest_date": latest_at[:10],
        }
        out["days_live"] = len({r[1] for r in rows})
    else:
        out["account"] = None
        out["days_live"] = 0

    cur = slots.current(conn, cfg)
    pnl = live_pnl.compute(conn, cfg, mode)
    slot_results = {}
    for slot_id in SLOT_IDS:
        holder = cur.get(slot_id)
        if holder is None:
            slot_results[slot_id] = {"empty": True}
            continue
        since = holder["since"]
        name = _human_name(conn, holder["strategy_key"], holder["version"])
        closed = [t for t in pnl["closed"] if t["slot"] == slot_id and t["opened"] >= since]
        open_ = [t for t in pnl["open"] if t["slot"] == slot_id and t["opened"] >= since]
        realized_net = sum(t["net"] for t in closed)
        symbol = entry = qty = mark = unreal_gross = ret_pct = opened_at = None
        if open_:
            o = open_[0]
            symbol, entry, qty, mark = o["symbol"], o["entry"], o["quantity"], o["mark"]
            unreal_gross, ret_pct, opened_at = o["gross"], o["ret_pct"], o["opened"]
        total_net = realized_net + (unreal_gross or 0.0)
        spark = []
        if symbol and entry:
            mark_rows = conn.execute(
                "SELECT price FROM slot_marks WHERE slot_id=? AND mode=? AND at>=? AND symbol=? "
                "AND price IS NOT NULL ORDER BY at", (slot_id, mode, since, symbol)).fetchall()
            spark = [0.0] + [(p / entry - 1) * 100 for (p,) in mark_rows]  # 0.0: the entry itself
        days_held = None
        if opened_at:
            days_held = max(0, (dt.datetime.now(dt.timezone.utc) -
                                dt.datetime.fromisoformat(opened_at)).days)
        slot_results[slot_id] = {
            "empty": False, "symbol": symbol, "name": name, "since": since,
            "entry": entry, "mark": mark, "quantity": qty,
            "net_usd": total_net if (open_ or closed) else None, "ret_pct": ret_pct,
            "days_held": days_held, "spark": spark, "closed_trades": len(closed),
        }
    out["slots"] = slot_results
    return out


def _footer_line(data: dict) -> str:
    if data["kill_switch"]:
        return f"⚠ Trading halted: {data['kill_switch']}"
    acct = data["account"]
    if not acct:
        return "No live trading history yet."
    days = data["days_live"]
    direction = "up" if acct["pnl_usd"] > 0 else ("down" if acct["pnl_usd"] < 0 else "flat")
    line = (f"Live {days} trading day{'s' if days != 1 else ''}. Account is {direction} "
           f"${abs(acct['pnl_usd']):.2f} ({acct['pnl_pct']:+.1f}%) since launch.")
    if days < 30:
        line += " Still too early to call it a trend."
    return line


def _caption(data: dict) -> str:
    acct = data["account"]
    date = data["generated_at"][:10]
    if not acct:
        return f"Stockbot2000 — {date}"
    verdict = "PROFITABLE" if acct["pnl_usd"] > 0 else ("LOSING" if acct["pnl_usd"] < 0 else "FLAT")
    return f"Stockbot2000 — {date} — {verdict} {acct['pnl_usd']:+.2f} ({acct['pnl_pct']:+.1f}%)"


def _sparkline(ax, series, color):
    ax.axis("off")
    if not series or len(series) < 2:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=9, color=GRAY,
                transform=ax.transAxes)
        return
    ax.plot(range(len(series)), series, color=color, linewidth=2.2)
    ax.axhline(0, color="#c7c9cc", linewidth=0.8, linestyle="--")
    ax.margins(x=0.03, y=0.15)


def _slot_card(ax, slot_id: int, s: dict):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    if s.get("empty"):
        ax.add_patch(FancyBboxPatch((0.01, 0.06), 0.98, 0.88, boxstyle="round,pad=0,rounding_size=0.03",
                                    linewidth=0, facecolor=CARD_GRAY, transform=ax.transAxes))
        ax.text(0.04, 0.5, f"SLOT {slot_id}", fontsize=15, fontweight="bold", color="#555",
               va="center", transform=ax.transAxes)
        ax.text(0.97, 0.5, "CASH — no strategy assigned", fontsize=13, color=GRAY, ha="right",
               va="center", transform=ax.transAxes)
        return
    net, ret = s.get("net_usd"), s.get("ret_pct")
    ax.add_patch(FancyBboxPatch((0.01, 0.06), 0.98, 0.88, boxstyle="round,pad=0,rounding_size=0.03",
                                linewidth=0, facecolor=_card_color(net), transform=ax.transAxes))
    ax.text(0.04, 0.72, f"SLOT {slot_id}  —  {s['symbol'] or 'no position'}", fontsize=16,
           fontweight="bold", color="#222", va="center", transform=ax.transAxes)
    ax.text(0.04, 0.30, (s["name"] or "")[:40], fontsize=11, color="#555", va="center",
           transform=ax.transAxes)
    if net is None:
        ax.text(0.97, 0.5, "no open position yet", fontsize=13, color=GRAY, ha="right",
               va="center", transform=ax.transAxes)
        return
    ax.text(0.62, 0.72, f"{net:+.2f}", fontsize=20, fontweight="bold", color=_color(net),
           ha="right", va="center", transform=ax.transAxes)
    sub = f"{ret:+.1f}%" if ret is not None else ""
    if s.get("days_held") is not None:
        sub += f"  ·  held {s['days_held']}d"
    ax.text(0.62, 0.32, sub, fontsize=11, color="#555", ha="right", va="center",
           transform=ax.transAxes)
    spark_ax = ax.inset_axes([0.66, 0.12, 0.32, 0.72], transform=ax.transAxes)
    _sparkline(spark_ax, s.get("spark") or [], _color(net))


def render(data: dict, out_path: str) -> None:
    fig = plt.figure(figsize=(10.8, 13.5), dpi=100)
    fig.patch.set_facecolor("white")
    gs = fig.add_gridspec(nrows=8, ncols=1, height_ratios=[0.5, 2.6, 1.35, 1.35, 1.35, 1.35, 1.35, 0.6],
                          left=0.04, right=0.96, top=0.98, bottom=0.02, hspace=0.35)

    title_ax = fig.add_subplot(gs[0]); title_ax.axis("off")
    title_ax.text(0, 0.5, "STOCKBOT2000", fontsize=22, fontweight="bold", color="#222",
                 va="center", transform=title_ax.transAxes)
    title_ax.text(1, 0.5, data["generated_at"][:10], fontsize=16, color="#777", ha="right",
                 va="center", transform=title_ax.transAxes)

    head_ax = fig.add_subplot(gs[1]); head_ax.set_xlim(0, 1); head_ax.set_ylim(0, 1); head_ax.axis("off")
    acct = data["account"]
    if acct:
        verdict = "PROFITABLE" if acct["pnl_usd"] > 0 else ("LOSING" if acct["pnl_usd"] < 0 else "FLAT")
        color = _color(acct["pnl_usd"])
        head_ax.add_patch(FancyBboxPatch((0, 0.08), 1, 0.84, boxstyle="round,pad=0,rounding_size=0.02",
                                         linewidth=0, facecolor=_card_color(acct["pnl_usd"]),
                                         transform=head_ax.transAxes))
        head_ax.text(0.04, 0.78, "REAL ACCOUNT", fontsize=14, color="#666", va="center",
                    transform=head_ax.transAxes)
        head_ax.text(0.04, 0.48, f"{acct['pnl_usd']:+.2f}", fontsize=52, fontweight="bold",
                    color=color, va="center", transform=head_ax.transAxes)
        head_ax.text(0.04, 0.20, f"{acct['pnl_pct']:+.1f}%  since {acct['since_date']}  —  "
                                 f"{verdict}", fontsize=15, fontweight="bold", color=color,
                    va="center", transform=head_ax.transAxes)
        head_ax.text(0.97, 0.78, "TODAY", fontsize=13, color="#666", ha="right", va="center",
                    transform=head_ax.transAxes)
        today_color = _color(acct["today_pnl_usd"])
        head_ax.text(0.97, 0.52, f"{acct['today_pnl_usd']:+.2f}", fontsize=22, fontweight="bold",
                    color=today_color, ha="right", va="center", transform=head_ax.transAxes)
        spark_ax = head_ax.inset_axes([0.42, 0.14, 0.52, 0.28], transform=head_ax.transAxes)
        _sparkline(spark_ax, acct["curve"], color)
    else:
        head_ax.text(0.5, 0.5, "No live trading history yet.", fontsize=16, color=GRAY,
                    ha="center", va="center", transform=head_ax.transAxes)

    for i, slot_id in enumerate(SLOT_IDS):
        ax = fig.add_subplot(gs[2 + i])
        _slot_card(ax, slot_id, data["slots"].get(slot_id, {"empty": True}))

    foot_ax = fig.add_subplot(gs[7]); foot_ax.axis("off")
    foot_ax.text(0.5, 0.5, _footer_line(data), fontsize=12, color="#555", ha="center",
                va="center", transform=foot_ax.transAxes, wrap=True)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, facecolor="white")
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="LIVE")
    ap.add_argument("--out", default="reports/daily_snapshot.png")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the numbers only; render nothing")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    data = collect(conn, cfg, a.mode)

    acct = data["account"]
    if acct:
        print(f"account: ${acct['equity']:.2f}  since {acct['since_date']}: {acct['pnl_usd']:+.2f} "
             f"({acct['pnl_pct']:+.1f}%)  today: {acct['today_pnl_usd']:+.2f}")
    else:
        print("account: no live_equity rows")
    for slot_id in SLOT_IDS:
        s = data["slots"].get(slot_id, {})
        if s.get("empty"):
            print(f"  slot {slot_id}: CASH")
        elif not s.get("symbol"):
            print(f"  slot {slot_id}: {s.get('name')} — no open position")
        else:
            ret = f"{s['ret_pct']:+.1f}%" if s.get("ret_pct") is not None else "n/a"
            print(f"  slot {slot_id}: {s['symbol']} ({s['name']})  net {s['net_usd']:+.2f}  {ret}  "
                 f"held {s.get('days_held')}d")
    print(_footer_line(data))

    if a.dry_run:
        return 0
    render(data, a.out)
    print(f"wrote {a.out}")
    if a.send:
        import notify
        ok = notify.send_telegram_photo(a.out, _caption(data))
        print("sent" if ok else "send FAILED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
