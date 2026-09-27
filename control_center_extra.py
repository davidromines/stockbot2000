"""Read-only data views for the Control Center panels (TASK-043).

Three views: strategy health (N5), published survivorship-free evidence
(Stage L) and the Knowledge Factory (Stage O9).  Every view is defensive:
a missing table yields an empty-but-valid structure rather than an
exception, because the panels must render on a partially migrated
database.
"""

import runtime  # noqa: F401  (thread limits must be set before anything else)

import sqlite3

# Ordering for flagged strategies.  Anything not listed sorts last, then by
# name, so an unknown state can never silently outrank a known failure.
_STATE_ORDER = {"FAILED": 0, "DEGRADING": 1, "WATCH": 2}

# Candidate threshold on the published t-statistics.  A t of 3 is the
# conventional bar for a survivorship-free replication; below it the
# evidence is not strong enough to surface as a candidate.
_T_CUTOFF = 3.0
_MAX_CANDIDATES = 20


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _rows(conn, sql, params=()):
    """Run a query, returning [] when the table it needs is absent."""
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def _get(row, key, default=None):
    """sqlite3.Row has no .get; tolerate both Row and plain mappings."""
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):   # TypeError: no row at all
        return default


def health_view(conn):
    """Current strategy health: counts by state plus every non-HEALTHY row.

    strategy_health is append-only, so the current row for a
    (strategy_key, version) pair is the one with the greatest id.  An older
    FAILED row superseded by a HEALTHY row must not be flagged.
    """
    if not _table_exists(conn, "strategy_health"):
        return {"counts": {}, "flagged": []}

    current = _rows(
        conn,
        """
        SELECT h.strategy_key, h.version, h.state, h.reason, h.at
        FROM strategy_health h
        JOIN (
            SELECT strategy_key, version, MAX(id) AS id
            FROM strategy_health
            GROUP BY strategy_key, version
        ) latest
          ON latest.strategy_key = h.strategy_key
         AND latest.version = h.version
         AND latest.id = h.id
        """,
    )

    names = {}
    if _table_exists(conn, "league_strategies"):
        for r in _rows(conn, "SELECT strategy_key, version, name FROM league_strategies"):
            names[(_get(r, "strategy_key"), _get(r, "version"))] = _get(r, "name")

    counts = {}
    flagged = []
    for r in current:
        state = _get(r, "state")
        counts[state] = counts.get(state, 0) + 1
        if state == "HEALTHY":
            continue
        key = _get(r, "strategy_key")
        version = _get(r, "version")
        flagged.append(
            {
                "strategy_key": key,
                "version": version,
                "name": names.get((key, version)) or key,
                "state": state,
                "reason": _get(r, "reason"),
                "since": _get(r, "at"),
            }
        )

    flagged.sort(key=lambda d: (_STATE_ORDER.get(d["state"], 99), d["name"] or ""))
    return {"counts": counts, "flagged": flagged}


def _jkp_years(conn):
    """signal -> year, from the published_signals catalogue (source 'jkp')."""
    years = {}
    if not _table_exists(conn, "published_signals"):
        return years
    for r in _rows(
        conn,
        "SELECT signal, year FROM published_signals WHERE source = 'jkp'",
    ):
        years[_get(r, "signal")] = _get(r, "year")
    return years


def _evidence_row(r, years):
    family = _get(r, "family")
    signal = _get(r, "signal")
    return {
        "family": family,
        "signal": signal,
        "year": years.get(signal),
        "post_ew_excess": _get(r, "mean_excess"),
        "post_ew_t": _get(r, "tstat_excess"),
        "post_vw_excess": _get(r, "mean_ls"),
        "post_vw_t": _get(r, "tstat_excess"),
        "pre_ew_excess": _get(r, "mean_long"),
    }


def published_view(conn):
    """
    Published survivorship-free evidence (Stage L), one row per family: long-leg excess
    over the market after publication, equal- and value-weighted, beside the in-sample
    ('pre') figure. published_evidence holds one row per (family, signal, weighting,
    period); this pivots them. Families named "jkp:<signal>" are the full JKP catalogue
    (candidates when post-publication t > 3); the rest are our own families.
    """
    if not _table_exists(conn, "published_evidence"):
        return {"families": [], "candidates": []}
    years = _jkp_years(conn)
    meta = {}
    if _table_exists(conn, "published_signals"):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(published_signals)")}
        cl = "cluster" if "cluster" in cols else "NULL"
        for r in _rows(conn, f"SELECT signal, description, {cl} AS cluster FROM published_signals "
                             "WHERE source='jkp'"):
            meta[_get(r, "signal")] = (_get(r, "description"), _get(r, "cluster"))
    piv = {}
    for r in _rows(conn, "SELECT family, signal, weighting, period, mean_excess, tstat_excess "
                         "FROM published_evidence"):
        fam = _get(r, "family") or ""
        d = piv.setdefault(fam, {"family": fam, "signal": _get(r, "signal"),
                                 "year": years.get(_get(r, "signal")),
                                 "post_ew_excess": None, "post_ew_t": None, "post_vw_excess": None,
                                 "post_vw_t": None, "pre_ew_excess": None})
        w, per = _get(r, "weighting"), _get(r, "period")
        if per == "post" and w == "ew":
            d["post_ew_excess"], d["post_ew_t"] = _get(r, "mean_excess"), _get(r, "tstat_excess")
        elif per == "post" and w == "vw_cap":
            d["post_vw_excess"], d["post_vw_t"] = _get(r, "mean_excess"), _get(r, "tstat_excess")
        elif per == "pre" and w == "ew":
            d["pre_ew_excess"] = _get(r, "mean_excess")

    def best_t(d):
        return max(d["post_ew_t"] or 0.0, d["post_vw_t"] or 0.0)

    families = sorted((d for f, d in piv.items() if not f.startswith("jkp:")),
                      key=lambda d: (d["post_ew_t"] is None, -(d["post_ew_t"] or 0.0)))
    candidates = []
    for f, d in piv.items():
        if f.startswith("jkp:") and best_t(d) > _T_CUTOFF:
            name, cluster = meta.get(d["signal"], (None, None))
            candidates.append({**d, "name": name, "cluster": cluster})
    candidates.sort(key=best_t, reverse=True)
    return {"families": families, "candidates": candidates[:_MAX_CANDIDATES]}

def knowledge_view(conn):
    """Knowledge Factory translation state, links and library status."""
    entries = 0
    by_state = {}
    if _table_exists(conn, "knowledge_entries"):
        for r in _rows(conn, "SELECT translation_state FROM knowledge_entries"):
            entries += 1
            state = _get(r, "translation_state") or "UNTRANSLATED"
            by_state[state] = by_state.get(state, 0) + 1

    linked = 0
    if _table_exists(conn, "knowledge_links"):
        row = conn.execute(
            "SELECT COUNT(DISTINCT entry_id) AS n FROM knowledge_links"
        ).fetchone()
        linked = _get(row, "n", 0) or 0

    library = {}
    published_entries = 0
    if _table_exists(conn, "strategy_library"):
        for r in _rows(
            conn,
            "SELECT validation_status, COUNT(*) AS n FROM strategy_library "
            "GROUP BY validation_status",
        ):
            library[_get(r, "validation_status")] = _get(r, "n", 0)
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM strategy_library "
            "WHERE entry_id LIKE 'published:%'"
        ).fetchone()
        published_entries = _get(row, "n", 0) or 0

    # Stage O rev 2 and Stage T: the daily reports' own JSON (written by
    # knowledge_factory.py and funnel.py), read, never recomputed here.
    import json
    from pathlib import Path

    def _read(path):
        try:
            return json.loads(Path(path).read_text())
        except Exception:                                    # noqa: BLE001 — a view never raises
            return {}

    kf = _read("data/knowledge_factory.json")
    fn = _read("data/funnel.json")
    near = sum(1 for f in fn.get("failures") or [] if f.get("near_miss"))
    reasons = {}
    for f in fn.get("failures") or []:
        for r in f.get("reasons") or []:
            reasons[r] = reasons.get(r, 0) + 1
    return {
        "entries": entries,
        "by_state": by_state,
        "linked": linked,
        "library": library,
        "published_entries": published_entries,
        "factory": {k: kf.get(k) for k in ("translated", "translated_yes", "requiring_interpretation",
                                           "not_translatable", "reproductions", "variants", "lineages")},
        "by_source_type": kf.get("by_source_type") or {},
        "funnel": {"as_of": fn.get("as_of"), "bottlenecks": (fn.get("bottlenecks") or [])[:3],
                   "near_misses": near, "reasons": reasons, "market": fn.get("market") or {}},
    }


def options_view(conn):
    """Stage R: each option strategy's real-price backtest beside its paper fund."""
    import options_lab
    stake = options_lab.DEFAULTS["stake_usd"]
    out = []
    for name, p in options_lab.STRATEGIES.items():
        if name.startswith("t_"):
            continue
        bt = _rows(conn, "SELECT trades, mean_ret, win_rate, start, end FROM option_backtests WHERE strategy=?", (name,))
        fund = _rows(conn, "SELECT capital_usd, started_on FROM option_funds WHERE name=?", (name,))
        eq = _rows(conn, "SELECT date, equity_usd, open_positions FROM option_fund_equity WHERE name=? "
                         "ORDER BY date DESC LIMIT 1", (name,))
        pt = _rows(conn, "SELECT COUNT(*), SUM(usd > 0), SUM(usd) FROM option_trades WHERE mode='PAPER' AND "
                         "strategy=? AND ret IS NOT NULL", (name,))
        b, f, e, t = (bt[0] if bt else None), (fund[0] if fund else None), (eq[0] if eq else None), pt[0] if pt else None
        out.append({"strategy": name, "name": p.get("name", name), "why": p.get("why", ""),
                    "bt_trades": _get(b, 0), "bt_mean": _get(b, 1), "bt_win": _get(b, 2),
                    "bt_usd": None if _get(b, 1) is None else stake * _get(b, 1),
                    "paper_since": _get(f, 1), "equity": _get(e, 1), "capital": _get(f, 0),
                    "open": _get(e, 2), "closed": _get(t, 0) or 0, "won": _get(t, 1) or 0, "paper_usd": _get(t, 2)})
    recent = [{"strategy": r[0], "symbol": r[1], "opened": r[2], "closed": r[3], "usd": r[4], "reason": r[5]}
              for r in _rows(conn, "SELECT strategy, symbol, opened, closed, usd, reason FROM option_trades "
                                   "WHERE mode='PAPER' ORDER BY COALESCE(closed, opened) DESC LIMIT 10")]
    return {"strategies": out, "recent": recent, "stake": stake}


def intraday_view(conn):
    """Stage Q2: same-day SHADOW strategies — would-be trades and money on $20 each."""
    if not _table_exists(conn, "intraday_trades"):
        return {"strategies": [], "open": 0}
    rows = _rows(conn, "SELECT strategy_key, COUNT(*), SUM(usd > 0), SUM(usd), AVG(ret_pct), COUNT(DISTINCT session) "
                       "FROM intraday_trades GROUP BY strategy_key ORDER BY SUM(usd) DESC")
    defs = {r[0]: r[1] for r in _rows(conn, "SELECT strategy_key, name FROM intraday_defs")} \
        if _table_exists(conn, "intraday_defs") else {}
    have = {r[0] for r in rows}
    strategies = [{"strategy": r[0], "trades": r[1], "won": r[2], "usd": r[3], "avg_pct": r[4], "sessions": r[5]}
                  for r in rows] + [{"strategy": k, "trades": 0} for k in sorted(defs) if k not in have]
    n_open = _rows(conn, "SELECT COUNT(*) FROM intraday_open")
    return {"strategies": strategies, "open": n_open[0][0] if n_open else 0}


def short_term_view(conn):
    """Stage Q1: the 1-5 session strategies (st_* families) — state and paper record."""
    if not _table_exists(conn, "factory_paper_link"):
        return {"families": []}
    rows = _rows(conn, """
        SELECT s.family, COUNT(DISTINCT s.strategy_key || s.version),
               SUM(a.closed_trades), SUM(a.net_usd)
        FROM league_strategies s
        LEFT JOIN factory_paper_link l ON l.strategy_key = s.strategy_key AND l.version = s.version
        LEFT JOIN (SELECT fund_id, closed_trades, net_usd, MAX(as_of) FROM fund_accounting
                   WHERE fund_kind='paper' GROUP BY fund_id) a ON a.fund_id = l.run_id
        WHERE s.family LIKE 'st\\_%' ESCAPE '\\' GROUP BY s.family ORDER BY s.family""")
    return {"families": [{"family": r[0], "strategies": r[1], "closed": r[2] or 0, "net_usd": r[3]} for r in rows]}


def movement_view(conn):
    """Leaderboard movement since the previous daily ranking snapshot (journal.py)."""
    try:
        import journal
        return journal.movement(conn, top=20)
    except Exception:                                        # noqa: BLE001 — a view never raises
        return {"date": None, "previous": None, "top": [], "new": [], "gone": []}


def analog_view(conn, top=10):
    """P5: what happened to stocks that looked like this one — the analog forecaster's newest
    read (share of the closest past setups that rose over 20 sessions, their mean move, their
    10th-percentile outcome) for each open LIVE slot position and the day's top-scored names.
    Read from data/analog/scores.parquet; never recomputed here."""
    try:
        import pandas as pd
        from pathlib import Path
        path = Path("data/analog/scores.parquet")
        if not path.exists():
            return {"as_of": None, "held": [], "top": []}
        held = []
        if _table_exists(conn, "slot_trades"):
            opens = {}
            for r in _rows(conn, "SELECT slot_id, symbol, action FROM slot_trades WHERE mode='LIVE' ORDER BY id"):
                if _get(r, "action") == "OPEN":
                    opens[_get(r, "slot_id")] = _get(r, "symbol")
                else:
                    opens.pop(_get(r, "slot_id"), None)
            held = sorted(set(opens.values()))
        s = pd.read_parquet(path)
        day = s["date"].max()
        s = s[s["date"] >= (pd.Timestamp(day) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")]
        last = s.sort_values("date").groupby("ticker").tail(1).set_index("ticker")

        def row(t):
            r = last.loc[t]
            return {"ticker": t, "date": r["date"], "p_up": float(r["analog_p_up"]), "mean": float(r["analog_mean"]),
                    "q10": float(r["analog_q10"]), "n": int(r["analog_n"])}
        today = last[last["date"] == day].sort_values("analog_p_up", ascending=False)
        return {"as_of": day, "held": [row(t) for t in held if t in last.index],
                "top": [row(t) for t in today.index[:top]]}
    except Exception:                                        # noqa: BLE001 — a view never raises
        return {"as_of": None, "held": [], "top": []}


def all_views(conn):
    return {
        "movement": movement_view(conn),
        "health": health_view(conn),
        "published": published_view(conn),
        "knowledge": knowledge_view(conn),
        "options": options_view(conn),
        "intraday": intraday_view(conn),
        "short_term": short_term_view(conn),
        "analog": analog_view(conn),
    }
