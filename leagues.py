"""
Nine leagues, one evidence source. Phase 13 §16-17, §19, §33; Addendum B §B3,
B4, B11. Step H8.

A strategy competes only inside its league, on that league's horizon. Every
figure comes from the same place:

    net, gross, costs   accounting.py (fund_accounting, liquidation basis)
    sessions, trades    the fund's own forward record
    drawdown            the fund's recorded equity curve

so a tactical fund and the Value Fund are measured the same way and judged by
different clocks.

TIERS (B11)
-----------
    INSUFFICIENT_SAMPLE  fewer sessions or closed trades than the league needs
    NOT_ELIGIBLE         enough evidence, but net <= 0 or drawdown over limit
    ELIGIBLE             enough evidence, positive net, drawdown within limit
    ESTABLISHED          ELIGIBLE and past the league's established_sessions

Benchmarks are reported, never gating (B20).

    python leagues.py --sync        register Value / crypto funds, §19 labels
    python leagues.py --standings   every league, ranked by net P&L
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3

import league
import storage
import strategy_objects as so
from universe import load_config

LIVE_STATES = (league.PAPER, league.QUALIFIED, league.LIVE_CANDIDATE, league.LIVE,
               league.ELIGIBLE)


def init(conn) -> None:
    so.init(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS factory_paper_link (
            strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
            run_id TEXT NOT NULL, enrolled_on TEXT NOT NULL,
            PRIMARY KEY (strategy_key, version))""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS league_standings (
            as_of TEXT NOT NULL, league TEXT NOT NULL, strategy_key TEXT NOT NULL,
            version INTEGER NOT NULL, rank INTEGER, tier TEXT NOT NULL,
            net_usd REAL, gross_usd REAL, costs_usd REAL, sessions INTEGER,
            closed_trades INTEGER, max_drawdown_pct REAL, family TEXT, detail TEXT,
            PRIMARY KEY (as_of, strategy_key, version))""")
    conn.commit()


def fund_ref(conn, key: str, version: int = 1):
    """(fund_kind, fund_id) holding this strategy's forward record, or None."""
    if key.startswith("paper:"):
        return "paper", key.split(":", 1)[1]
    if key.startswith("pair:"):
        return "pair", key.split(":", 1)[1]
    if key.startswith("value:"):
        return "value", key.split(":", 1)[1]
    if key.startswith("crypto:"):
        return "crypto", key.split(":", 1)[1]
    r = conn.execute("SELECT run_id FROM factory_paper_link WHERE strategy_key=? AND version=?",
                     (key, version)).fetchone()
    return ("paper", r[0]) if r else None


def league_of(conn, cfg, key: str, version: int = 1) -> str:
    m = so.meta(conn, key, version)
    if m and m.get("league"):
        return m["league"]
    row = conn.execute("SELECT family FROM league_strategies WHERE strategy_key=? "
                       "ORDER BY version DESC LIMIT 1", (key,)).fetchone()
    fam = row[0] if row else None
    return (cfg.get("league_families") or {}).get(fam, "tactical")


def family_of(conn, key: str, version: int = 1) -> str:
    """The concentration family (§18). Stop-width variants of one rule share it."""
    m = so.meta(conn, key, version)
    if m and m.get("family"):
        return m["family"]
    name = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? "
                         "ORDER BY version DESC LIMIT 1", (key,)).fetchone() or [""])[0]
    # Legacy funds: the rule is the name before the " · " variant suffix, and
    # lettered siblings ("Crash Buyer 20d a/b/c") are one rule too.
    base = name.split(" · ")[0].strip()
    parts = base.split()
    if parts and len(parts[-1]) == 1 and parts[-1].isalpha():
        base = " ".join(parts[:-1])
    return base.lower().replace(" ", "_") or key


def _max_dd(conn, kind: str, fid: str) -> float | None:
    q = {"paper": ("SELECT equity_usd FROM paper_equity WHERE run_id=? ORDER BY date"),
         "pair": ("SELECT equity_usd FROM pair_fund_equity WHERE name=? ORDER BY date"),
         "value": ("SELECT equity_usd FROM value_fund_equity WHERE name=? ORDER BY date"),
         "crypto": ("SELECT equity_usd FROM crypto_fund_equity WHERE name=? ORDER BY date")}[kind]
    peak, dd = None, 0.0
    for (e,) in conn.execute(q, (fid,)):
        peak = e if peak is None else max(peak, e)
        if peak:
            dd = max(dd, (peak - e) / peak * 100)
    return dd if peak is not None else None


def _sessions(conn, kind: str, fid: str) -> int:
    q = {"paper": "SELECT COUNT(*) FROM paper_equity WHERE run_id=?",
         "pair": "SELECT COUNT(*) FROM pair_fund_equity WHERE name=?",
         "value": "SELECT COUNT(*) FROM value_fund_equity WHERE name=?",
         "crypto": "SELECT COUNT(*) FROM crypto_fund_equity WHERE name=?"}[kind]
    return int(conn.execute(q, (fid,)).fetchone()[0])


def evidence(conn, key: str, version: int = 1) -> dict:
    ref = fund_ref(conn, key, version)
    if not ref:
        return {"has_forward_record": False}
    kind, fid = ref
    a = conn.execute("SELECT * FROM fund_accounting WHERE fund_kind=? AND fund_id=? "
                     "ORDER BY as_of DESC, accounting_version DESC LIMIT 1", (kind, fid)).fetchone()
    ev = {"has_forward_record": True, "fund_kind": kind, "fund_id": fid,
          "sessions": _sessions(conn, kind, fid), "max_drawdown_pct": _max_dd(conn, kind, fid)}
    if a:
        a = dict(a)
        ev.update(net_usd=a["net_usd"], gross_usd=a["gross_usd"], costs_usd=a["costs_usd"],
                  closed_trades=a["closed_trades"] or 0, as_of=a["as_of"],
                  capital_usd=a["capital_usd"], recon_status=a.get("recon_status"))
    else:
        ev.update(net_usd=None, gross_usd=None, costs_usd=None, closed_trades=0,
                  recon_status="NO_ACCOUNTING")
    return ev


def tier(ev: dict, lc: dict) -> str:
    if not ev.get("has_forward_record") or ev.get("net_usd") is None:
        return "INSUFFICIENT_SAMPLE"
    if ev["sessions"] < lc["min_forward_sessions"] or ev["closed_trades"] < lc["min_closed_trades"]:
        return "INSUFFICIENT_SAMPLE"
    if ev["net_usd"] <= 0 or (ev.get("max_drawdown_pct") or 0) > lc["max_drawdown_pct"]:
        return "NOT_ELIGIBLE"
    return "ESTABLISHED" if ev["sessions"] >= lc["established_sessions"] else "ELIGIBLE"


def current_pool(conn) -> list:
    """(key, version, state) for every strategy with a forward record in play."""
    rows = conn.execute("""
        SELECT s.strategy_key, s.version, s.to_state FROM league_state s
        JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state
              GROUP BY strategy_key, version) m ON m.mid = s.id""").fetchall()
    return [(k, v, st) for k, v, st in rows if st in LIVE_STATES]


def standings(conn, cfg, record: bool = False) -> dict:
    init(conn)
    out = {name: [] for name in cfg["leagues"]}
    for key, ver, st in current_pool(conn):
        lg = league_of(conn, cfg, key, ver)
        lc = cfg["leagues"].get(lg, cfg["leagues"]["tactical"])
        ev = evidence(conn, key, ver)
        name = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                             (key, ver)).fetchone() or [key])[0]
        out.setdefault(lg, []).append({
            "strategy_key": key, "version": ver, "name": name, "state": st,
            "league": lg, "family": family_of(conn, key, ver), "tier": tier(ev, lc),
            "classification": so.classification(conn, key, ver), **ev})
    for lg, rows in out.items():
        rows.sort(key=lambda r: -(r.get("net_usd") if r.get("net_usd") is not None else -1e9))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
    if record:
        as_of = max((r.get("as_of") or "" for rs in out.values() for r in rs), default="")
        for lg, rows in out.items():
            for r in rows:
                conn.execute("INSERT OR REPLACE INTO league_standings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (as_of, lg, r["strategy_key"], r["version"], r["rank"], r["tier"],
                              r.get("net_usd"), r.get("gross_usd"), r.get("costs_usd"),
                              r.get("sessions"), r.get("closed_trades"), r.get("max_drawdown_pct"),
                              r["family"], json.dumps({"state": r["state"],
                                                       "classification": r["classification"]})))
        conn.commit()
    return out


def sync(conn, cfg) -> dict:
    """Bring the Value and crypto funds into the league; apply the §19 label."""
    init(conn)
    done = {"registered": [], "labelled": 0}
    for key, name, fam, src in (("value:stockbot_value_fund", "Stockbot Value Fund", "value", "value_fund"),
                                ("crypto:crypto_paper_fund", "Crypto Grid", "crypto", "crypto_fund")):
        exists = conn.execute("SELECT 1 FROM " + {"value_fund": "value_fund",
                              "crypto_fund": "crypto_fund"}[src] + " LIMIT 1").fetchone()
        if not exists:
            continue
        league.register(conn, key, name, {"family": fam, "universe": src,
                                          "entry_rule": src, "exit_rule": src},
                        author="leagues.sync", source_kind=src, source_ref=key.split(":", 1)[1])
        if league.state(conn, key) is None:
            league.transition(conn, key, league.PAPER,
                              "existing forward record migrated into the league", actor="leagues.sync")
            done["registered"].append(key)
    # §19: every Rising 200 variant is PROMISING / INSUFFICIENT EVIDENCE, one family.
    sweep = "stop_width experiment (2026-09-24): rising_200 loses net in all 30 stop x hold cells, 2006-2019"
    for key, ver, name in conn.execute("SELECT strategy_key, version, name FROM league_strategies "
                                       "WHERE name LIKE 'Rising 200%'").fetchall():
        if so.classification(conn, key, ver) != "PROMISING / INSUFFICIENT EVIDENCE":
            so.decide(conn, key, ver, "RESEARCH_MORE",
                      "Phase 13 §19: retained, not proven; stop widths are variants of one family",
                      classification="PROMISING / INSUFFICIENT EVIDENCE",
                      evidence={"backtest": sweep})
            done["labelled"] += 1
    return done


def render(st: dict) -> str:
    L = ["", "  LEAGUE STANDINGS  (net = liquidation-basis accounting; benchmarks informational)"]
    for lg, rows in st.items():
        if not rows:
            continue
        L += ["", f"  {lg.upper()}", "  " + "-" * 86,
              f"  {'#':>2} {'strategy':<28}{'tier':<20}{'net':>8}{'gross':>8}{'costs':>7}"
              f"{'sess':>6}{'trades':>7}{'maxDD%':>8}"]
        for r in rows:
            f = lambda v, fmt: (fmt % v) if v is not None else "—"  # noqa: E731
            L.append(f"  {r['rank']:>2} {r['name'][:27]:<28}{r['tier']:<20}"
                     f"{f(r.get('net_usd'), '%+.2f'):>8}{f(r.get('gross_usd'), '%+.2f'):>8}"
                     f"{f(r.get('costs_usd') and -r['costs_usd'], '%+.2f'):>7}"
                     f"{r.get('sessions') or 0:>6}{r.get('closed_trades') or 0:>7}"
                     f"{f(r.get('max_drawdown_pct'), '%.1f'):>8}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--standings", action="store_true")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    conn.row_factory = sqlite3.Row
    if a.sync:
        print(f"  {sync(conn, cfg)}")
    if a.standings or not a.sync:
        print(render(standings(conn, cfg, record=a.record)))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
