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

SURVIVORSHIP (owner, 2026-09-24: "use the synthetic data")
----------------------------------------------------------
Where survivorship_backtest.py has run a strategy WITH the synthetic dead
companies in the universe, that result (`as_is`) is its backtest — for the
score and for the gate — and the every-death-a-total-loss run (`zero`) is shown
beside it as the worst case. The old backtest is used only for a strategy that
has not been run that way yet, and the row says which source it used. The
drawdown exposure check the old promotion ladder applied is part of the gate:
a strategy taking `survivorship.max_drawdown_exposure` or more of its entries
in names already 30% below their 200-day high is out.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys

log = logging.getLogger("ranking")

DEFAULTS = {"prior_trades": 10, "no_backtest_prior": 0.0,
            # Stage L4: shrink a backtest by its family's POST-publication evidence (JKP, dead
            # companies included): t >= 3 keeps it whole, t <= 0 zeroes it, linear between. A
            # family published evidence says is gone after publication (liquidity, size) then
            # cannot lead on its backtest alone. Off until the owner turns it on.
            "published_prior": False,
            # The unseen-window test (holdout.py, 2023 -> today, one look per version): a loss
            # there fails the gate, and that result replaces the 2016-19 backtest as the prior.
            "use_holdout": True,
            # Compare strategies per day held, not per trade (hold_period.py): every per-trade
            # figure is scaled to this many sessions. A year-long ETF trade and a week-long
            # stock trade are different units; per trade, long holds looked many times better.
            # None disables.
            "normalize_hold_days": 20, "min_hold_for_scaling": 5}


def published_factor(conn, family: str | None) -> tuple:
    """(shrink factor 0..1, post-publication t) for a strategy family, or (1.0, None) when
    the family has no published evidence. Equal-weighted long-leg excess, post period."""
    if not family:
        return 1.0, None
    try:
        r = conn.execute("SELECT MAX(tstat_excess) FROM published_evidence WHERE family=? AND period='post' "
                         "AND weighting='ew'", (family,)).fetchone()
    except sqlite3.Error:
        return 1.0, None
    if not r or r[0] is None:
        return 1.0, None
    t = float(r[0])
    return min(1.0, max(0.0, t / 3.0)), t
OUT_STATES = ("REJECTED", "RETIRED")


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("ranking") or {})}


def score(backtest: float | None, forward: float | None, n: int, s: dict) -> float:
    prior = float(s["no_backtest_prior"]) if backtest is None else float(backtest)
    k = float(s["prior_trades"])
    if forward is None or n <= 0:
        return prior
    return (k * prior + n * float(forward)) / (k + n)


def gate(backtest: float | None, share_deep: float | None = None, limit: float | None = None) -> tuple:
    """(passes, reason). A measured loss fails, and so does concentrating entries in
    deeply drawn-down names; an absent backtest does not."""
    if share_deep is not None and limit is not None and share_deep >= limit:
        return False, (f"{share_deep:.0%} of entries in names >30% below their 200-day high "
                       f"(limit {limit:.0%}): the bias this data cannot measure")
    if backtest is None:
        return True, "no backtest: ranked on paper evidence from a neutral start"
    if backtest <= 0:
        return False, f"backtest loses money net ({backtest:+.3%} per trade)"
    return True, f"backtest {backtest:+.3%} per trade"


def survivorship(conn, key: str, version: int) -> dict:
    """The dead-companies-included backtest, the worst case and the exposure, where computed."""
    try:
        import survivorship_backtest as sb
        s = sb.result(conn, key, version, sb.SCORE_MODE, stale_ok=True)
        w = sb.result(conn, key, version, sb.WORST_MODE, stale_ok=True)
    except Exception as e:                                       # noqa: BLE001
        log.warning(f"survivorship backtest unavailable for {key}: {type(e).__name__}: {e}")
        return {}
    if not s or not s.get("trades"):
        return {}
    if s.get("stale"):
        log.warning(f"{key} v{version}: dead-company backtest is from an earlier synthetic build — "
                    "used until survivorship_backtest.py recomputes it")
    return {"backtest": s["per_trade"], "worst_case": (w or {}).get("per_trade"),
            "share_deep": s.get("share_deep"), "synthetic_trades": s.get("synthetic_trades"),
            "stale": bool(s.get("stale"))}


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
    if key.startswith("crypto:"):
        # Stage K4: a crypto trend fund's backtest is its crypto_backtests row
        # (net of the measured Robinhood spread). The grid fund has none and
        # ranks from the neutral start, as before.
        r = conn.execute("SELECT strategy FROM crypto_fund WHERE name=?", (key.split(":", 1)[1],)).fetchone() \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='crypto_fund'").fetchone() else None
        try:
            st = json.loads(r[0]) if r else {}
        except (TypeError, ValueError):
            st = {}
        if st.get("engine") == "crypto_trend" and st.get("strategy_id"):
            import crypto_backtest
            row = crypto_backtest.result(conn, st["strategy_id"])
            if row and row.get("trades") and row.get("net_per_trade") is not None:
                return float(row["net_per_trade"])
        return None
    if key.startswith("option:"):
        # Stage R: an option strategy's backtest is its mean return per trade on the
        # premium, from real historical option prices (options_lab.py).
        r = conn.execute("SELECT mean_ret, trades FROM option_backtests WHERE strategy=?",
                         (key.split(":", 1)[1],)).fetchone() \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='option_backtests'").fetchone() else None
        return float(r[0]) if r and r[1] and r[0] is not None else None
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


def live_per_trade(conn, key: str, ver: int) -> tuple:
    """(mean return per dollar per closed LIVE slot trade, count) for one strategy version,
    from the append-only slot_trades log (OPEN then CLOSE per slot)."""
    try:
        rows = conn.execute("SELECT slot_id, action, quantity, price, strategy_key, version FROM slot_trades "
                            "WHERE mode='LIVE' ORDER BY id").fetchall()
    except sqlite3.Error:
        return None, 0
    opens, rets = {}, []
    for slot, action, q, px, k, v in rows:
        if action == "OPEN":
            opens[slot] = (k, v, float(px))
        else:
            o = opens.pop(slot, None)
            if o and o[0] == key and int(o[1]) == int(ver) and o[2] > 0 and px:
                rets.append(float(px) / o[2] - 1)
    return (sum(rets) / len(rets), len(rets)) if rets else (None, 0)


def _per_hold(per_trade: float | None, hold: float | None, s: dict):
    """A per-trade figure scaled to `normalize_hold_days` sessions of holding."""
    n = s.get("normalize_hold_days")
    if per_trade is None or not n or not hold:
        return per_trade
    # A very short measured hold would multiply a small, noisy per-trade figure many times
    # (a 2-session hold x10); holds shorter than the floor are scaled as the floor.
    return per_trade * float(n) / max(float(hold), float(s.get("min_hold_for_scaling", 5)))


def _market_checks(conn, key: str, ver: int) -> dict:
    """{'unseen_vs_random': 'PASS'|'FAIL'|'NA', 'bear_vs_random': ...} — informational only."""
    try:
        import market_checks
        return {c: d["verdict"] for c, d in market_checks.checks(conn, key, ver).items()}
    except Exception:                                        # noqa: BLE001 — a check never blocks ranking
        return {}


def pool(conn) -> list:
    """(key, version, state) for every strategy not REJECTED or RETIRED — DEMOTED included."""
    rows = conn.execute("""
        SELECT s.strategy_key, s.version, s.to_state FROM league_state s
        JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state
              GROUP BY strategy_key, version) m ON m.mid = s.id""").fetchall()
    # paper:<run_id> for a fund that belongs to a factory strategy is the same
    # strategy registered twice (migrate_league before 2026-09-26); rank it once.
    try:
        linked = {f"paper:{r[0]}" for r in conn.execute("SELECT run_id FROM factory_paper_link")}
    except sqlite3.Error:
        linked = set()
    return [(k, v, st) for k, v, st in rows if st not in OUT_STATES and k not in linked]


SEARCH_PREFIXES = ("lab_", "survivor_")


def from_search(conn, key: str) -> bool:
    """True for a strategy the evolutionary search found (its paper fund is named
    lab_* / survivor_* by paper_trading.promote_survivors). Owner, 2026-09-26:
    search strategies earn their score on paper only — a search backtest is the
    best of up to a million tries on the same history, too lucky to guide money."""
    if not key.startswith("paper:"):
        return False
    try:
        r = conn.execute("SELECT name FROM paper_runs WHERE run_id=?", (key.split(":", 1)[1],)).fetchone()
    except sqlite3.Error:
        return False
    return bool(r and r[0] and str(r[0]).startswith(SEARCH_PREFIXES))


def so_genome(conn, key: str, ver: int):
    """The genome behind a ranked strategy when it is a factory object (fx_ key), else None."""
    if not str(key).startswith("fx_"):
        return None
    import strategy_objects as so
    return so.genome(conn, key, ver)


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
        elif ev.get("fund_kind") == "value":
            r = conn.execute("SELECT COUNT(*) FROM value_fund_positions WHERE name=?", (ev["fund_id"],)).fetchone()
            ev["open_positions"] = int(r[0]) if r else 0
            # Its positions are its capital split across its holdings, not $20.
            if ev.get("capital_usd") and ev["open_positions"]:
                ev["position_usd"] = float(ev["capital_usd"]) / ev["open_positions"]
        elif ev.get("fund_kind") == "option":
            import options_lab
            r = conn.execute("SELECT COUNT(*) FROM option_trades WHERE mode='PAPER' AND strategy=? AND "
                             "closed IS NULL", (ev["fund_id"],)).fetchone()
            ev["open_positions"] = int(r[0]) if r else 0
            ev["position_usd"] = options_lab.settings(cfg)["stake_usd"]
        elif ev.get("fund_kind") == "crypto":
            # A crypto fund splits its capital evenly across its pairs.
            r = conn.execute("SELECT symbols FROM crypto_fund WHERE name=?", (ev["fund_id"],)).fetchone()
            try:
                n_sym = len(json.loads(r[0])) if r else 0
            except (TypeError, ValueError):
                n_sym = 0
            if ev.get("capital_usd") and n_sym:
                ev["position_usd"] = float(ev["capital_usd"]) / n_sym
        searched = from_search(conn, key)
        import hold_period
        try:
            import slots as _slots
            g_hold = _slots.genome_for(conn, key, ver)
        except Exception:                                    # noqa: BLE001
            g_hold = None
        hold, hold_src = hold_period.estimate(conn, key, ver, g_hold)
        pf, pt = published_factor(conn, leagues.family_of(conn, key, ver)) if s["published_prior"] else (1.0, None)
        sv = survivorship(conn, key, ver)
        bt = sv["backtest"] if sv else backtest_per_trade(conn, cfg, key, ver)
        fw, n = forward_per_trade(ev)
        # Addendum D criterion 12: the strategy's own closed LIVE slot trades are forward
        # evidence too, pooled per trade with its paper record (fills are real, spread included).
        lv, m = live_per_trade(conn, key, ver)
        if m:
            fw = ((fw or 0.0) * n + lv * m) / (n + m)
            n += m
        limit = float((cfg.get("survivorship") or {}).get("max_drawdown_exposure", 0.35))
        ok, why = gate(bt, sv.get("share_deep"), limit)
        ho, prior_bt = None, bt
        if s["use_holdout"] and not searched:
            import holdout
            ho = holdout.result(conn, key, ver)
            if ho and ho.get("trades"):
                if ok and (ho["per_trade"] or 0) <= 0:
                    ok, why = False, f"loses on unseen 2023-today data ({ho['per_trade']:+.3%} per trade)"
                prior_bt = ho["per_trade"]
        name = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                             (key, ver)).fetchone() or [key])[0]
        out.append({"strategy_key": key, "version": ver, "name": name, "state": state,
                    "family": leagues.family_of(conn, key, ver), "league": leagues.league_of(conn, cfg, key, ver),
                    "backtest": bt, "forward": fw, "forward_trades": n,
                    "backtest_source": ((("with dead companies" + (" (earlier build)" if sv.get("stale") else ""))
                                          if sv.get("synthetic_trades") else
                                         "survivors only (dead companies not measurable)") if sv
                                        else ("survivors only" if bt is not None else None)),
                    "worst_case": sv.get("worst_case"), "share_deep": sv.get("share_deep"),
                    "synthetic_trades": sv.get("synthetic_trades"),
                    "from_search": searched,
                    "score": _per_hold(score(None if searched else (prior_bt * pf if prior_bt is not None else None),
                                             fw, n, s), hold, s),
                    "hold_days": hold, "hold_source": hold_src,
                    "published_t": pt, "holdout": (ho or {}).get("per_trade"),
                    "holdout_trades": (ho or {}).get("trades"),
                    # Bull-market checks (market_checks.py): recorded and shown, never a gate.
                    "checks": _market_checks(conn, key, ver), "passes_gate": ok, "gate": why,
                    **{k: ev.get(k) for k in ("net_usd", "gross_usd", "costs_usd", "sessions", "closed_trades",
                                              "max_drawdown_pct", "as_of", "recon_status", "fund_kind")}})
    out.sort(key=lambda r: (not r["passes_gate"], -r["score"]))
    return out


def render(rows: list, limit: int = 40) -> str:
    def p(v):
        return "     —" if v is None else f"{v:+.2%}"
    L = ["", "  RANKING — expected net return per trade; backtest first, paper evidence takes over",
         "  search strategies (found by the evolutionary search) score on paper only: no backtest head start",
         "  backtest = with synthetic dead companies (*) where computed, else survivors only; worst = every death a total loss",
         f"  {'#':>3} {'strategy':<30} {'score':>7} {'backtest':>10} {'worst':>7} {'paper':>7} {'trades':>6} "
         f"{'net $':>7}  gate"]
    for i, r in enumerate(rows[:limit], 1):
        star = "*" if r.get("backtest_source") == "with dead companies" else " "
        L.append(f"  {i:>3} {str(r['name'])[:30]:<30} {p(r['score']):>7} {p(r['backtest']):>9}{star} "
                 f"{p(r.get('worst_case')):>7} {p(r['forward']):>7} {r['forward_trades']:>6} "
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
