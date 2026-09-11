"""
The experiment leaderboard. Every idea this project tries, ranked by money.

One table for backtests, paper runs and lab strategies alike, because the
question that actually needs answering is "is idea 2 better than idea 1" — and
that is settled by comparing net P&L on a like-for-like basis, not by comparing a
backtest AUC against a paper-trading win rate.

Absolute figures from backtests remain survivorship-inflated and always will be
until delisted prices exist. Relative figures are far more robust, because both
ideas carry the same bias. That holds best between similar strategies: a
dip-buyer is inflated more than a trend-follower, since the dips that never
recovered are exactly what is missing from the data.

Usage:
    python experiments.py                      # leaderboard, best money first
    python experiments.py --kind backtest      # one kind only
    python experiments.py --show <id>          # one experiment in detail
    python experiments.py --compare A B        # two ideas side by side
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json

import storage
from universe import load_config


def _fmt(v, spec="+,.2f", dash="—"):
    return dash if v is None else format(v, spec)


def leaderboard(conn, kind: str | None, limit: int) -> None:
    rows = storage.leaderboard(conn, kind, limit)
    if not rows:
        print("No experiments recorded yet.\n"
              "  backtest.py --name <label>   records one\n"
              "  paper_trading.py --record    records a forward run")
        return

    print(f"{'NET P&L':>11} {'%cap':>7} {'verdict':>10} {'trades':>8} "
          f"{'costs':>10} {'maxDD':>7} {'kind':>9}  name")
    print("-" * 96)
    for r in rows:
        verdict = "PROFIT" if (r["net_pnl_usd"] or 0) > 0 else "LOSS"
        print(f"{_fmt(r['net_pnl_usd']):>11} {_fmt(r['net_pnl_pct'], '+.1f'):>7} "
              f"{verdict:>10} {r['n_trades'] or 0:>8,} {_fmt(r['costs_usd'], ',.2f'):>10} "
              f"{_fmt(r['max_drawdown_pct'], '.1f'):>7} {r['kind']:>9}  {r['name']}")

    best = rows[0]
    print()
    if (best["net_pnl_usd"] or 0) > 0:
        print(f"  Best: {best['name']} at {_fmt(best['net_pnl_usd'])} — the number to beat.")
    else:
        print(f"  Nothing profitable yet. Best is {best['name']} at "
              f"{_fmt(best['net_pnl_usd'])}, so the bar is simply 'above zero'.")


def show(conn, exp_id: str) -> None:
    r = conn.execute("SELECT * FROM experiments WHERE id = ? OR name = ?",
                     (exp_id, exp_id)).fetchone()
    if not r:
        print(f"No experiment '{exp_id}'.")
        return
    r = dict(r)
    print(f"\n{r['name']}  ({r['kind']})")
    print("=" * 60)
    print(f"  NET P&L            {_fmt(r['net_pnl_usd'])}  "
          f"({'PROFITABLE' if (r['net_pnl_usd'] or 0) > 0 else 'LOSS'})")
    print(f"  as % of capital    {_fmt(r['net_pnl_pct'], '+.1f')}%")
    print(f"  gross P&L          {_fmt(r['gross_pnl_usd'])}")
    print(f"  costs              {_fmt(r['costs_usd'], ',.2f')}")
    print(f"  trades             {r['n_trades'] or 0:,}")
    print(f"  win rate           {_fmt(r['win_rate_pct'], '.1f')}%")
    print(f"  max drawdown       {_fmt(r['max_drawdown_pct'], '.1f')}%")
    print(f"  avg days held      {_fmt(r['avg_days_held'], '.1f')}")
    print(f"  period             {r['period_start']} -> {r['period_end']}")
    if r["notes"]:
        print(f"  notes              {r['notes']}")

    worst = conn.execute("""
        SELECT ticker, net_pnl_usd, pnl_pct, exit_reason FROM experiment_trades
        WHERE experiment_id = ? ORDER BY net_pnl_usd ASC LIMIT 5
    """, (r["id"],)).fetchall()
    if worst:
        print("\n  worst trades:")
        for t in worst:
            print(f"    {t['ticker']:<8} {_fmt(t['net_pnl_usd'])}  "
                  f"{_fmt(t['pnl_pct'], '+.1f')}%  {t['exit_reason']}")


def compare(conn, a: str, b: str) -> None:
    """
    Two ideas side by side.

    The comparison is the point. Both carry the same survivorship inflation, so
    the difference between them is far more trustworthy than either number alone.
    """
    rows = []
    for key in (a, b):
        r = conn.execute("SELECT * FROM experiments WHERE id = ? OR name = ?",
                         (key, key)).fetchone()
        if not r:
            print(f"No experiment '{key}'.")
            return
        rows.append(dict(r))
    x, y = rows

    print(f"\n{'':<22}{x['name'][:24]:>24}{y['name'][:24]:>24}")
    print("-" * 70)
    for label, field, spec in [
        ("NET P&L", "net_pnl_usd", "+,.2f"),
        ("% of capital", "net_pnl_pct", "+.1f"),
        ("gross P&L", "gross_pnl_usd", "+,.2f"),
        ("costs", "costs_usd", ",.2f"),
        ("trades", "n_trades", ",d"),
        ("win rate %", "win_rate_pct", ".1f"),
        ("max drawdown %", "max_drawdown_pct", ".1f"),
    ]:
        print(f"{label:<22}{_fmt(x[field], spec):>24}{_fmt(y[field], spec):>24}")

    diff = (y["net_pnl_usd"] or 0) - (x["net_pnl_usd"] or 0)
    winner = y["name"] if diff > 0 else x["name"]
    print("-" * 70)
    print(f"  {winner} is better by {abs(diff):,.2f} in net P&L.")
    print("  Both carry the same survivorship inflation, so the gap between them\n"
          "  is more trustworthy than either figure on its own.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kind", choices=["backtest", "paper", "live"])
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--show", metavar="ID")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"))
    args = parser.parse_args()

    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)

    if args.show:
        show(conn, args.show)
    elif args.compare:
        compare(conn, *args.compare)
    else:
        leaderboard(conn, args.kind, args.limit)
    conn.close()


if __name__ == "__main__":
    main()
