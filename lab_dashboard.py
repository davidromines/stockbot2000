"""
The lab dashboard. Phase 10.

Writes a self-contained HTML page showing what the search found, ranked by money.
No server, no dependencies — open the file.

**Net P&L leads every table.** Fitness, Sharpe and trade counts are shown because
they explain *why* a strategy scored as it did, but they are diagnostics. A
strategy that loses money is not interesting no matter how elegant its Sharpe, and
a dashboard that leads with Sharpe invites exactly the wrong conclusion.

Also renders the family tree of the best strategy. A winner arrived at through a
visible line of improving ancestors is a different proposition from one that
appeared fully formed from a random draw — the first is evidence the search is
working, the second is a lottery ticket.

Usage:
    python lab_dashboard.py                 # newest run
    python lab_dashboard.py --run <id>
    python lab_dashboard.py --open          # also print the file path
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import html
import json
from pathlib import Path

import ledger
import storage
from universe import load_config

CSS = """
:root{--bg:#F6F5F1;--surface:#fff;--border:#DEDBD3;--text:#20221F;--soft:#5C5F58;
--mute:#8A8D85;--accent:#2B6E52;--win:#1F8A5F;--loss:#A5471F;--track:#E7E4DC}
@media(prefers-color-scheme:dark){:root{--bg:#181A17;--surface:#212420;--border:#383B35;
--text:#ECEAE3;--soft:#B2B4AB;--mute:#82857D;--accent:#5FBE94;--win:#3ED28C;
--loss:#E8875B;--track:#33362F}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--text);margin:0;padding:0 20px 60px;
font:14px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.wrap{max-width:1040px;margin:0 auto}
header{padding:40px 0 20px;border-bottom:1px solid var(--border);margin-bottom:28px}
h1{margin:0 0 6px;font-size:28px;letter-spacing:-.01em}
h2{font-size:18px;margin:32px 0 10px}
.sub{color:var(--soft);margin:0;max-width:70ch}
.mono{font-family:ui-monospace,'SF Mono',Menlo,monospace}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
border:1px solid var(--border);border-radius:10px;overflow:hidden;
background:var(--surface);margin:22px 0}
.tile{padding:16px 18px;border-right:1px solid var(--border)}
.tile:last-child{border-right:none}
.tile .v{font-family:ui-monospace,monospace;font-size:22px;font-weight:600;
font-variant-numeric:tabular-nums}
.tile .k{font-size:12.5px;color:var(--soft);margin-top:3px}
.win{color:var(--win)}.loss{color:var(--loss)}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-bottom:8px}
th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;
color:var(--mute);padding:0 8px 8px 0;border-bottom:1px solid var(--border)}
td{padding:8px 8px 8px 0;border-bottom:1px solid var(--border);color:var(--soft)}
td.num{text-align:right;font-family:ui-monospace,monospace;
font-variant-numeric:tabular-nums;color:var(--text)}
td.rule{font-family:ui-monospace,monospace;font-size:12px;color:var(--text)}
.note{font-size:13px;color:var(--mute);border-left:2px solid var(--border);
padding-left:10px;margin:14px 0;max-width:74ch}
.note.warn{border-left-color:var(--loss);color:var(--soft)}
.wrapx{overflow-x:auto}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);
color:var(--mute);font-size:13px}
"""


def _money(v) -> str:
    if v is None:
        return '<td class="num">—</td>'
    cls = "win" if v > 0 else ("loss" if v < 0 else "")
    return f'<td class="num {cls}">{v:+,.2f}</td>'


def build(conn, run_id: str | None, out_path: Path) -> Path:
    run = conn.execute(
        "SELECT * FROM lab_runs WHERE run_id = ? " if run_id else
        "SELECT * FROM lab_runs ORDER BY started_at DESC LIMIT 1",
        (run_id,) if run_id else ()).fetchone()
    if not run:
        raise SystemExit("No lab runs recorded. Run evolve.py first.")
    run = dict(run)
    stats = ledger.run_stats(conn, run["run_id"])
    top = ledger.top_by_pnl(conn, run["run_id"], limit=25)

    best_pnl = stats.get("best_pnl") or 0
    profitable = stats.get("profitable") or 0
    evaluated = stats.get("evaluated") or 0

    rows = "".join(
        f"<tr><td class='num'>{i}</td>{_money(r['net_pnl_usd'])}"
        f"<td class='num'>{r['fitness']:.3f}</td>"
        f"<td class='num'>{r['n_trades']:,}</td>"
        f"<td class='num'>{r['generation']}</td>"
        f"<td>{html.escape(r['origin'])}</td>"
        f"<td class='rule'>{html.escape((r['entry_desc'] or '')[:120])}</td></tr>"
        for i, r in enumerate(top, start=1))

    tree = ""
    if top:
        chain = ledger.lineage(conn, top[0]["id"])
        tree = "".join(
            f"<tr><td class='num'>{c['generation']}</td>"
            f"<td>{html.escape(c['origin'])}</td>"
            f"<td class='num'>{(c['fitness'] or 0):.3f}</td>"
            f"{_money(c['net_pnl_usd'])}"
            f"<td class='rule'>{html.escape((c['entry_desc'] or '')[:110])}</td></tr>"
            for c in chain)

    ladder = "".join(
        f"<tr><td>{s}</td><td class='num'>{r['p'] or 0}</td>"
        f"<td class='num'>{r['f'] or 0}</td><td class='num'>{r['v'] or 0}</td></tr>"
        for s in ("shortlist", "validation", "sealed", "paper", "funded")
        for r in [conn.execute(
            "SELECT SUM(decision='pass') p, SUM(decision='fail') f, "
            "SUM(decision='void') v FROM promotions WHERE stage=?", (s,)).fetchone()])

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stockbot2000 Lab</title><style>{CSS}</style></head><body><div class="wrap">
<header>
  <h1>Strategy Lab</h1>
  <p class="sub">Run <span class="mono">{run['run_id']}</span> ·
  search window {run['window_start']} to {run['window_end']} ·
  started {run['started_at']}</p>
</header>

<div class="tiles">
  <div class="tile"><div class="v {'win' if best_pnl > 0 else 'loss'}">{best_pnl:+,.0f}</div>
    <div class="k">Best net P&amp;L (USD)</div></div>
  <div class="tile"><div class="v">{profitable:,}</div>
    <div class="k">Profitable of {evaluated:,} evaluated</div></div>
  <div class="tile"><div class="v">{(profitable / evaluated * 100) if evaluated else 0:.0f}%</div>
    <div class="k">Hit rate of the search</div></div>
  <div class="tile"><div class="v">{run['generations']}&times;{run['population']}</div>
    <div class="k">Generations &times; population</div></div>
</div>

<p class="note warn"><strong>These are in-sample figures on the search window.</strong>
A strategy appearing here has cleared nothing yet — the ladder below is what
separates a finding from a coincidence. Net P&amp;L is also computed over sampled
signals rather than a live portfolio, so treat it as a ranking, not a forecast.</p>

<h2>Best strategies by money</h2>
<div class="wrapx"><table>
<tr><th>#</th><th>Net P&amp;L</th><th>Fitness</th><th>Trades</th><th>Gen</th>
<th>Origin</th><th>Entry rule</th></tr>
{rows or '<tr><td colspan="7">Nothing evaluated.</td></tr>'}
</table></div>

<h2>How the best one was arrived at</h2>
<p class="note">A winner reached through a visible line of improving ancestors is
evidence the search is working. One that appeared fully formed from a random draw
is a lottery ticket. The difference matters more than the P&amp;L.</p>
<div class="wrapx"><table>
<tr><th>Gen</th><th>Origin</th><th>Fitness</th><th>Net P&amp;L</th><th>Entry rule</th></tr>
{tree or '<tr><td colspan="5">No lineage.</td></tr>'}
</table></div>

<h2>Promotion ladder</h2>
<table><tr><th>Stage</th><th>Pass</th><th>Fail</th><th>Void</th></tr>{ladder}</table>
<p class="note">Most candidates dying at validation is the system working
correctly. The sealed holdout may be opened exactly once per strategy, and that
rule is enforced in code.</p>
<p class="note warn"><strong>Void</strong> means the verdict was withdrawn because
the benchmark behind it was later found to be wrong &mdash; not that the strategy
failed. Voided candidates at the earlier stages are eligible to be judged again on
correct terms; a voided <em>sealed</em> result is not, because the strategy has
already seen that data whatever the verdict said.</p>

<footer>Generated by <span class="mono">lab_dashboard.py</span>.
Nothing here is investment advice, and no backtested result is a prediction of
future returns.</footer>
</div></body></html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", dest="run_id")
    parser.add_argument("--out", default="data/lab_dashboard.html")
    args = parser.parse_args()

    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    ledger.init(conn)
    path = build(conn, args.run_id, Path(args.out))
    conn.close()
    print(f"Wrote {path.resolve()}")


if __name__ == "__main__":
    main()
