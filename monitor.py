"""
Live dashboard for everything running on this box. Zero dependencies.

Three ways to watch, all from one file and all stdlib-only — no pip install, no
sudo, nothing to break when the VM is rebuilt:

    python monitor.py            # live terminal dashboard, refreshes in place
    python monitor.py --serve    # web page on http://localhost:8787
    python monitor.py --once     # single snapshot, for scripts and cron

The terminal mode works over SSH, which matters because this machine is usually
headless in practice. The web mode is the one to leave open on the XFCE desktop:
a browser in fullscreen is the closest thing to an always-on overlay that does
not need anything installed.

Deliberately read-only. It opens the database in read-only mode and never writes,
so leaving it running cannot interfere with a search, a ladder or the daily
capture — and it cannot become the eighth bug.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

from universe import load_config

ROOT = Path(__file__).parent
REFRESH = 10


def _db():
    """Read-only connection. A monitor must never be able to write."""
    cfg = load_config()
    p = cfg["database"]["market_data_path"]
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)


def _procs() -> list:
    """What of ours is actually running, with elapsed time and CPU."""
    out = []
    try:
        ps = subprocess.run(["ps", "-eo", "pid,etime,pcpu,rss,args"],
                            capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return out
    for line in ps.splitlines()[1:]:
        if "awk" in line or "monitor.py" in line:
            continue
        for tag in ("evolve.py", "promote.py", "daily.sh", "lab_loop.sh",
                    "value_metrics", "sec_fundamentals", "build_features",
                    "backfill.py", "conviction", "train_model", "bias_exposure"):
            if tag in line:
                f = line.split(None, 4)
                if len(f) >= 5:
                    out.append({"pid": f[0], "elapsed": f[1], "cpu": f[2],
                                "rss_gb": int(f[3]) / 1048576, "what": tag})
                break
    return out


def _tail(path: Path, pattern: str | None = None, n: int = 1) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        return ""
    if pattern:
        lines = [x for x in lines if re.search(pattern, x)]
    return lines[-n] if lines else ""


def snapshot() -> dict:
    s: dict = {"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    # --- system ---------------------------------------------------------
    try:
        s["load"] = os.getloadavg()[0]
    except Exception:
        s["load"] = 0.0
    try:
        mem = Path("/proc/meminfo").read_text()
        tot = int(re.search(r"MemTotal:\s+(\d+)", mem).group(1)) / 1048576
        av = int(re.search(r"MemAvailable:\s+(\d+)", mem).group(1)) / 1048576
        s["mem_used"], s["mem_total"] = tot - av, tot
    except Exception:
        s["mem_used"] = s["mem_total"] = 0.0
    du = shutil.disk_usage("/")
    s["disk_free_gb"] = du.free / 1e9
    s["disk_pct"] = du.used / du.total * 100
    s["cores"] = os.cpu_count() or 1
    s["procs"] = _procs()

    # --- the search loop -------------------------------------------------
    gen = _tail(ROOT / "logs/lab_loop_evolve.log", r"gen \d+/\d+")
    s["gen_line"] = gen.split("INFO:evolve:")[-1].strip() if gen else "(idle)"
    summary = ROOT / "data/lab_loop_summary.log"
    s["iterations"] = []
    if summary.exists():
        s["iterations"] = summary.read_text(errors="replace").splitlines()[-4:]
    s["loop_alive"] = any(p["what"] == "lab_loop.sh" for p in s["procs"])

    # --- database --------------------------------------------------------
    try:
        c = _db()
        q = lambda sql: c.execute(sql).fetchone()          # noqa: E731
        s["last_bar"] = q("SELECT MAX(date) FROM prices")[0]
        s["n_strategies"] = q("SELECT COUNT(*) FROM strategies")[0]
        s["n_evals"] = q("SELECT COUNT(*) FROM evaluations")[0]
        s["n_survivors"] = q("SELECT COUNT(*) FROM promotions WHERE stage='validation' "
                             "AND decision='pass'")[0]
        s["n_sealed"] = q("SELECT COUNT(*) FROM promotions WHERE stage='sealed' "
                          "AND decision='pass'")[0]
        s["runs"] = [dict(zip(("name", "cap", "eq", "stepped"), r)) for r in c.execute("""
            SELECT p.name, p.capital_usd,
                   COALESCE((SELECT equity_usd FROM paper_equity e WHERE e.run_id=p.run_id
                             ORDER BY date DESC LIMIT 1), p.capital_usd),
                   COALESCE(p.last_step_on,'-')
            FROM paper_runs p WHERE p.status='open' ORDER BY 3 DESC""")]
        c.close()
    except Exception as e:
        s["db_error"] = str(e)[:70]
    return s


# -- terminal rendering ------------------------------------------------------

C = {"r": "\033[0m", "b": "\033[1m", "dim": "\033[2m", "grn": "\033[32m",
     "red": "\033[31m", "yel": "\033[33m", "cyn": "\033[36m", "mag": "\033[35m"}


def _bar(frac: float, width: int = 18) -> str:
    """A meter that reads at a glance. Colour by pressure, not by prettiness."""
    frac = max(0.0, min(1.0, frac))
    fill = int(frac * width)
    col = C["grn"] if frac < 0.7 else (C["yel"] if frac < 0.9 else C["red"])
    return f"{col}{'█' * fill}{C['dim']}{'░' * (width - fill)}{C['r']}"


def render(s: dict) -> str:
    L = []
    A = L.append
    A(f"{C['b']}{C['cyn']}  STOCKBOT2000{C['r']}{C['dim']}   {s['time']}"
      f"   refresh {REFRESH}s   ctrl-C to quit{C['r']}")
    A("  " + "─" * 76)

    load_frac = s["load"] / max(s["cores"], 1)
    mem_frac = s["mem_used"] / max(s["mem_total"], 1e-9)
    A(f"  cpu   {_bar(load_frac)} {s['load']:>5.2f} / {s['cores']} cores")
    A(f"  mem   {_bar(mem_frac)} {s['mem_used']:>5.1f} / {s['mem_total']:.1f} GB")
    A(f"  disk  {_bar(s['disk_pct']/100)} {s['disk_free_gb']:>5.0f} GB free")
    A("")

    alive = f"{C['grn']}running{C['r']}" if s["loop_alive"] else f"{C['red']}STOPPED{C['r']}"
    A(f"  {C['b']}SEARCH LOOP{C['r']}  {alive}")
    A(f"    {s['gen_line'][:72]}")
    for line in s["iterations"]:
        m = re.search(r"iter\s+(\d+).*survivors\s+(\d+).*TRIALS ([\d,]+)", line)
        if m:
            col = C["grn"] if int(m.group(2)) else C["dim"]
            A(f"    {C['dim']}iter {m.group(1):>3}{C['r']}  "
              f"{col}{m.group(2):>3} survivors{C['r']}  "
              f"{C['dim']}{m.group(3)} cumulative trials{C['r']}")
    A("")

    if s.get("procs"):
        A(f"  {C['b']}RUNNING{C['r']}")
        for p in s["procs"]:
            A(f"    {p['what']:<18}{C['dim']}pid {p['pid']:<8}{C['r']}"
              f"{p['elapsed']:>10}{float(p['cpu']):>7.0f}% cpu{p['rss_gb']:>7.1f} GB")
    else:
        A(f"  {C['b']}RUNNING{C['r']}  {C['dim']}nothing{C['r']}")
    A("")

    A(f"  {C['b']}LADDER{C['r']}   "
      f"{s.get('n_strategies',0):,} strategies   "
      f"{s.get('n_evals',0):,} evaluations   "
      f"{s.get('n_survivors',0)} validated   "
      f"{C['mag']}{s.get('n_sealed',0)} sealed{C['r']}")
    A(f"  {C['dim']}last price bar {s.get('last_bar','?')}{C['r']}")
    A("")

    runs = s.get("runs", [])
    if runs:
        tot = sum(r["eq"] for r in runs)
        base = sum(r["cap"] for r in runs)
        col = C["grn"] if tot >= base else C["red"]
        A(f"  {C['b']}PAPER TRADING{C['r']}   {len(runs)} runs   "
          f"{col}${tot:,.2f} of ${base:,.0f}  ({tot-base:+,.2f}){C['r']}")
        for r in runs[:9]:
            pnl = r["eq"] - r["cap"]
            c = C["grn"] if pnl > 0 else (C["red"] if pnl < 0 else C["dim"])
            A(f"    {r['name']:<22}{c}{r['eq']:>8.2f}{pnl:>+9.2f}{C['r']}"
              f"  {C['dim']}{r['stepped']}{C['r']}")
        if len(runs) > 9:
            A(f"    {C['dim']}… and {len(runs)-9} more{C['r']}")
    if s.get("db_error"):
        A(f"  {C['red']}db: {s['db_error']}{C['r']}")
    return "\n".join(L)


def terminal_loop() -> None:
    try:
        while True:
            out = render(snapshot())
            # Redraw in place rather than scrolling: clear, home, print.
            print("\033[2J\033[H" + out, flush=True)
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        print("\033[?25h")


# -- web mode ----------------------------------------------------------------

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Stockbot2000</title><meta http-equiv="refresh" content="{refresh}">
<style>
:root{{--bg:#12140f;--fg:#e8e6df;--dim:#7d8177;--grn:#5fbe94;--red:#e8875b;
--yel:#d8bd6a;--cyn:#6fb5c9;--card:#1a1d17;--line:#2b2f26}}
*{{box-sizing:border-box}}
body{{background:var(--bg);color:var(--fg);margin:0;padding:18px;
font:13.5px/1.5 ui-monospace,'SF Mono',Menlo,monospace}}
h1{{font-size:17px;margin:0 0 2px;letter-spacing:.08em;color:var(--cyn)}}
.t{{color:var(--dim);font-size:12px;margin-bottom:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:13px 15px}}
.card h2{{font-size:11px;letter-spacing:.11em;text-transform:uppercase;
color:var(--dim);margin:0 0 10px;font-weight:600}}
table{{width:100%;border-collapse:collapse}}
td{{padding:2px 0;white-space:nowrap}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.grn{{color:var(--grn)}}.red{{color:var(--red)}}.yel{{color:var(--yel)}}.dim{{color:var(--dim)}}
.meter{{height:7px;background:#24271f;border-radius:4px;overflow:hidden;margin:4px 0 9px}}
.meter div{{height:100%}}
.big{{font-size:21px;font-variant-numeric:tabular-nums}}
</style></head><body>
<h1>STOCKBOT2000</h1><div class="t">{time} &middot; auto-refresh {refresh}s</div>
<div class="grid">{cards}</div></body></html>"""


def _meter(frac: float) -> str:
    frac = max(0.0, min(1.0, frac))
    col = "var(--grn)" if frac < .7 else ("var(--yel)" if frac < .9 else "var(--red)")
    return f'<div class="meter"><div style="width:{frac*100:.0f}%;background:{col}"></div></div>'


def html(s: dict) -> str:
    import html as H
    cards = []

    cards.append(
        '<div class="card"><h2>machine</h2>'
        f'<table><tr><td>cpu</td><td class="n">{s["load"]:.2f} / {s["cores"]}</td></tr></table>'
        f'{_meter(s["load"]/max(s["cores"],1))}'
        f'<table><tr><td>memory</td><td class="n">{s["mem_used"]:.1f} / {s["mem_total"]:.1f} GB</td></tr></table>'
        f'{_meter(s["mem_used"]/max(s["mem_total"],1e-9))}'
        f'<table><tr><td>disk</td><td class="n">{s["disk_free_gb"]:.0f} GB free</td></tr></table>'
        f'{_meter(s["disk_pct"]/100)}</div>')

    alive = ('<span class="grn">running</span>' if s["loop_alive"]
             else '<span class="red">STOPPED</span>')
    rows = ""
    for line in s["iterations"]:
        m = re.search(r"iter\s+(\d+).*survivors\s+(\d+).*TRIALS ([\d,]+)", line)
        if m:
            cls = "grn" if int(m.group(2)) else "dim"
            rows += (f'<tr><td class="dim">iter {m.group(1)}</td>'
                     f'<td class="n {cls}">{m.group(2)} survivors</td>'
                     f'<td class="n dim">{m.group(3)} trials</td></tr>')
    cards.append(f'<div class="card"><h2>search loop &middot; {alive}</h2>'
                 f'<div class="dim" style="margin-bottom:8px">{H.escape(s["gen_line"][:70])}</div>'
                 f'<table>{rows}</table></div>')

    prows = "".join(
        f'<tr><td>{H.escape(p["what"])}</td><td class="n dim">{p["elapsed"]}</td>'
        f'<td class="n">{float(p["cpu"]):.0f}%</td>'
        f'<td class="n dim">{p["rss_gb"]:.1f} GB</td></tr>' for p in s.get("procs", []))
    cards.append('<div class="card"><h2>running now</h2>'
                 f'<table>{prows or "<tr><td class=dim>nothing</td></tr>"}</table></div>')

    cards.append(
        '<div class="card"><h2>ladder</h2><table>'
        f'<tr><td>strategies</td><td class="n">{s.get("n_strategies",0):,}</td></tr>'
        f'<tr><td>evaluations</td><td class="n">{s.get("n_evals",0):,}</td></tr>'
        f'<tr><td>validated</td><td class="n grn">{s.get("n_survivors",0)}</td></tr>'
        f'<tr><td>sealed</td><td class="n yel">{s.get("n_sealed",0)}</td></tr>'
        f'<tr><td>last bar</td><td class="n dim">{s.get("last_bar","?")}</td></tr>'
        '</table></div>')

    runs = s.get("runs", [])
    if runs:
        tot = sum(r["eq"] for r in runs); base = sum(r["cap"] for r in runs)
        cls = "grn" if tot >= base else "red"
        rr = "".join(
            f'<tr><td>{H.escape(r["name"])}</td>'
            f'<td class="n">{r["eq"]:.2f}</td>'
            f'<td class="n {"grn" if r["eq"]>=r["cap"] else "red"}">{r["eq"]-r["cap"]:+.2f}</td></tr>'
            for r in runs)
        cards.append(f'<div class="card" style="grid-column:1/-1"><h2>paper trading '
                     f'&middot; {len(runs)} runs</h2>'
                     f'<div class="big {cls}">${tot:,.2f} <span class="dim" '
                     f'style="font-size:13px">of ${base:,.0f} &nbsp; {tot-base:+,.2f}</span></div>'
                     f'<table style="margin-top:8px">{rr}</table></div>')
    return PAGE.format(time=s["time"], refresh=REFRESH, cards="".join(cards))


def serve(port: int = 8787) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = html(snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass                      # a dashboard should not spam its own log

    # Bound to localhost only. This exposes account positions and should not be
    # reachable from the network; to view it remotely, tunnel over SSH:
    #   ssh -L 8787:localhost:8787 stockpicker@<host>
    srv = HTTPServer(("127.0.0.1", port), H)
    print(f"  dashboard on http://localhost:{port}  (localhost only; ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    global REFRESH          # must precede every use of the name, including the
                            # --refresh default below
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--refresh", type=int, default=REFRESH)
    a = ap.parse_args()
    REFRESH = a.refresh
    if a.serve:
        serve(a.port)
    elif a.once:
        print(render(snapshot()))
    else:
        terminal_loop()


if __name__ == "__main__":
    main()
