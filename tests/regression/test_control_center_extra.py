"""Regression tests for control_center_extra (TASK-043)."""

import runtime  # noqa: F401

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import control_center_extra as cce

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name + ("  " + detail if detail else ""))
        FAILURES.append(name)


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _health_db():
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE strategy_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT, strategy_key TEXT, version INTEGER,
            state TEXT, reason TEXT, metrics TEXT);
        CREATE TABLE league_strategies (
            strategy_key TEXT, version INTEGER, name TEXT);
        """
    )
    conn.execute(
        "INSERT INTO league_strategies VALUES ('alpha', 1, 'Alpha')")
    conn.execute(
        "INSERT INTO league_strategies VALUES ('beta', 1, 'Beta')")
    conn.execute(
        "INSERT INTO league_strategies VALUES ('gamma', 1, 'Gamma')")
    # alpha: older FAILED superseded by HEALTHY -> must not be flagged.
    conn.execute(
        "INSERT INTO strategy_health (at, strategy_key, version, state, reason) "
        "VALUES ('2026-01-01', 'alpha', 1, 'FAILED', 'old')")
    conn.execute(
        "INSERT INTO strategy_health (at, strategy_key, version, state, reason) "
        "VALUES ('2026-02-01', 'alpha', 1, 'HEALTHY', 'ok')")
    # beta: WATCH, gamma: FAILED.
    conn.execute(
        "INSERT INTO strategy_health (at, strategy_key, version, state, reason) "
        "VALUES ('2026-02-02', 'beta', 1, 'WATCH', 'thin')")
    conn.execute(
        "INSERT INTO strategy_health (at, strategy_key, version, state, reason) "
        "VALUES ('2026-02-03', 'gamma', 1, 'FAILED', 'broke')")
    conn.commit()
    return conn


def test_health():
    conn = _health_db()
    view = cce.health_view(conn)
    flagged = view["flagged"]
    keys = [f["strategy_key"] for f in flagged]
    check("health: superseded FAILED not flagged", "alpha" not in keys, str(keys))
    check("health: FAILED before WATCH",
          keys.index("gamma") < keys.index("beta"), str(keys))
    check("health: counts cover all current states",
          view["counts"].get("HEALTHY") == 1
          and view["counts"].get("WATCH") == 1
          and view["counts"].get("FAILED") == 1, str(view["counts"]))
    check("health: name resolved from league_strategies",
          flagged[0]["name"] == "Gamma", str(flagged[0]))
    check("health: since is the current row's at",
          flagged[0]["since"] == "2026-02-03", str(flagged[0]))


def _published_db():
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE published_evidence (
            family TEXT, signal TEXT, weighting TEXT, period TEXT, months INTEGER,
            mean_long REAL, mean_mkt REAL, mean_excess REAL, tstat_excess REAL,
            mean_ls REAL, computed_at TEXT);
        CREATE TABLE published_signals (
            source TEXT, signal TEXT, acronym TEXT, authors TEXT, year INTEGER,
            sample_start TEXT, sample_end TEXT, op_return REAL, op_tstat REAL,
            description TEXT, direction TEXT, cluster TEXT, significance TEXT);
        """
    )
    conn.execute(
        "INSERT INTO published_signals (source, signal, year, description, cluster) "
        "VALUES ('jkp', 'mom', 1993, 'Momentum', 'price')")
    conn.execute(
        "INSERT INTO published_evidence VALUES "
        "('value_book', 'bm', 'ew', 'post', 336, 0.5, 0.1, 0.4, 4.2, 0.3, 'now')")
    conn.execute(
        "INSERT INTO published_evidence VALUES "
        "('jkp:mom', 'mom', 'ew', 'post', 336, 0.6, 0.1, 0.5, 3.5, 0.4, 'now')")
    conn.execute(
        "INSERT INTO published_evidence VALUES "
        "('jkp:weak', 'weak', 'ew', 'post', 336, 0.1, 0.1, 0.0, 1.2, 0.0, 'now')")
    conn.commit()
    return conn


def test_published():
    conn = _published_db()
    view = cce.published_view(conn)
    vb = [f for f in view["families"] if f["family"] == "value_book"]
    check("published: post-publication t used, not the all-period row",
          len(vb) == 1 and abs(vb[0]["post_ew_t"] - 4.2) < 1e-9, vb)
    fams = view["families"]
    cands = view["candidates"]
    check("published: jkp rows excluded from families",
          all(not f["family"].startswith("jkp:") for f in fams) and len(fams) == 1,
          str(fams))
    check("published: families sorted by post_ew_t desc",
          [f["post_ew_t"] for f in fams] == sorted(
              [f["post_ew_t"] for f in fams], reverse=True), str(fams))
    check("published: candidates only t > 3",
          all((c["post_ew_t"] or 0) > 3 or (c["post_vw_t"] or 0) > 3 for c in cands)
          and len(cands) == 1, str(cands))
    check("published: candidate carries name and cluster",
          cands[0]["name"] == "Momentum" and cands[0]["cluster"] == "price",
          str(cands[0]))
    check("published: year from published_signals",
          cands[0]["year"] == 1993, str(cands[0]))


def _knowledge_db():
    conn = _conn()
    conn.executescript(
        """
        CREATE TABLE knowledge_entries (
            entry_id TEXT, strategy_name TEXT, source TEXT,
            translation_state TEXT, factory_family TEXT);
        CREATE TABLE knowledge_links (
            entry_id TEXT, strategy_key TEXT, version INTEGER,
            variant TEXT, linked_at TEXT);
        CREATE TABLE strategy_library (
            entry_id TEXT, name TEXT, family TEXT,
            validation_status TEXT, status_reason TEXT, implementation TEXT);
        """
    )
    conn.execute("INSERT INTO knowledge_entries VALUES ('e1','s','x','DATA_UNAVAILABLE','f')")
    conn.execute("INSERT INTO knowledge_entries VALUES ('e2','s','x','DATA_UNAVAILABLE','f')")
    conn.execute("INSERT INTO knowledge_entries VALUES ('e3','s','x',NULL,'f')")
    conn.execute("INSERT INTO knowledge_links VALUES ('e1','k',1,'v','now')")
    conn.execute("INSERT INTO knowledge_links VALUES ('e1','k',2,'v','now')")
    conn.execute("INSERT INTO strategy_library VALUES ('published:1','n','f','SUPPORTED','r','i')")
    conn.execute("INSERT INTO strategy_library VALUES ('published:2','n','f','REJECTED','r','i')")
    conn.execute("INSERT INTO strategy_library VALUES ('local:3','n','f','SUPPORTED','r','i')")
    conn.commit()
    return conn


def test_knowledge():
    conn = _knowledge_db()
    view = cce.knowledge_view(conn)
    check("knowledge: entry count", view["entries"] == 3, str(view))
    check("knowledge: NULL state becomes UNTRANSLATED",
          view["by_state"].get("UNTRANSLATED") == 1
          and view["by_state"].get("DATA_UNAVAILABLE") == 2, str(view["by_state"]))
    check("knowledge: distinct linked entries", view["linked"] == 1, str(view))
    check("knowledge: library status counts",
          view["library"].get("SUPPORTED") == 2
          and view["library"].get("REJECTED") == 1, str(view["library"]))
    check("knowledge: published entries counted",
          view["published_entries"] == 2, str(view))


def test_empty():
    conn = _conn()
    h = cce.health_view(conn)
    p = cce.published_view(conn)
    k = cce.knowledge_view(conn)
    check("empty: health valid", h == {"counts": {}, "flagged": []}, str(h))
    check("empty: published valid",
          p == {"families": [], "candidates": []}, str(p))
    check("empty: knowledge valid",
          k == {"entries": 0, "by_state": {}, "linked": 0,
                "library": {}, "published_entries": 0}, str(k))
    a = cce.all_views(conn)
    check("empty: all_views composes",
          set(a) == {"movement", "health", "published", "knowledge", "options", "intraday", "short_term"}, str(a))
    check("empty: options lists every strategy with no numbers yet",
          a["options"]["strategies"] and all(o["bt_mean"] is None and o["closed"] == 0 for o in a["options"]["strategies"]))
    check("empty: same-day and short-term books are empty, not errors",
          a["intraday"] == {"strategies": [], "open": 0} and a["short_term"] == {"families": []}, str(a["intraday"]))


def main():
    test_health()
    test_published()
    test_knowledge()
    test_empty()
    if FAILURES:
        print("FAILED: " + ", ".join(FAILURES))
        sys.exit(1)
    print("ALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
