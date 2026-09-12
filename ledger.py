"""
The idea ledger. Phase 09.

Every strategy the search ever tries is recorded here with its parentage, its
genome and its results. Three reasons this is not optional:

**Lineage.** A winning strategy is far more trustworthy when you can see the
mutations that produced it. An ancestor line of steadily improving fitness is
evidence; a single outlier with random parents is a lottery ticket.

**Trial count.** Testing 200,000 strategies inflates the winner's apparent skill
purely through multiple testing. The deflated Sharpe correction needs to know
exactly how many candidates were tried, and that number is only trustworthy if it
was recorded as the search ran rather than estimated afterwards.

**Revival.** A branch abandoned at generation 40 may be worth revisiting when the
reward function changes. Genomes are stored as JSON, so any strategy can be
re-run exactly as it was.

Full trade-by-trade records are kept only for shortlisted strategies. Storing
every fill for 200k nightly candidates would add gigabytes for no benefit — the
genome fully determines behaviour, so any strategy can be re-simulated on demand.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import uuid

import storage


def init(conn) -> None:
    """Create the lab's tables. Safe to call repeatedly."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id          TEXT PRIMARY KEY,
            parent_id   TEXT,
            run_id      TEXT NOT NULL,
            generation  INTEGER NOT NULL,
            origin      TEXT NOT NULL,        -- seed | random | mutation | crossover
            genome      TEXT NOT NULL,        -- JSON, re-runnable exactly
            complexity  INTEGER NOT NULL,
            entry_desc  TEXT,
            exit_desc   TEXT,
            status      TEXT NOT NULL DEFAULT 'evaluated',
            created_at  TEXT NOT NULL
        ) STRICT
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            strategy_id   TEXT NOT NULL,
            window_start  TEXT, window_end TEXT,
            trial_index   INTEGER NOT NULL,   -- for the deflated Sharpe correction
            fitness       REAL NOT NULL,
            net_pnl_usd   REAL NOT NULL,      -- the number that matters
            excess_pnl_usd REAL,               -- net, less what the null earned
            benchmark_pnl_usd REAL,            -- what the null earned on these trades
            gross_pnl_usd REAL,
            costs_usd     REAL,
            sharpe        REAL,
            max_drawdown  REAL,
            n_trades      INTEGER,
            win_rate      REAL,
            verdict       TEXT,
            PRIMARY KEY (strategy_id, window_start)
        ) STRICT, WITHOUT ROWID
    """)
    # Added after the fact: excess over the null was computed on every evaluation
    # but never stored, so the shortlist could only rank by net P&L and spent its
    # slots on strategies that had merely drifted upward with the market.
    have = {r[1] for r in conn.execute("PRAGMA table_info(evaluations)")}
    for col in ("excess_pnl_usd", "benchmark_pnl_usd"):
        if col not in have:
            conn.execute(f"ALTER TABLE evaluations ADD COLUMN {col} REAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS promotions (
            strategy_id TEXT NOT NULL,
            stage       TEXT NOT NULL,
            decision    TEXT NOT NULL,        -- pass | fail
            evidence    TEXT,
            decided_at  TEXT NOT NULL,
            PRIMARY KEY (strategy_id, stage)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lab_runs (
            run_id      TEXT PRIMARY KEY,
            started_at  TEXT NOT NULL,
            finished_at TEXT,
            generations INTEGER,
            population  INTEGER,
            evaluated   INTEGER NOT NULL DEFAULT 0,
            window_start TEXT, window_end TEXT,
            config      TEXT,
            notes       TEXT
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_strat_run ON strategies(run_id, generation)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_pnl ON evaluations(net_pnl_usd DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eval_fitness ON evaluations(fitness DESC)")
    conn.commit()


def new_run(conn, window: tuple[str, str], generations: int, population: int,
            config: dict | None = None, notes: str = "") -> str:
    run_id = uuid.uuid4().hex[:12]
    conn.execute("""
        INSERT INTO lab_runs (run_id, started_at, generations, population,
                              window_start, window_end, config, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, storage._now(), generations, population, window[0], window[1],
          json.dumps(config or {}), notes))
    conn.commit()
    return run_id


def finish_run(conn, run_id: str, evaluated: int) -> None:
    conn.execute("UPDATE lab_runs SET finished_at = ?, evaluated = ? WHERE run_id = ?",
                 (storage._now(), evaluated, run_id))
    conn.commit()


def record(conn, run_id: str, generation: int, origin: str, genome_dict: dict,
           describe, complexity: int, parent_id: str | None,
           result: dict, window: tuple[str, str], trial_index: int) -> str:
    """
    Store one evaluated candidate.

    `trial_index` is the running count of evaluations in this run. It exists
    solely so a deflated Sharpe can be computed later: the winner of 200,000
    trials needs a far larger correction than the winner of 200, and guessing
    that number after the fact defeats the purpose.
    """
    sid = uuid.uuid4().hex[:12]
    conn.execute("""
        INSERT INTO strategies (id, parent_id, run_id, generation, origin, genome,
                                complexity, entry_desc, exit_desc, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'evaluated', ?)
    """, (sid, parent_id, run_id, generation, origin, json.dumps(genome_dict),
          complexity, describe(genome_dict["entry"])[:500],
          describe(genome_dict["exit"])[:500], storage._now()))
    conn.execute("""
        INSERT OR REPLACE INTO evaluations
            (strategy_id, window_start, window_end, trial_index, fitness, net_pnl_usd,
             excess_pnl_usd, benchmark_pnl_usd,
             gross_pnl_usd, costs_usd, sharpe, max_drawdown, n_trades, win_rate, verdict)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (sid, window[0], window[1], trial_index,
          float(result.get("fitness", 0.0)), float(result.get("net_pnl_usd", 0.0)),
          result.get("excess_pnl_usd"), result.get("benchmark_pnl_usd"),
          result.get("gross_pnl_usd"), result.get("costs_usd"),
          result.get("sharpe"), result.get("max_drawdown"),
          result.get("n_trades"), result.get("win_rate"), result.get("verdict")))
    return sid


def top_by_pnl(conn, run_id: str | None = None, limit: int = 20) -> list[dict]:
    """Best strategies by money. The default ranking, deliberately."""
    sql = """
        SELECT s.id, s.generation, s.origin, s.complexity, s.entry_desc, s.exit_desc,
               e.net_pnl_usd, e.excess_pnl_usd, e.benchmark_pnl_usd, e.fitness,
               e.sharpe, e.max_drawdown, e.n_trades, e.trial_index
        FROM evaluations e JOIN strategies s ON s.id = e.strategy_id
    """
    params: list = []
    if run_id:
        sql += " WHERE s.run_id = ?"; params.append(run_id)
    sql += " ORDER BY e.net_pnl_usd DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def lineage(conn, strategy_id: str) -> list[dict]:
    """Walk a strategy back to its random ancestor."""
    out, sid = [], strategy_id
    while sid:
        r = conn.execute("""
            SELECT s.id, s.parent_id, s.generation, s.origin, s.entry_desc,
                   e.fitness, e.net_pnl_usd
            FROM strategies s LEFT JOIN evaluations e ON e.strategy_id = s.id
            WHERE s.id = ?
        """, (sid,)).fetchone()
        if not r:
            break
        out.append(dict(r))
        sid = r["parent_id"]
    return list(reversed(out))


def run_stats(conn, run_id: str) -> dict:
    r = conn.execute("""
        SELECT COUNT(*) AS evaluated,
               SUM(CASE WHEN e.net_pnl_usd > 0 THEN 1 ELSE 0 END) AS profitable,
               MAX(e.net_pnl_usd) AS best_pnl,
               MAX(e.fitness) AS best_fitness
        FROM evaluations e JOIN strategies s ON s.id = e.strategy_id
        WHERE s.run_id = ?
    """, (run_id,)).fetchone()
    return dict(r) if r else {}
