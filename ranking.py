"""
One ranking for every strategy: backtest first, paper evidence takes over.

The owner's promotion process (2026-09-24):

    1. backtest a strategy to see whether it has base profitability
    2. give it a ranking
    3. paper-trade it so every strategy's forward record accrues
    4. move it up or down the list continuously
    and: the five slots are always filled with the five best, never left
    empty waiting for weeks of paper data.

THE SCORE
---------
Expected net return per trade, as a fraction of the money in the trade:

    score = (k * backtest + n * forward) / (k + n)

  backtest   mean NET return per trade on the search window (the Lab's
             `evaluations`, the factory's backtest metrics). The starting point.
  forward    the fund's restated NET P&L (accounting.py, liquidation basis, so
             open positions count) per dollar per trade taken.
  n          forward trades taken (closed + open).
  k          `ranking.prior_trades`: how many forward trades it takes for the
             paper record to weigh as much as the backtest.

On day one a strategy ranks on its backtest. Every paper trade moves weight to
the forward record, so a strategy that trades worse than its backtest sinks as
the evidence arrives, and one that trades better rises. That is shrinkage, not
a gate: nothing waits for a sample floor.

THE GATE (step 1)
-----------------
A strategy whose backtest LOSES money net is out: `backtest <= 0`. A strategy
with NO backtest (pair funds, the value fund, the classifier) is not failed for
a test it never had; it starts at `ranking.no_backtest_prior` (0 — neutral) and
its paper record decides.

Units are the same on both sides — net return per trade — which is the lesson
of degradation.py: a Lab P&L summed over 20,000 trades is not comparable with a
fund's return on $100.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import sqlite3
import sys

log = logging.getLogger("ranking")

DEFAULTS = {"prior_trades": 10, "no_backtest_prior": 0.0}
OUT_STATES = ("REJECTED", "RETIRED")


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("ranking") or {})}


def score(backtest: float | None, forward: float | None, n: int, s: dict) -> float:
    prior = float(s["no_backtest_prior"]) if backtest is None else float(backtest)
    k = float(s["prior_trades"])
    if forward is None or n <= 0:
        return prior
    return (k * prior + n * float(forward)) / (k + n)


def gate(backtest: float | None) -> tuple:
    """(passes, reason). Only a measured loss fails; an absent backtest does not."""
    if backtest is None:
        return True, "no backtest: ranked on paper evidence from a neutral start"
    if backtest <= 0:
        return False, f"backtest loses money net ({backtest:+.3%} per trade)"
    return True, f"backtest {backtest:+.3%} per trade"


# --- evidence ------------------------------------------------------------------

def backtest_per_trade(conn, cfg: dict, key: str, version: int) -> float | None:
    """Mean net return per trade on the search window, or None when no backtest exists."""
    size = float((cfg.get("risk") or {}).get("position_size_usd") or 20.0)
    if key.startswith("fx_"):
        import strategy_objects as so
        m = so.latest_metrics(conn, key, version, "backtest")
        if m and m.get("trades") and m.get("net_usd") is not None:
            return float(m["net_usd"]) / int(m["trades"]) / size
        return None
    if key.startswith("paper:"):
        import degradation
        sid, _ = degradation._link(conn, key.split(":", 1)[1])
        if sid and cfg.get("lab"):
            bt, _ = degradation._backtest_return(conn, sid, size, cfg["lab"])
            return bt
    return None


def forward_per_trade(ev: dict) -> tuple:
    """(net return per dollar per trade, trades taken) from the league's accounting evidence."""
    net, cap = ev.get("net_usd"), ev.get("capital_usd")
    if net is None or not cap:
        return None, 0
    kind = ev.get("fund_kind")
    closed = int(ev.get("closed_trades") or 0)
    if kind == "pair":
        # One position holding the whole fund; every switch is a trade, plus
        # the current holding.
        n, per_trade_capital = closed + 1, float(cap)
    else:
        n = closed + int(ev.get("open_positions") or 0)
        per_trade_capital = float(ev.get("position_usd") or 20.0)
    if n <= 0:
        return None, 0
    return float(net) / (per_trade_capital * n), n


def pool(conn) -> list:
    """(key, version, state) for every strategy not REJECTED or RETIRED — DEMOTED included."""
    rows = conn.execute("""
        SELECT s.strategy_key, s.version, s.to_state FROM league_state s
        JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state
              GROUP BY strategy_key, version) m ON m.mid = s.id""").fetchall()
    return [(k, v, st) for k, v, st in rows if st not in OUT_STATES]


def rank(conn, cfg: dict) -> list:
    """Every strategy with its backtest, forward, score and gate verdict, best first."""
    import leagues
    s = settings(cfg)
    out = []
    for key, ver, state in pool(conn):
        ev = leagues.evidence(conn, key, ver)
        if ev.get("fund_kind") == "paper":
            r = conn.execute("SELECT COUNT(*) FROM paper_positions WHERE run_id=?", (ev["fund_id"],)).fetchone()
            ev["open_positions"] = int(r[0]) if r else 0
        bt = backtest_per_trade(conn, cfg, key, ver)
        fw, n = forward_per_trade(ev)
        ok, why = gate(bt)
        name = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                             (key, ver)).fetchone() or [key])[0]
        out.append({"strategy_key": key, "version": ver, "name": name, "state": state,
                    "family": leagues.family_of(conn, key, ver), "league": leagues.league_of(conn, cfg, key, ver),
                    "backtest": bt, "forward": fw, "forward_trades": n,
                    "score": score(bt, fw, n, s), "passes_gate": ok, "gate": why,
                    **{k: ev.get(k) for k in ("net_usd", "gross_usd", "costs_usd", "sessions", "closed_trades",
                                              "max_drawdown_pct", "as_of", "recon_status", "fund_kind")}})
    out.sort(key=lambda r: (not r["passes_gate"], -r["score"]))
    return out


def render(rows: list, limit: int = 40) -> str:
    def p(v):
        return "     —" if v is None else f"{v:+.2%}"
    L = ["", "  RANKING — expected net return per trade; backtest first, paper evidence takes over",
         f"  {'#':>3} {'strategy':<30} {'score':>7} {'backtest':>9} {'paper':>7} {'trades':>6} "
         f"{'net $':>7}  gate"]
    for i, r in enumerate(rows[:limit], 1):
        L.append(f"  {i:>3} {str(r['name'])[:30]:<30} {p(r['score']):>7} {p(r['backtest']):>9} "
                 f"{p(r['forward']):>7} {r['forward_trades']:>6} "
                 f"{(r['net_usd'] if r['net_usd'] is not None else 0):>+7.2f}  "
                 f"{'ok' if r['passes_gate'] else 'OUT: ' + r['gate']}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The single strategy ranking.")
    ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    print(render(rank(conn, cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
