"""
The Phase 13 strategy object. Spec §13 (fields), §14 (lifecycle), §15
(profitable vs proven), §37 (machine-readable decisions); Addendum B §B17.

ONE IDENTITY, NOT TWO
---------------------
`league.py` already owns who a strategy is (`strategy_key`) and what it was
(`version`, minted from a hash of the material fields). This module adds the
§13 fields around that identity instead of forking a second registry:

    strategy_meta       one row per (strategy_key, version); written once
    strategy_metrics    append-only snapshots: backtest / paper / live
    strategy_decisions  every §37 decision, with its evidence

Nothing here updates a row. A strategy whose rules change is a new version
(league.register), and a metric that changes is a new snapshot.

CLASSIFICATION IS NOT STATE (§15)
---------------------------------
`state` is where a strategy sits in the lifecycle (league log). `classification`
is what the evidence says about it: PROFITABLE means positive measured P&L and
nothing more; PROMISING means enough evidence to keep testing; QUALIFIED means
every gate passed; LIVE means authorized for money. Positive P&L alone never
moves a strategy toward live.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import hashlib
import json
from datetime import datetime, timezone

import league

# §37
DECISIONS = ("CONTINUE", "PROMOTE", "DEMOTE", "RETIRE", "REJECT", "RESEARCH_MORE",
             "DATA_PROBLEM", "ACCOUNTING_PROBLEM", "INSUFFICIENT_SAMPLE")
# §11
SURVIVORSHIP = ("SURVIVORSHIP_SAFE", "SURVIVORSHIP_ADJUSTED",
                "SURVIVORSHIP_LIMITED", "UNKNOWN")
# §15 — plus the label §19 prescribes for the Rising 200 family
CLASSIFICATIONS = ("UNTESTED", "UNPROFITABLE", "PROFITABLE", "PROMISING",
                   "PROMISING / INSUFFICIENT EVIDENCE", "QUALIFIED", "LIVE")

META_FIELDS = ("family", "league", "source", "source_ref", "hypothesis",
               "economic_rationale", "universe", "data_requirements", "features",
               "parameters", "entry_rules", "exit_rules", "position_sizing",
               "risk_rules", "holding_period", "backtest_period",
               "validation_period", "intraday", "parent_key")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _j(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


def init(conn) -> None:
    league.init(conn)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS strategy_meta (
            strategy_key TEXT NOT NULL,
            version      INTEGER NOT NULL,
            {', '.join(f'{f} TEXT' for f in META_FIELDS)},
            created_at   TEXT NOT NULL,
            PRIMARY KEY (strategy_key, version)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_metrics (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_key  TEXT NOT NULL,
            version       INTEGER NOT NULL,
            as_of         TEXT NOT NULL,
            phase         TEXT NOT NULL,        -- backtest | validation | robustness | paper | live
            window        TEXT,
            gross_usd     REAL, costs_usd REAL, net_usd REAL,
            return_pct    REAL, max_drawdown_pct REAL,
            sharpe        REAL, sortino REAL,
            win_rate      REAL, profit_factor REAL,
            trades        INTEGER, sessions INTEGER, turnover REAL,
            benchmark_return_pct REAL, excess_vs_null_usd REAL,
            correlation   REAL, capacity_usd REAL,
            survivorship_status TEXT, data_quality_status TEXT,
            detail        TEXT,
            recorded_at   TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sm_key ON strategy_metrics(strategy_key, version, phase)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_decisions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT NOT NULL,
            strategy_key  TEXT NOT NULL,
            version       INTEGER NOT NULL,
            decision      TEXT NOT NULL,
            from_state    TEXT,
            to_state      TEXT,
            classification TEXT,
            reason        TEXT NOT NULL,
            evidence      TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sd_key ON strategy_decisions(strategy_key)")
    conn.commit()


def key_for(family: str, params: dict, prefix: str = "fx") -> str:
    """Deterministic identity: the same family and parameters are the same strategy."""
    h = hashlib.sha256(_j({"family": family, "params": params}).encode()).hexdigest()[:10]
    return f"{prefix}_{family}_{h}"


def register(conn, obj: dict, author: str = "strategy_factory") -> dict:
    """
    Register a strategy object; idempotent. Returns {strategy_key, version, new}.

    `obj` carries: strategy_key, name, family, league, genome (entry/exit/risk),
    and any META_FIELDS. The material fields handed to league.register are the
    genome and parameters, so a changed rule mints a new version.
    """
    init(conn)
    g = obj.get("genome") or {}
    spec = {"family": obj["family"], "universe": obj.get("universe"),
            "entry_rule": g.get("entry"), "exit_rule": g.get("exit"),
            "position_sizing": obj.get("position_sizing"),
            "holding_period": (g.get("risk") or {}).get("max_hold_days", obj.get("holding_period")),
            "parameters": {"params": obj.get("parameters"), "risk": g.get("risk")},
            "required_data": obj.get("data_requirements")}
    before = league.versions(conn, obj["strategy_key"])
    row = league.register(conn, obj["strategy_key"], obj["name"], spec, author=author,
                          source_kind=obj.get("source"), source_ref=obj.get("source_ref"),
                          parent_key=obj.get("parent_key"),
                          hypothesis=obj.get("hypothesis", ""))
    ver = row["version"]
    new = len(league.versions(conn, obj["strategy_key"])) > len(before)
    if new:
        meta = {f: obj.get(f) for f in META_FIELDS}
        meta["entry_rules"] = g.get("entry")
        meta["exit_rules"] = g.get("exit")
        meta["risk_rules"] = g.get("risk")
        conn.execute(
            f"INSERT OR IGNORE INTO strategy_meta (strategy_key, version, "
            f"{', '.join(META_FIELDS)}, created_at) VALUES "
            f"({', '.join('?' * (len(META_FIELDS) + 3))})",
            (obj["strategy_key"], ver, *[_j(meta[f]) if not isinstance(meta[f], str)
                                          else meta[f] for f in META_FIELDS], _now()))
        if league.state(conn, obj["strategy_key"], ver) is None:
            league.transition(conn, obj["strategy_key"], league.DISCOVERED,
                              f"generated by {author}", version=ver, actor=author)
        conn.commit()
    return {"strategy_key": obj["strategy_key"], "version": ver, "new": new}


def meta(conn, strategy_key: str, version: int | None = None) -> dict | None:
    init(conn)
    q = ("SELECT * FROM strategy_meta WHERE strategy_key=? "
         + ("AND version=? " if version else "") + "ORDER BY version DESC LIMIT 1")
    r = conn.execute(q, (strategy_key, version) if version else (strategy_key,)).fetchone()
    if not r:
        return None
    d = dict(zip([c[0] for c in conn.execute("SELECT * FROM strategy_meta LIMIT 0").description], r))
    for f in META_FIELDS:
        try:
            d[f] = json.loads(d[f]) if d[f] and d[f][:1] in "[{\"0123456789-tfn" else d[f]
        except (TypeError, ValueError):
            pass
    return d


def genome(conn, strategy_key: str, version: int | None = None) -> dict | None:
    m = meta(conn, strategy_key, version)
    if not m:
        return None
    return {"entry": m["entry_rules"], "exit": m["exit_rules"], "risk": m["risk_rules"]}


def record_metrics(conn, strategy_key: str, version: int, phase: str, **m) -> None:
    init(conn)
    cols = ["strategy_key", "version", "as_of", "phase", "recorded_at"]
    vals = [strategy_key, version, m.pop("as_of", _now()[:10]), phase, _now()]
    if "detail" in m and not isinstance(m["detail"], str):
        m["detail"] = _j(m["detail"])
    for k, v in m.items():
        cols.append(k)
        vals.append(v)
    conn.execute(f"INSERT INTO strategy_metrics ({','.join(cols)}) VALUES "
                 f"({','.join('?' * len(vals))})", vals)
    conn.commit()


def latest_metrics(conn, strategy_key: str, version: int, phase: str) -> dict | None:
    init(conn)
    cur = conn.execute("SELECT * FROM strategy_metrics WHERE strategy_key=? AND version=? "
                       "AND phase=? ORDER BY id DESC LIMIT 1", (strategy_key, version, phase))
    r = cur.fetchone()
    return dict(zip([c[0] for c in cur.description], r)) if r else None


def decide(conn, strategy_key: str, version: int, decision: str, reason: str,
           to_state: str | None = None, classification: str | None = None,
           evidence: dict | None = None, actor: str = "factory_pipeline") -> dict:
    """
    Record a §37 decision and, if it names a new state, make the transition.

    The decision is written even when the transition is refused, so the log
    shows what the system tried and why the state machine said no.
    """
    init(conn)
    if decision not in DECISIONS:
        raise ValueError(f"{decision!r} is not a §37 decision; have {DECISIONS}")
    if classification and classification not in CLASSIFICATIONS:
        raise ValueError(f"{classification!r} is not a §15 classification")
    frm = league.state(conn, strategy_key, version)
    moved, err = None, None
    if to_state and to_state != frm:
        try:
            league.transition(conn, strategy_key, to_state, f"{decision}: {reason}",
                              version=version, actor=actor)
            moved = to_state
        except league.LeagueError as e:
            err = str(e)
    conn.execute("INSERT INTO strategy_decisions (at, strategy_key, version, decision, "
                 "from_state, to_state, classification, reason, evidence) VALUES (?,?,?,?,?,?,?,?,?)",
                 (_now(), strategy_key, version, decision, frm, moved,
                  classification, reason + (f" [transition refused: {err}]" if err else ""),
                  _j(evidence or {})))
    conn.commit()
    return {"decision": decision, "from": frm, "to": moved, "refused": err}


def classification(conn, strategy_key: str, version: int | None = None) -> str:
    init(conn)
    q = ("SELECT classification FROM strategy_decisions WHERE strategy_key=? "
         + ("AND version=? " if version else "")
         + "AND classification IS NOT NULL ORDER BY id DESC LIMIT 1")
    r = conn.execute(q, (strategy_key, version) if version else (strategy_key,)).fetchone()
    return r[0] if r else "UNTESTED"


def in_state(conn, state: str) -> list:
    """(strategy_key, version) pairs whose current state is `state` (canonical names)."""
    league.init(conn)
    rows = conn.execute("""
        SELECT s.strategy_key, s.version, s.to_state FROM league_state s
        JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state
              GROUP BY strategy_key, version) m ON m.mid = s.id""").fetchall()
    return [(k, v) for k, v, st in rows if league.canonical(st) == state]
