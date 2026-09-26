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
    except (IndexError, KeyError):
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
    """Published survivorship-free evidence, split into families/candidates."""
    if not _table_exists(conn, "published_evidence"):
        return {"families": [], "candidates": []}

    years = _jkp_years(conn)
    rows = _rows(
        conn,
        """
        SELECT family, signal, mean_long, mean_mkt, mean_excess, tstat_excess,
               mean_ls, computed_at
        FROM published_evidence
        """,
    )

    families = []
    candidates = []
    for r in rows:
        family = _get(r, "family") or ""
        if family.startswith("jkp:"):
            ew_t = _get(r, "tstat_excess")
            vw_t = _get(r, "tstat_excess")
            if not ((ew_t is not None and ew_t > _T_CUTOFF)
                    or (vw_t is not None and vw_t > _T_CUTOFF)):
                continue
            entry = _evidence_row(r, years)
            entry["name"] = None
            entry["cluster"] = None
            candidates.append(entry)
        else:
            families.append(_evidence_row(r, years))

    families.sort(key=lambda d: (d["post_ew_t"] is None, -(d["post_ew_t"] or 0.0)))

    def _best_t(d):
        return max(d["post_ew_t"] or 0.0, d["post_vw_t"] or 0.0)

    candidates.sort(key=_best_t, reverse=True)
    candidates = candidates[:_MAX_CANDIDATES]

    # Enrich candidates with the catalogue description/cluster where present.
    if candidates and _table_exists(conn, "published_signals"):
        meta = {}
        for r in _rows(
            conn,
            "SELECT signal, description, cluster FROM published_signals",
        ):
            meta[_get(r, "signal")] = (_get(r, "description"), _get(r, "cluster"))
        for c in candidates:
            desc, cluster = meta.get(c["signal"], (None, None))
            c["name"] = desc
            c["cluster"] = cluster

    return {"families": families, "candidates": candidates}


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

    return {
        "entries": entries,
        "by_state": by_state,
        "linked": linked,
        "library": library,
        "published_entries": published_entries,
    }


def all_views(conn):
    return {
        "health": health_view(conn),
        "published": published_view(conn),
        "knowledge": knowledge_view(conn),
    }
