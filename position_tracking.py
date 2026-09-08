"""
SQLite-backed position tracker. This is the source of truth for what's
currently held, what's been closed, and why — feeds both the "don't exceed
10 holdings" rule and the backtest/performance review.

Run directly to initialize the DB:  python position_tracking.py
"""
import sqlite3
from datetime import datetime, timezone

from universe import load_config

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open', 'closed')),
    entry_date TEXT NOT NULL,
    entry_price REAL NOT NULL,
    dollar_amount REAL NOT NULL,
    shares REAL NOT NULL,
    score_at_entry REAL NOT NULL,
    reason_at_entry TEXT,
    stop_loss_price REAL,
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,          -- 'stop_loss' | 'manual' | 'score_decay' | 'take_profit'
    pnl_usd REAL,
    pnl_pct REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
"""


def get_conn(db_path: str = None) -> sqlite3.Connection:
    if db_path is None:
        cfg = load_config()
        db_path = cfg["database"]["path"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = None):
    conn = get_conn(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def open_position(ticker: str, entry_price: float, dollar_amount: float,
                   score_at_entry: float, reason_at_entry: str, stop_loss_price: float,
                   db_path: str = None) -> int:
    shares = round(dollar_amount / entry_price, 6)
    conn = get_conn(db_path)
    cur = conn.execute(
        """INSERT INTO positions
           (ticker, status, entry_date, entry_price, dollar_amount, shares,
            score_at_entry, reason_at_entry, stop_loss_price, created_at)
           VALUES (?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, datetime.now(timezone.utc).isoformat(), entry_price, dollar_amount,
         shares, score_at_entry, reason_at_entry, stop_loss_price,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    position_id = cur.lastrowid
    conn.close()
    return position_id


def close_position(position_id: int, exit_price: float, exit_reason: str, db_path: str = None):
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"No position with id {position_id}")

    pnl_usd = (exit_price - row["entry_price"]) * row["shares"]
    pnl_pct = (exit_price / row["entry_price"] - 1) * 100

    conn.execute(
        """UPDATE positions SET status='closed', exit_date=?, exit_price=?,
           exit_reason=?, pnl_usd=?, pnl_pct=? WHERE id=?""",
        (datetime.now(timezone.utc).isoformat(), exit_price, exit_reason, pnl_usd, pnl_pct, position_id),
    )
    conn.commit()
    conn.close()


def get_open_positions(db_path: str = None) -> list[sqlite3.Row]:
    conn = get_conn(db_path)
    rows = conn.execute("SELECT * FROM positions WHERE status='open'").fetchall()
    conn.close()
    return rows


def get_open_count(db_path: str = None) -> int:
    return len(get_open_positions(db_path))


def get_closed_positions(db_path: str = None) -> list[sqlite3.Row]:
    conn = get_conn(db_path)
    rows = conn.execute("SELECT * FROM positions WHERE status='closed' ORDER BY exit_date DESC").fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    print("Position tracking DB initialized at config's database.path")
