"""Measure how often a strategy's entry rule actually fires.

A slot held by a rule that cannot fire in the current regime is dead capital
(the owner's "December effect" strategy held slot 1 through September). This
module answers one question: over the trailing window the live system actually
evaluates rules on, on how many distinct dates did the entry rule fire?
"""
import runtime  # noqa: F401  (thread limits must be set before pandas)

import sqlite3
import sys

import pandas as pd


def measurable(genome) -> bool:
    """True only for a plain strategy genome with an entry rule.

    Fund-type genomes (pair/value/rotation/crypto) carry no entry node to
    measure; treating them as measurable would report a false zero activity.
    """
    if not isinstance(genome, dict):
        return False
    if "entry" not in genome:
        return False
    return not any(k in genome for k in ("pair", "value", "rotation", "crypto"))


def missing_columns(df, genome) -> list:
    """Columns the entry rule reads that the frame lacks (genome.evaluate would give NaN,
    which looks exactly like a rule that never fires)."""
    import genome as genome_mod
    cols = {n["col"] for n in genome_mod._all_nodes(genome["entry"]) if isinstance(n, dict) and "col" in n}
    return sorted(c for c in cols if c not in df.columns and not str(c).startswith("cal_"))


def _entry_mask(df, genome):
    """Boolean Series aligned to df: True where the entry rule fires.

    Evaluated once over the whole frame so look-back rules (pct_change, lag)
    see their history; row-by-row evaluation would silently break them.
    """
    import genome as genome_mod

    series = genome_mod.evaluate(genome["entry"], df)
    return genome_mod._as_bool(series)


def _recent_dates(df, sessions):
    """The last `sessions` distinct dates in df, as a set."""
    dates = pd.Series(df["date"]).dropna().astype(str)
    distinct = sorted(dates.unique())
    return set(distinct[-sessions:]) if sessions > 0 else set()


def active_sessions(df, genome, sessions=60) -> int:
    """Distinct recent dates on which the entry rule fired for >=1 row."""
    if df is None or len(df) == 0:
        return 0
    mask = _entry_mask(df, genome)
    recent = _recent_dates(df, sessions)
    fired = pd.Series(df["date"]).astype(str)[mask.fillna(False)]
    return len(set(fired[fired.isin(recent)]))


def last_signal(df, genome):
    """Latest date the entry rule fired for any row, or None if never."""
    if df is None or len(df) == 0:
        return None
    mask = _entry_mask(df, genome)
    fired = pd.Series(df["date"]).astype(str)[mask.fillna(False)]
    if fired.empty:
        return None
    return str(max(fired))


def activity(conn, cfg, key, version, df=None, sessions=60) -> dict:
    """Activity report for one strategy version.

    A rule that raises is reported as measurable with zero activity plus the
    error text: an unmeasurable rule is not the same as a quiet one, and the
    caller needs to see which it is.
    """
    import slots
    import paper_trading

    out = {
        "key": key,
        "version": version,
        "measurable": False,
        "active_sessions": None,
        "last_signal": None,
    }
    g = slots.genome_for(conn, key, version)
    if not measurable(g):
        return out
    out["measurable"] = True
    if df is None:
        df = paper_trading._recent_frame(conn, cfg)
    try:
        gone = missing_columns(df, g)
        if gone:
            raise KeyError(f"frame lacks columns {gone}")
        out["active_sessions"] = active_sessions(df, g, sessions=sessions)
        out["last_signal"] = last_signal(df, g)
    except Exception as exc:  # noqa: BLE001 - report, never crash the caller
        out["active_sessions"] = 0
        out["last_signal"] = None
        out["error"] = str(exc)
    return out


def _current_holders(conn) -> dict:
    """slot_id -> (strategy_key, version) for the latest ASSIGN row per slot.

    Ties on `at` are broken by rowid so the result is deterministic; without a
    tiebreak two rows written in the same second could flip the holder between
    runs and the report would disagree with itself.
    """
    rows = conn.execute(
        """
        SELECT slot_id, strategy_key, version
          FROM slot_assignments
         WHERE action = 'ASSIGN'
         ORDER BY slot_id, at, id
        """
    ).fetchall()
    holders = {}
    for r in rows:
        holders[int(r["slot_id"])] = (r["strategy_key"], r["version"])
    return holders


def _family_for(conn, key, version):
    """Family name from strategy_objects, or None when the row is absent."""
    try:
        row = conn.execute(
            "SELECT family FROM strategy_objects WHERE strategy_key = ? AND version = ?",
            (key, version),
        ).fetchone()
    except sqlite3.Error:
        return None
    return row["family"] if row is not None else None


def all_slots(conn, cfg) -> list:
    """Activity report for each of the five live slots.

    Always returns five entries, one per slot_id 1-5, so the caller can print a
    fixed-shape report; an empty slot is represented by None fields rather than
    being omitted.
    """
    holders = _current_holders(conn)
    out = []
    for slot_id in range(1, 6):
        entry = {
            "slot_id": slot_id,
            "strategy_key": None,
            "version": None,
            "family": None,
        }
        holder = holders.get(slot_id)
        if holder is not None:
            key, version = holder
            entry["strategy_key"] = key
            entry["version"] = version
            entry["family"] = _family_for(conn, key, version)
            entry.update(activity(conn, cfg, key, version))
        out.append(entry)
    return out


def _format_slot(entry) -> str:
    """One report line per slot, matching the documented output format."""
    slot = entry["slot_id"]
    if entry["strategy_key"] is None:
        return f"slot {slot}  (empty)"
    head = (
        f"slot {slot}  {entry['strategy_key']}  v{entry['version']}  "
        f"family={entry['family']}"
    )
    if not entry.get("measurable"):
        return f"{head}  not measurable"
    if entry.get("error"):
        return f"{head}  not measurable: {entry['error']}"
    sessions = entry.get("sessions", 60)
    return (
        f"{head}  active={entry['active_sessions']}/{sessions}  "
        f"last={entry['last_signal']}"
    )


def main(argv=None):
    import argparse

    from universe import load_config

    parser = argparse.ArgumentParser(description="Strategy signal activity")
    parser.add_argument("--key")
    parser.add_argument("--version", type=int)
    parser.add_argument("--sessions", type=int, default=60)
    parser.add_argument(
        "--all-slots",
        action="store_true",
        help="report activity for every currently assigned slot",
    )
    args = parser.parse_args(argv)

    if not args.all_slots and (args.key is None or args.version is None):
        parser.error("--key and --version are required unless --all-slots is set")

    cfg = load_config()
    path = cfg["database"]["market_data_path"]
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if args.all_slots:
            for entry in all_slots(conn, cfg):
                print(_format_slot(entry))
        else:
            print(activity(conn, cfg, args.key, args.version, sessions=args.sessions))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
