"""
Forward paper trading. Records what a strategy would have done, day by day.

This is the only measurement in the project with **no survivorship bias at all**.
A backtest can only buy companies that still exist; paper trading buys what is
listed today and finds out what happens, exactly as live trading would. Whatever
the ~10-point annual haircut on backtests turns out to understate or overstate,
none of it applies here.

It is also the slowest possible way to learn anything — weeks per meaningful
result — which is precisely why it sits at the end of the promotion ladder rather
than the start. Backtests are for discarding ideas cheaply. This is for trusting
the survivors.

How it works: a run holds a strategy and a cash balance. Each trading day,
`--step` reads the current signals, closes anything that hit its stop, take-profit
or holding limit, and opens positions in the best remaining candidates up to the
position cap. Everything is priced from the database, so a step is reproducible
and can be replayed.

Costs are charged through the same `costs.py` the backtest and the Lab use. A
paper result that flattered itself by ignoring spread would defeat the purpose.

Usage:
    python paper_trading.py --start "momentum_v1"     # open a run
    python paper_trading.py --step                    # advance every open run one day
    python paper_trading.py --status                  # positions and P&L
    python paper_trading.py --close "momentum_v1"     # close out and record the result
    python paper_trading.py --promote                 # paper trade the Lab's validation survivors
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import uuid

import pandas as pd

import costs as costs_mod
import genome as gn
import storage
from stop_loss import calculate_stop_loss
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paper")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_runs (
            run_id       TEXT PRIMARY KEY,
            name         TEXT NOT NULL UNIQUE,
            strategy     TEXT NOT NULL,      -- JSON: genome, or 'model' for the classifier
            capital_usd  REAL NOT NULL,
            cash_usd     REAL NOT NULL,
            started_on   TEXT NOT NULL,
            last_step_on TEXT,
            status       TEXT NOT NULL DEFAULT 'open',
            created_at   TEXT NOT NULL
        ) STRICT
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_positions (
            run_id      TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            entry_date  TEXT NOT NULL,
            entry_price REAL NOT NULL,
            shares      REAL NOT NULL,
            stop_price  REAL,
            days_held   INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, ticker)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            run_id        TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            entry_date    TEXT NOT NULL,
            exit_date     TEXT NOT NULL,
            entry_price   REAL, exit_price REAL, shares REAL,
            gross_pnl_usd REAL, costs_usd REAL, net_pnl_usd REAL, pnl_pct REAL,
            exit_reason   TEXT,
            PRIMARY KEY (run_id, ticker, entry_date)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_equity (
            run_id     TEXT NOT NULL,
            date       TEXT NOT NULL,
            cash_usd   REAL NOT NULL,
            positions_usd REAL NOT NULL,
            equity_usd REAL NOT NULL,
            open_positions INTEGER NOT NULL,
            PRIMARY KEY (run_id, date)
        ) STRICT, WITHOUT ROWID
    """)
    # Columns the production table gained by hand and code came to depend on:
    # fund_report and the factory read `label` / `family`, the review cycle
    # reads `last_review`. No code created them, so a rebuilt database broke
    # enrolment (found by the Phase 13 end-to-end test, 2026-09-24). Idempotent.
    have = {r[1] for r in conn.execute("PRAGMA table_info(paper_runs)")}
    for col in ("last_review", "label", "family"):
        if col not in have:
            conn.execute(f"ALTER TABLE paper_runs ADD COLUMN {col} TEXT")
    # Stage AD item 3 — next-open fills. A step decides on the close of D and writes an order here; the next step
    # fills it at the open of the stock's first bar after D (entries sized at that open, exits gapping through).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_pending (
            run_id     TEXT NOT NULL,
            ticker     TEXT NOT NULL,
            side       TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
            decided_on TEXT NOT NULL,
            reason     TEXT,
            atr        REAL,
            stop_mult  REAL,
            stop_pct   REAL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, ticker, side)
        ) STRICT, WITHOUT ROWID
    """)
    # entry_date / exit_date stay the DECISION dates (every consumer that shifts to the next open keeps working);
    # the fill basis and the session actually filled are recorded beside them. NULL = the old close fills.
    for table, cols in (("paper_positions", ("fill_basis", "fill_date")),
                        ("paper_trades", ("fill_basis", "fill_date", "exit_fill_date"))):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
    conn.commit()


def fill_mode(cfg: dict) -> str:
    """`paper.fills`: 'next_open' (Stage AD item 3, the simulator's convention) or 'close' (the old engine, kept so a
    config edit rolls it back)."""
    return str(((cfg.get("paper") or {}).get("fills")) or "next_open")


def research_positions(cfg: dict) -> int:
    """Positions a paper fund may hold: `paper.positions` (research mode, 2026-09-27), else the
    live cap. Paper is measurement, not the $100 account: more positions at the same $20 size
    means more trades per day of forward time — the evidence the ranking waits for — and the
    per-trade return, the quantity ranked, is unchanged."""
    return int(((cfg.get("paper") or {}).get("positions")) or cfg["risk"]["max_open_positions"])


def recapitalize(conn, cfg: dict) -> int:
    """Give research-mode capital to every open fund that has not yet taken a step (no mark,
    no position, no trade) — nothing it has recorded changes. Funds with a record keep theirs."""
    capital = cfg["risk"]["position_size_usd"] * research_positions(cfg)
    cur = conn.execute("""UPDATE paper_runs SET capital_usd=?, cash_usd=? WHERE status='open' AND capital_usd < ?
        AND NOT EXISTS (SELECT 1 FROM paper_equity e WHERE e.run_id=paper_runs.run_id)
        AND NOT EXISTS (SELECT 1 FROM paper_positions p WHERE p.run_id=paper_runs.run_id)
        AND NOT EXISTS (SELECT 1 FROM paper_trades t WHERE t.run_id=paper_runs.run_id)""",
                       (capital, capital, capital))
    conn.commit()
    return cur.rowcount


def start(conn, cfg: dict, name: str, strategy: str = "model") -> str:
    capital = cfg["risk"]["position_size_usd"] * research_positions(cfg)
    today = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    run_id = uuid.uuid4().hex[:12]
    conn.execute("""
        INSERT INTO paper_runs (run_id, name, strategy, capital_usd, cash_usd,
                                started_on, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (run_id, name, strategy, capital, capital, today, storage._now()))
    conn.commit()
    log.info(f"Opened paper run '{name}' ({run_id}) with ${capital:,.2f} from {today}")
    return run_id


def _latest_scores(conn, cfg: dict) -> pd.DataFrame:
    """
    Today's ranked candidates, priced and filtered exactly as live trading would.

    Reuses the same loader the daily scorer uses, so paper trading cannot
    accidentally see a wider universe than the real system would.
    """
    import xgboost as xgb

    latest = storage.load_latest_features(
        conn, FEATURE_COLS,
        types=cfg["universe"]["tradeable_types"],
        max_staleness_days=cfg["scoresheet"].get("max_staleness_days", 5),
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"))
    if latest.empty:
        return latest
    model = xgb.XGBClassifier()
    model.load_model(cfg["model"]["path"])
    # Score with the columns the MODEL was trained on, not with whatever
    # FEATURE_COLS happens to hold today. Adding four indicators to FEATURE_COLS
    # made this line raise a feature_names mismatch, and because it runs before
    # the per-run loop it took down every paper run with it — including the
    # conviction books, which do not use the classifier at all. A stale model
    # should degrade one run, never the whole step.
    # Explicit None checks: feature_names_in_ is a numpy array, and `a or b` on
    # one raises "truth value of an array is ambiguous" rather than falling back.
    want = getattr(model, "feature_names_in_", None)
    if want is None:
        want = model.get_booster().feature_names
    want = list(want) if want is not None else list(FEATURE_COLS)
    missing = [c for c in want if c not in latest.columns]
    if missing:
        log.warning(f"Model expects columns not present ({missing}); "
                    f"classifier scoring skipped this step.")
        latest["score"] = 0.0
        return latest
    if len(want) != len(FEATURE_COLS):
        log.warning(f"Model was trained on {len(want)} features but FEATURE_COLS "
                    f"now has {len(FEATURE_COLS)} — scoring on the model's set. "
                    f"Retrain with train_model.py to use the new indicators.")
    latest["score"] = model.predict_proba(latest[want])[:, 1] * 100
    return latest.sort_values("score", ascending=False)


LOOKBACK_DAYS = 420          # calendar days of history a genome rule may need


_FRAME: dict = {}


def _recent_frame(conn, cfg: dict):
    """
    The trailing window every genome rule is evaluated over, loaded once.

    Cached for the life of the process because a `--step` scores every open run
    against the same day, and reloading four hundred days of the universe per run
    would dominate the step entirely.
    """
    if "df" in _FRAME:
        return _FRAME["df"]
    from train_model import FEATURE_COLS as FC
    last = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    start = (pd.Timestamp(last) - pd.Timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    df = storage.load_training_frame(
        conn, FC, types=cfg["universe"]["tradeable_types"],
        start_date=start, end_date=last,
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True)
    if not df.empty:
        # Fundamental genomes (strategy factory) read daily_fundamentals
        # columns; without them they would silently never fire.
        df = storage.attach_fundamentals(conn, df)
        df = df.sort_values(["ticker", "date"])
    _FRAME["df"] = df
    return df


def _genome_signals(conn, cfg: dict, genome: dict):
    """
    Today's entry candidates and exit signals for one genome.

    Both rules are evaluated over the **same** trailing window, in one pass. A
    genome rule is not evaluable from one row per ticker: `pct_change`, `zscore`
    and `lag` look backwards, so scoring `pct_change(sma_200, 3) > 0.02` against
    a single row silently yields NaN and therefore no signals at all. That
    failure looks exactly like "the strategy did not trade today", which is
    indistinguishable from it working.

    The window carries the same tradeability floors the live scanner uses, so
    paper trading can never see a wider universe than a real order could reach.
    """
    df = _recent_frame(conn, cfg)
    if df.empty:
        return df, set()
    latest = df["date"].max()
    on_today = (df["date"] == latest).to_numpy()

    entry = gn._as_bool(gn.evaluate(genome["entry"], df)).to_numpy()
    exit_ = gn._as_bool(gn.evaluate(genome["exit"], df)).to_numpy()

    cands = df[on_today & entry].copy()
    # No score to rank on, so rank by liquidity: of the names that fired, the
    # most tradeable first. Arbitrary but stated, and stable run to run.
    if "dollar_volume_20" in cands:
        cands = cands.sort_values("dollar_volume_20", ascending=False)
    exits = set(df.loc[on_today & exit_, "ticker"].astype(str))
    return cands, exits


def _strategy_of(run: dict):
    """The genome behind a run, or None when it is the classifier."""
    raw = run.get("strategy") or "model"
    if raw == "model":
        return None
    try:
        g = json.loads(raw)
        if isinstance(g, dict) and g.get("conviction"):
            return None                  # handled separately; not a genome
        return g if isinstance(g, dict) and "entry" in g else None
    except (ValueError, TypeError):
        log.warning(f"Run '{run.get('name')}' has an unreadable strategy; "
                    f"falling back to the classifier.")
        return None


def _conviction_of(run: dict) -> str | None:
    """The conviction screen behind a run, if it is one."""
    raw = run.get("strategy") or ""
    if not raw.startswith("{"):
        return None
    try:
        g = json.loads(raw)
        return g.get("conviction") if isinstance(g, dict) else None
    except (ValueError, TypeError):
        return None


def _stale_marks(conn, tickers, prices: dict, today: str) -> dict:
    """Last real close at or before `today` for held tickers missing from today's prices."""
    out = {}
    for t in tickers:
        if t in prices:
            continue
        r = conn.execute("SELECT close FROM prices WHERE ticker=? AND date<=? "
                         "ORDER BY date DESC LIMIT 1", (t, today)).fetchone()
        if r and r[0]:
            out[t] = float(r[0])
    return out


def _rotation_of(run: dict):
    try:
        g = json.loads(run.get("strategy") or "")
    except (ValueError, TypeError):
        return None
    return g.get("rotation") if isinstance(g, dict) else None


def _kalman_of(run: dict) -> bool:
    try:
        g = json.loads(run.get("strategy") or "")
    except (ValueError, TypeError):
        return False
    return isinstance(g, dict) and g.get("family") == "kalman_pair"


def _rotation_step(conn, cfg, run, today, cost_model) -> bool:
    """
    Advance one ETF rotation fund (rotation.py): once a month — or when it holds nothing —
    move to the fund's current holdings (top K by trailing return, SHY when momentum is not
    positive); every day, mark the book. No stop and no time exit: the monthly ranking is
    the exit, as in the backtest. ETF closes are read from `prices` directly (the stock
    universe the other runs trade does not include ETFs).
    """
    import rotation
    params = _rotation_of(run)
    size = cfg["risk"]["position_size_usd"]

    def close(t):
        r = conn.execute("SELECT close FROM prices WHERE ticker=? AND date=?", (t, today)).fetchone()
        return float(r[0]) if r and r[0] else None

    open_pos = [dict(r) for r in conn.execute("SELECT * FROM paper_positions WHERE run_id=?", (run["run_id"],))]
    cash = run["cash_usd"]
    last = run.get("last_review") or ""
    if not open_pos or last[:7] != today[:7]:
        target = rotation.current(conn, params, as_of=today)["holdings"]
        for pos in list(open_pos):
            if pos["ticker"] in target:
                continue
            px = close(pos["ticker"])
            if px is None:
                continue
            e, sh, gross, notional = _exit_values(conn, pos, px)       # on the adjusted series (corporate actions)
            cost = float(cost_model.round_trip(notional, 1e9, sh))
            conn.execute("""INSERT OR REPLACE INTO paper_trades (run_id,ticker,entry_date,exit_date,entry_price,
                exit_price,shares,gross_pnl_usd,costs_usd,net_pnl_usd,pnl_pct,exit_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run["run_id"], pos["ticker"], pos["entry_date"], today, e, px, sh,
                 gross, cost, gross - cost, (px / e - 1) * 100, "rotated_out"))
            conn.execute("DELETE FROM paper_positions WHERE run_id=? AND ticker=?", (run["run_id"], pos["ticker"]))
            cash += notional + gross - cost
            open_pos.remove(pos)
        held = {p["ticker"] for p in open_pos}
        for t in target:
            px = close(t)
            if t in held or px is None or cash < size:
                continue
            shares = size / px
            conn.execute("""INSERT OR REPLACE INTO paper_positions (run_id,ticker,entry_date,entry_price,shares,
                stop_price,days_held) VALUES (?,?,?,?,?,NULL,0)""", (run["run_id"], t, today, px, shares))
            cash -= size
            open_pos.append({"ticker": t, "shares": shares, "entry_price": px})
        conn.execute("UPDATE paper_runs SET last_review=? WHERE run_id=?", (today, run["run_id"]))
    pv = sum(_mark_value(conn, p, close(p["ticker"])) for p in open_pos)
    conn.execute("""INSERT OR REPLACE INTO paper_equity (run_id,date,cash_usd,positions_usd,equity_usd,open_positions)
        VALUES (?,?,?,?,?,?)""", (run["run_id"], today, cash, pv, cash + pv, len(open_pos)))
    conn.execute("UPDATE paper_runs SET cash_usd=?, last_step_on=? WHERE run_id=?", (cash, today, run["run_id"]))
    conn.commit()
    return True


def _conviction_step(conn, cfg, run, today, prices, dv, cost_model) -> bool:
    """
    Advance one conviction run. Reviews weekly; does nothing on other days.

    A conviction book is not a swing strategy with a longer hold. It has no
    holding limit, no stop and no take-profit: the only reason to sell is that
    the reason for owning has stopped being true. Applying an ATR stop here would
    convert it back into the high-turnover regime the whole approach exists to
    escape — and that regime is where every price-based strategy in this project
    has already died to costs.

    Hysteresis is carried over from the backtest: buy inside the top decile, sell
    only when a name drops out of the top 40%. The gap is what keeps turnover
    near 3-10% a month rather than churning on noise at a single threshold.
    """
    import conviction as cv
    import pandas as pd

    name = _conviction_of(run)
    if name not in cv.SCREENS:
        return False
    # Review once a week. `last_review` is stored on the run so a missed cron
    # morning delays the review rather than skipping it silently.
    last = run.get("last_review") or ""
    if last and (pd.Timestamp(today) - pd.Timestamp(last)).days < 6:
        return True                       # handled, nothing to do today

    sc = cv.SCREENS[name]
    panel = cv._load_panel(conn, cfg, today, today)
    if panel.empty:
        # _load_panel samples Wednesdays; on other days ask for the trailing week.
        start = str((pd.Timestamp(today) - pd.Timedelta(days=8)).date())
        panel = cv._load_panel(conn, cfg, start, today)
        if panel.empty:
            log.info(f"'{run['name']}' {today}: no fundamental panel this week")
            return True
        panel = panel[panel["date"] == panel["date"].max()]

    day = panel.dropna(subset=[c for c in sc["requires"] if c in panel.columns]).copy()
    if len(day) < 40:
        log.info(f"'{run['name']}' {today}: only {len(day)} scoreable names, skipping")
        return True
    day["score"] = sc["score"](day)
    day = day.dropna(subset=["score"])
    day["pct"] = day["score"].rank(pct=True)
    ranks = dict(zip(day["ticker"].astype(str), day["pct"]))

    size = cfg["risk"]["position_size_usd"]
    cap = cfg["risk"]["max_open_positions"]
    open_pos = [dict(r) for r in conn.execute(
        "SELECT * FROM paper_positions WHERE run_id=?", (run["run_id"],))]
    cash = run["cash_usd"]
    sold = bought = 0

    for pos in open_pos[:]:
        r = ranks.get(pos["ticker"])
        px = prices.get(pos["ticker"])
        if px is None or r is None:
            continue                      # unpriceable or unscoreable: revisit next week
        if r < 0.60:                      # fell out of the wide band
            e, sh, gross, notional = _exit_values(conn, pos, px)   # on the adjusted series (corporate actions)
            cost = float(cost_model.round_trip(notional, dv.get(pos["ticker"], 0), sh))
            conn.execute("""INSERT OR REPLACE INTO paper_trades
                (run_id,ticker,entry_date,exit_date,entry_price,exit_price,shares,
                 gross_pnl_usd,costs_usd,net_pnl_usd,pnl_pct,exit_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run["run_id"], pos["ticker"], pos["entry_date"], today,
                 e, px, sh, gross, cost, gross - cost,
                 (px / e - 1) * 100, "fundamentals_deteriorated"))
            conn.execute("DELETE FROM paper_positions WHERE run_id=? AND ticker=?",
                         (run["run_id"], pos["ticker"]))
            cash += notional + gross - cost
            open_pos.remove(pos); sold += 1

    held = {p["ticker"] for p in open_pos}
    for t in day.sort_values("score", ascending=False)["ticker"].astype(str):
        if len(open_pos) >= cap or cash < size:
            break
        if t in held or ranks.get(t, 0) < 0.90:
            continue
        px = prices.get(t)
        if not px or px <= 0:
            continue
        shares = size / px
        conn.execute("""INSERT OR REPLACE INTO paper_positions
            (run_id,ticker,entry_date,entry_price,shares,stop_price,days_held)
            VALUES (?,?,?,?,?,NULL,0)""", (run["run_id"], t, today, px, shares))
        cash -= size
        open_pos.append({"ticker": t, "shares": shares, "entry_price": px})
        held.add(t); bought += 1

    pv = sum(_mark_value(conn, p, prices.get(p["ticker"])) for p in open_pos)
    equity = cash + pv
    conn.execute("""INSERT OR REPLACE INTO paper_equity
        (run_id,date,cash_usd,positions_usd,equity_usd,open_positions)
        VALUES (?,?,?,?,?,?)""", (run["run_id"], today, cash, pv, equity, len(open_pos)))
    conn.execute("UPDATE paper_runs SET cash_usd=?, last_step_on=?, last_review=? "
                 "WHERE run_id=?", (cash, today, today, run["run_id"]))
    conn.commit()
    log.info(f"'{run['name']}' {today}: REVIEW — {bought} bought, {sold} sold, "
             f"{len(open_pos)} held | equity ${equity:,.2f} | "
             f"NET P&L ${equity - run['capital_usd']:+,.2f}")
    return True


ANCHOR_RANGE = (0.02, 50.0)   # adjustment factors outside this are data defects, not corporate actions


def adjusted_entry(conn, ticker: str, entry_date: str, entry_price: float, col: str = "close") -> float:
    """Stage AD item 4: a position's entry price on TODAY's adjusted series. The engine records the close it paid; the
    prices table is back-adjusted later for splits, spin-offs and dividends, so comparing the recorded price with a
    later adjusted price books the adjustment as profit or loss (CTVA: four trades near -84%) and puts a stored stop on
    the wrong scale (a 2-for-1 split would stop the position at once). The adjusted close of the entry date is the
    entry on the same series as every later price. A factor outside ANCHOR_RANGE is treated as a data defect: the
    recorded price stands."""
    col = "open" if col == "open" else "close"                 # a next-open fill is anchored on its session's open
    r = conn.execute(f"SELECT {col} FROM prices WHERE ticker=? AND date=?", (ticker, str(entry_date)[:10])).fetchone()
    a = float(r[0]) if r and r[0] else None
    if not a or a <= 0 or not entry_price:
        return float(entry_price)
    k = a / float(entry_price)
    return a if ANCHOR_RANGE[0] <= k <= ANCHOR_RANGE[1] else float(entry_price)


def _anchored(conn, pos: dict) -> float:
    """A position's entry on today's adjusted series: the open of its fill session for a next-open fill, else the
    close of its entry date; its own recorded price when it has neither (bought this step)."""
    if pos.get("fill_basis") == "next_open" and pos.get("fill_date"):
        return adjusted_entry(conn, pos["ticker"], pos["fill_date"], pos["entry_price"], col="open")
    if pos.get("entry_date"):
        return adjusted_entry(conn, pos["ticker"], pos["entry_date"], pos["entry_price"])
    return float(pos["entry_price"])


def _exit_values(conn, pos: dict, px: float) -> tuple:
    """(entry on the adjusted series, shares on that series, gross $, dollars paid) for booking an exit at `px`."""
    e = _anchored(conn, pos)
    notional = float(pos["shares"]) * float(pos["entry_price"])
    return e, notional / e, notional * (px / e - 1), notional


def _mark_value(conn, pos: dict, px: float | None) -> float:
    """A position's value at `px` on the adjusted series (dollars paid x px / adjusted entry); at cost without a price."""
    notional = float(pos["shares"]) * float(pos["entry_price"])
    if px is None:
        return notional
    return notional * px / _anchored(conn, pos)


FILL_WAIT_SESSIONS = 3      # an order whose stock shows no bar for this many sessions is cancelled (BUY) or booked at its
                            # last real close (SELL: a position must be able to leave)


def _next_bar(conn, ticker: str, after: str, upto: str):
    """(date, open) of the stock's first bar after `after`, on or before `upto`; None when it has none yet."""
    r = conn.execute("SELECT date, open FROM prices WHERE ticker=? AND date>? AND date<=? AND open > 0 "
                     "ORDER BY date LIMIT 1", (ticker, str(after)[:10], upto)).fetchone()
    return (str(r[0])[:10], float(r[1])) if r else None


def _entry_stop(cfg, px: float, atr, mult, pct) -> float:
    """The stop a fill at `px` carries: mult x the decision bar's ATR below it (the config rule without a multiple),
    tightened by a per-trade percentage stop where the genome has one (Stage P4). Same rule as the close path."""
    if mult and atr and atr == atr and atr > 0:
        stop = px - float(mult) * float(atr)
    else:
        stop = calculate_stop_loss(px, atr, cfg)
    if pct is not None and pct == pct:
        stop = max(stop, px * (1 + min(max(float(pct), -0.5), -0.01)))
    return float(stop)


def _step_next_open(conn, cfg, run, today, prices, dv, candidates, exits_today, genome, run_cap, run_horizon,
                    horizon, size, cost_model, days_since) -> None:
    """
    One run, one day, at NEXT-OPEN fills (Stage AD item 3) — the simulator's convention since 2026-09-15.

    1. Fill yesterday's decisions at the open of each stock's first bar after the decision: SELLs first (an exit gaps
       through its stop exactly as the simulator charges it), then BUYs, sized at that open, while a slot and the cash
       are there. Cash moves at the fill, never at the decision.
    2. Decide on today's close: exits (stop, take-profit, exit rule, holding limit) and entries become orders for the
       next step. A position waiting to sell is still held and marked.
    3. Mark at today's close, as before.
    entry_date / exit_date record the DECISION dates; fill_date / exit_fill_date the sessions filled.
    """
    rid = run["run_id"]
    open_pos = [dict(r) for r in conn.execute("SELECT * FROM paper_positions WHERE run_id = ?", (rid,))]
    orders = [dict(r) for r in conn.execute("SELECT * FROM paper_pending WHERE run_id=? ORDER BY created_at, ticker",
                                            (rid,))]
    cash = run["cash_usd"]
    sold = bought = cancelled = 0
    rk = (genome or {}).get("risk", {})

    # --- 1a. SELL fills -----------------------------------------------------------------------
    by_ticker = {p["ticker"]: p for p in open_pos}
    for o in [o for o in orders if o["side"] == "SELL"]:
        pos = by_ticker.get(o["ticker"])
        if pos is None:
            conn.execute("DELETE FROM paper_pending WHERE run_id=? AND ticker=? AND side='SELL'", (rid, o["ticker"]))
            continue
        bar = _next_bar(conn, o["ticker"], o["decided_on"], today)
        reason = o["reason"]
        if bar is None:
            if 0 <= days_since(o["decided_on"]) < FILL_WAIT_SESSIONS:
                continue                                   # no open yet: still pending, still held
            last = conn.execute("SELECT date, close FROM prices WHERE ticker=? AND date<=? AND close > 0 "
                                "ORDER BY date DESC LIMIT 1", (o["ticker"], today)).fetchone()
            bar = (None, float(last[1])) if last else (None, _anchored(conn, pos))   # not an open: no exit_fill_date
            reason = f"{reason} (no open: last close)"
        fdate, px = bar
        e_adj, shares_adj, gross, notional = _exit_values(conn, pos, px)
        cost = float(cost_model.round_trip(notional, dv.get(pos["ticker"], 0), shares_adj))
        conn.execute("""
            INSERT OR REPLACE INTO paper_trades
                (run_id, ticker, entry_date, exit_date, entry_price, exit_price, shares, gross_pnl_usd, costs_usd,
                 net_pnl_usd, pnl_pct, exit_reason, fill_basis, fill_date, exit_fill_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (rid, pos["ticker"], pos["entry_date"], o["decided_on"], e_adj, px, shares_adj, gross, cost,
              gross - cost, (px / e_adj - 1) * 100, reason, pos.get("fill_basis") or "close", pos.get("fill_date"),
              fdate))
        conn.execute("DELETE FROM paper_positions WHERE run_id=? AND ticker=?", (rid, pos["ticker"]))
        conn.execute("DELETE FROM paper_pending WHERE run_id=? AND ticker=? AND side='SELL'", (rid, pos["ticker"]))
        cash += notional + gross - cost
        open_pos.remove(pos)
        sold += 1

    # --- 1b. BUY fills ------------------------------------------------------------------------
    held = {p["ticker"] for p in open_pos}
    for o in [o for o in orders if o["side"] == "BUY"]:
        t = o["ticker"]
        bar = None if t in held else _next_bar(conn, t, o["decided_on"], today)
        if bar is None and t not in held and 0 <= days_since(o["decided_on"]) < FILL_WAIT_SESSIONS:
            continue                                       # no open yet: try again next step
        if bar is None or len(open_pos) >= run_cap or cash < size:
            why = ("already held" if t in held else "no bar" if bar is None else "no free slot at the open"
                   if len(open_pos) >= run_cap else "not enough cash at the open")
            log.info(f"'{run['name']}' {t}: order of {o['decided_on']} cancelled ({why})")
            conn.execute("DELETE FROM paper_pending WHERE run_id=? AND ticker=? AND side='BUY'", (rid, t))
            cancelled += 1
            continue
        fdate, px = bar
        stop = _entry_stop(cfg, px, o["atr"], o["stop_mult"], o["stop_pct"])
        try:
            conn.execute("""
                INSERT INTO paper_positions
                    (run_id, ticker, entry_date, entry_price, shares, stop_price, days_held, fill_basis, fill_date)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (rid, t, o["decided_on"], px, size / px, stop, max(days_since(o["decided_on"]), 0), "next_open", fdate))
        except sqlite3.IntegrityError:
            log.warning(f"'{run['name']}' already holds {t}; not overwriting")
            conn.execute("DELETE FROM paper_pending WHERE run_id=? AND ticker=? AND side='BUY'", (rid, t))
            continue
        conn.execute("DELETE FROM paper_pending WHERE run_id=? AND ticker=? AND side='BUY'", (rid, t))
        cash -= size
        open_pos.append({"ticker": t, "entry_date": o["decided_on"], "entry_price": px, "shares": size / px,
                         "stop_price": stop, "days_held": 0, "fill_basis": "next_open", "fill_date": fdate})
        held.add(t)
        bought += 1

    # --- 2a. exit decisions on today's close ----------------------------------------------------
    # `prices` is today's market AFTER the purchase floors (min price, dollar volume). A held stock that fell below
    # them is still sold on its own close, as the simulator does: a filter that decides what may be bought must never
    # decide what may be sold. Its real close today is read from the unfiltered table; without a bar today it is
    # marked at its last real close and decided on nothing (the unpriceable rule below).
    stale = _stale_marks(conn, [p["ticker"] for p in open_pos], prices, today)
    missing = [p["ticker"] for p in open_pos if p["ticker"] not in prices]
    closes_today = {r[0]: float(r[1]) for r in conn.execute(
        f"SELECT ticker, close FROM prices WHERE date=? AND close > 0 AND ticker IN ({','.join('?' * len(missing))})",
        (today, *missing))} if missing else {}
    waiting = {r[0] for r in conn.execute("SELECT ticker FROM paper_pending WHERE run_id=? AND side='SELL'", (rid,))}
    eff, to_sell = {}, 0
    for pos in open_pos[:]:
        t = pos["ticker"]
        px = prices.get(t, closes_today.get(t))
        elapsed = days_since(pos["entry_date"])
        held_days = elapsed if elapsed >= 0 else pos["days_held"] + 1
        e_adj = _anchored(conn, pos)
        eff[t] = e_adj
        if t in waiting:
            continue
        k = e_adj / float(pos["entry_price"]) if pos["entry_price"] else 1.0
        stop_adj = pos["stop_price"] * k if pos["stop_price"] else None
        reason = None
        if px is None:
            if held_days >= horizon * 4:
                # Unpriceable for a long time: nothing will ever fill it. Booked at its entry, as the close path does.
                notional = pos["shares"] * pos["entry_price"]
                cost = float(cost_model.round_trip(notional, dv.get(t, 0), notional / e_adj))
                conn.execute("""
                    INSERT OR REPLACE INTO paper_trades
                        (run_id, ticker, entry_date, exit_date, entry_price, exit_price, shares, gross_pnl_usd,
                         costs_usd, net_pnl_usd, pnl_pct, exit_reason, fill_basis, fill_date, exit_fill_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (rid, t, pos["entry_date"], today, e_adj, e_adj, notional / e_adj, 0.0, cost, -cost, 0.0,
                      "unpriceable", pos.get("fill_basis") or "close", pos.get("fill_date"), None))
                conn.execute("DELETE FROM paper_positions WHERE run_id=? AND ticker=?", (rid, t))
                cash += notional - cost
                open_pos.remove(pos)
                sold += 1
                continue
        elif stop_adj and px <= stop_adj:
            reason = "stop_loss"
        elif rk.get("take_profit_pct") and px >= e_adj * (1 + float(rk["take_profit_pct"]) / 100):
            reason = "take_profit"
        elif t in exits_today:
            reason = "exit_rule"
        elif held_days >= run_horizon:
            reason = "horizon_timeout"
        if reason:
            conn.execute("INSERT OR IGNORE INTO paper_pending (run_id, ticker, side, decided_on, reason, created_at) "
                         "VALUES (?,?,?,?,?,?)", (rid, t, "SELL", today, reason, storage._now()))
            waiting.add(t)
            to_sell += 1
        conn.execute("UPDATE paper_positions SET days_held=? WHERE run_id=? AND ticker=?", (held_days, rid, t))
        pos["days_held"] = held_days

    # --- 2b. entry decisions --------------------------------------------------------------------
    # A slot that a pending sale frees at the next open may be refilled at that same open (sells fill first);
    # the cash it brings is counted at today's mark. Pending buys that have not filled yet hold their slot and cash.
    buys = [r[0] for r in conn.execute("SELECT ticker FROM paper_pending WHERE run_id=? AND side='BUY'", (rid,))]
    free = run_cap - (len(open_pos) - len(waiting & {p["ticker"] for p in open_pos})) - len(buys)
    proj = cash - size * len(buys) + sum(
        _mark_value(conn, p, prices.get(p["ticker"], stale.get(p["ticker"]))) for p in open_pos if p["ticker"] in waiting)
    taken = {p["ticker"] for p in open_pos} | set(buys)
    to_buy = 0
    for _, row in candidates.iterrows():
        if free <= 0 or proj < size:
            break
        t = str(row["ticker"])
        if t in taken or not float(row["close"]) > 0:
            continue
        atr = row.get("atr_14")
        pcol = rk.get("stop_pct_col")
        pv = row.get(pcol) if pcol else None
        conn.execute("INSERT OR IGNORE INTO paper_pending (run_id, ticker, side, decided_on, reason, atr, stop_mult, "
                     "stop_pct, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (rid, t, "BUY", today, "entry rule" if genome else "classifier",
                      float(atr) if atr is not None and atr == atr else None,
                      float(rk["stop_atr_multiple"]) if rk.get("stop_atr_multiple") else None,
                      float(pv) if pv is not None and pv == pv else None, storage._now()))
        taken.add(t)
        free -= 1
        proj -= size
        to_buy += 1

    # --- 3. mark at today's close (positions waiting to sell included) ---------------------------
    positions_value = sum(p["shares"] * p["entry_price"]
                          * prices.get(p["ticker"], stale.get(p["ticker"], eff.get(p["ticker"], p["entry_price"])))
                          / eff.get(p["ticker"], p["entry_price"])
                          for p in open_pos)
    equity = cash + positions_value
    conn.execute("""
        INSERT OR REPLACE INTO paper_equity (run_id, date, cash_usd, positions_usd, equity_usd, open_positions)
        VALUES (?,?,?,?,?,?)
    """, (rid, today, cash, positions_value, equity, len(open_pos)))
    conn.execute("UPDATE paper_runs SET cash_usd=?, last_step_on=? WHERE run_id=?", (cash, today, rid))
    conn.commit()
    log.info(f"'{run['name']}' {today}: filled {bought} buys / {sold} sells at the open ({cancelled} cancelled); "
             f"ordered {to_buy} buys / {to_sell} sells for the next open | {len(open_pos)} held | equity "
             f"${equity:,.2f} | NET P&L ${equity - run['capital_usd']:+,.2f}")


def step(conn, cfg: dict) -> None:
    """Advance every open run by one trading day."""
    runs = conn.execute("SELECT * FROM paper_runs WHERE status = 'open'").fetchall()
    if not runs:
        log.info("No open paper runs.")
        return

    # Prices come from the classifier's view of today, which is the widest
    # tradeable set; genome runs narrow it further with their own entry rule.
    market = _latest_scores(conn, cfg)
    if market.empty:
        log.warning("No scoreable candidates — is the database stale?")
        return
    today = str(market["date"].max())[:10]
    prices = dict(zip(market["ticker"].astype(str), market["close"]))
    dv = (dict(zip(market["ticker"].astype(str), market["dollar_volume_20"]))
          if "dollar_volume_20" in market else {})

    cost_model = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    cap = research_positions(cfg)
    horizon = cfg["labeling"]["horizon_days"]

    # Trading days elapsed, measured against the calendar rather than counted by
    # invocation. The old `days_held + 1` counted how many times this function
    # ran, so a missed cron morning silently extended every open position past
    # its holding limit — and a catch-up after a gap compressed five days of
    # price movement into one tick. Verified: a position entered 2026-09-04 and
    # priced on 2026-09-11 reported two days held against five actually elapsed.
    calendar = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM prices WHERE date <= ? ORDER BY date DESC LIMIT 400",
        (today,)).fetchall()]
    offset = {d: i for i, d in enumerate(calendar)}      # 0 = today, counting back

    def days_since(entry_date: str) -> int:
        """Trading days between an entry and today. Falls back to the stored count."""
        e = str(entry_date)[:10]
        return offset[e] if e in offset else -1

    for run in runs:
        run = dict(run)
        # Each run trades its own strategy. A Lab genome brings its own entry
        # rule, exit rule and risk parameters; those beat the config defaults,
        # because a strategy validated at a 45-day hold is a different strategy
        # if paper trading closes it at 5.
        # Conviction runs are portfolio-level and weekly; they do not use the
        # per-trade stop/hold machinery below.
        if _rotation_of(run):
            if run["last_step_on"] != today:
                _rotation_step(conn, cfg, run, today, cost_model)
            continue
        if _kalman_of(run):
            continue    # kalman_pair.step_fund() steps this fund (daily.sh [5d]); no entry rule here
        if _conviction_of(run):
            if _conviction_step(conn, cfg, run, today, prices, dv, cost_model):
                continue

        genome = _strategy_of(run)
        if genome is None:
            candidates, exits_today = market, set()
            run_cap, run_horizon = cap, horizon
        else:
            candidates, exits_today = _genome_signals(conn, cfg, genome)
            rk = genome.get("risk", {})
            run_cap = int(rk.get("max_open_positions") or cap)
            run_horizon = int(rk.get("max_hold_days") or horizon)
            fundable = int(run["capital_usd"] // size)
            if run_cap > fundable:
                # The $100 mandate binds before the genome's own cap does. Say so
                # rather than let the run quietly trade a different strategy from
                # the one that was validated.
                log.info(f"'{run['name']}' wants {run_cap} positions; ${run['capital_usd']:,.0f} "
                         f"at ${size:.0f} funds {fundable}. Trading the smaller.")
                run_cap = fundable
            if candidates.empty:
                log.info(f"'{run['name']}' {today}: entry rule fired on nothing today")
        if run["last_step_on"] == today:
            log.info(f"'{run['name']}' already stepped to {today}")
            continue
        if fill_mode(cfg) == "next_open":
            _step_next_open(conn, cfg, run, today, prices, dv, candidates, exits_today, genome, run_cap, run_horizon,
                            horizon, size, cost_model, days_since)
            continue
        # The old close fills (paper.fills: close — kept as the rollback). Orders left by the next-open path would
        # never fill here; they are dropped, and every position is re-decided on today's close below.
        n_drop = conn.execute("DELETE FROM paper_pending WHERE run_id=?", (run["run_id"],)).rowcount
        if n_drop:
            log.info(f"'{run['name']}': {n_drop} next-open orders dropped (paper.fills is 'close')")

        open_pos = [dict(r) for r in conn.execute(
            "SELECT * FROM paper_positions WHERE run_id = ?", (run["run_id"],))]
        stale = _stale_marks(conn, [p["ticker"] for p in open_pos], prices, today)
        cash = run["cash_usd"]
        closed = 0

        # --- exits first, so freed slots can be refilled the same day ---------
        eff = {}                                         # ticker -> entry on today's adjusted series
        for pos in open_pos[:]:
            px = prices.get(pos["ticker"])
            elapsed = days_since(pos["entry_date"])
            held = elapsed if elapsed >= 0 else pos["days_held"] + 1
            e_adj = _anchored(conn, pos)          # a next-open fill (if the switch was rolled back) anchors on its open
            k = e_adj / float(pos["entry_price"]) if pos["entry_price"] else 1.0
            eff[pos["ticker"]] = e_adj
            stop_adj = pos["stop_price"] * k if pos["stop_price"] else None
            notional = pos["shares"] * pos["entry_price"]          # dollars paid: unchanged by any adjustment
            reason = None
            if px is None:
                # No current price. Not necessarily wrong — it may have stopped
                # trading — but a position we cannot price cannot be managed.
                if held >= horizon * 4:
                    reason, px = "unpriceable", e_adj
            elif stop_adj and px <= stop_adj:
                reason = "stop_loss"
            elif (genome and genome.get("risk", {}).get("take_profit_pct")
                  and px >= e_adj * (1 + float(
                      genome["risk"]["take_profit_pct"]) / 100)):
                reason = "take_profit"
            elif pos["ticker"] in exits_today:
                reason = "exit_rule"
            elif held >= run_horizon:
                reason = "horizon_timeout"

            if reason:
                gross = notional * (px / e_adj - 1)
                shares_adj = notional / e_adj
                cost = cost_model.round_trip(notional, dv.get(pos["ticker"], 0),
                                             shares_adj)
                conn.execute("""
                    INSERT OR REPLACE INTO paper_trades
                        (run_id, ticker, entry_date, exit_date, entry_price, exit_price,
                         shares, gross_pnl_usd, costs_usd, net_pnl_usd, pnl_pct, exit_reason)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (run["run_id"], pos["ticker"], pos["entry_date"], today,
                      e_adj, px, shares_adj, gross, float(cost),
                      gross - float(cost), (px / e_adj - 1) * 100, reason))
                conn.execute("DELETE FROM paper_positions WHERE run_id=? AND ticker=?",
                             (run["run_id"], pos["ticker"]))
                cash += notional + gross - float(cost)
                open_pos.remove(pos)
                closed += 1
            else:
                conn.execute("UPDATE paper_positions SET days_held=? WHERE run_id=? AND ticker=?",
                             (held, run["run_id"], pos["ticker"]))
                pos["days_held"] = held

        # --- entries into whatever slots are free -----------------------------
        held_tickers = {p["ticker"] for p in open_pos}
        opened = 0
        for _, row in candidates.iterrows():
            if len(open_pos) >= run_cap or cash < size:
                break
            t = str(row["ticker"])
            if t in held_tickers:
                continue
            px = float(row["close"])
            if px <= 0:
                continue
            shares = size / px
            atr = row.get("atr_14")
            mult = (genome or {}).get("risk", {}).get("stop_atr_multiple")
            if mult and atr and atr == atr and atr > 0:
                stop = px - float(mult) * float(atr)
            else:
                stop = calculate_stop_loss(px, atr, cfg)
            # Stage P4: a per-trade stop from a column (simulator's stop_pct_col), tightest wins.
            pcol = (genome or {}).get("risk", {}).get("stop_pct_col")
            pv = row.get(pcol) if pcol else None
            if pv is not None and pv == pv:
                stop = max(stop, px * (1 + min(max(float(pv), -0.5), -0.01)))
            # Plain INSERT, and skip on conflict. INSERT OR REPLACE let a
            # repeated step overwrite a held position: the old shares vanished
            # with no trade record while the new buy still left cash, which is
            # how 11 funds' cash stopped reconciling (found 2026-09-24).
            try:
                conn.execute("""
                    INSERT INTO paper_positions
                        (run_id, ticker, entry_date, entry_price, shares, stop_price, days_held)
                    VALUES (?,?,?,?,?,?,0)
                """, (run["run_id"], t, today, px, shares, float(stop)))
            except sqlite3.IntegrityError:
                log.warning(f"'{run['name']}' already holds {t}; not overwriting")
                continue
            cash -= size
            open_pos.append({"ticker": t, "shares": shares, "entry_price": px})
            eff[t] = px
            held_tickers.add(t)
            opened += 1

        # A position with no bar today is marked at its LAST REAL CLOSE, never
        # at entry. Marking at entry hid every loss on 2026-09-22, when the
        # source was missing that session for most tickers (accounting.py).
        # Marked on the adjusted series: value = dollars paid x (mark / entry on the same series).
        positions_value = sum(p["shares"] * p["entry_price"]
                              * prices.get(p["ticker"], stale.get(p["ticker"], eff.get(p["ticker"], p["entry_price"])))
                              / eff.get(p["ticker"], p["entry_price"])
                              for p in open_pos)
        equity = cash + positions_value
        conn.execute("""
            INSERT OR REPLACE INTO paper_equity
                (run_id, date, cash_usd, positions_usd, equity_usd, open_positions)
            VALUES (?,?,?,?,?,?)
        """, (run["run_id"], today, cash, positions_value, equity, len(open_pos)))
        conn.execute("UPDATE paper_runs SET cash_usd=?, last_step_on=? WHERE run_id=?",
                     (cash, today, run["run_id"]))
        conn.commit()

        pnl = equity - run["capital_usd"]
        log.info(f"'{run['name']}' {today}: {opened} opened, {closed} closed, "
                 f"{len(open_pos)} held | equity ${equity:,.2f} | NET P&L ${pnl:+,.2f}")


def status(conn) -> None:
    runs = [dict(r) for r in conn.execute("SELECT * FROM paper_runs ORDER BY created_at")]
    if not runs:
        print("No paper runs. Start one with --start <name>.")
        return
    for r in runs:
        eq = conn.execute("SELECT * FROM paper_equity WHERE run_id=? ORDER BY date DESC LIMIT 1",
                          (r["run_id"],)).fetchone()
        realised = conn.execute(
            "SELECT COALESCE(SUM(net_pnl_usd),0) s, COUNT(*) n FROM paper_trades WHERE run_id=?",
            (r["run_id"],)).fetchone()
        equity = eq["equity_usd"] if eq else r["capital_usd"]
        pnl = equity - r["capital_usd"]
        print(f"\n{r['name']}  [{r['status']}]  started {r['started_on']}")
        verdict = "PROFIT" if pnl > 0 else ("LOSS" if pnl < 0 else "FLAT")
        print(f"  NET P&L        ${pnl:+,.2f}   ({verdict})")
        print(f"  equity         ${equity:,.2f} of ${r['capital_usd']:,.2f}")
        print(f"  realised       ${realised['s']:+,.2f} over {realised['n']} closed trades")
        print(f"  open positions {eq['open_positions'] if eq else 0}")
        print(f"  last stepped   {r['last_step_on'] or 'never'}")


def close(conn, cfg: dict, name: str) -> None:
    """Close a run out and file it in the experiment ledger alongside the backtests."""
    r = conn.execute("SELECT * FROM paper_runs WHERE name = ?", (name,)).fetchone()
    if not r:
        print(f"No paper run '{name}'.")
        return
    r = dict(r)
    trades = pd.read_sql_query("SELECT * FROM paper_trades WHERE run_id = ?",
                               conn, params=[r["run_id"]])
    eq = pd.read_sql_query("SELECT * FROM paper_equity WHERE run_id=? ORDER BY date",
                           conn, params=[r["run_id"]])
    net = float(trades["net_pnl_usd"].sum()) if not trades.empty else 0.0
    dd = storage.max_drawdown_pct(eq["equity_usd"]) if not eq.empty else 0.0

    storage.record_experiment(conn, {
        "id": f"paper:{name}", "name": name, "kind": "paper",
        "config": r["strategy"],
        "period_start": r["started_on"], "period_end": r["last_step_on"],
        "n_trades": len(trades), "capital_usd": r["capital_usd"],
        "net_pnl_usd": round(net, 2),
        "net_pnl_pct": round(net / r["capital_usd"] * 100, 1) if r["capital_usd"] else None,
        "gross_pnl_usd": float(trades["gross_pnl_usd"].sum()) if not trades.empty else 0.0,
        "costs_usd": float(trades["costs_usd"].sum()) if not trades.empty else 0.0,
        "win_rate_pct": round((trades["net_pnl_usd"] > 0).mean() * 100, 1) if not trades.empty else None,
        "max_drawdown_pct": round(dd, 1),
        "avg_days_held": None,
        "notes": "forward paper trading — no survivorship bias",
    }, trades)
    conn.execute("UPDATE paper_runs SET status='closed' WHERE run_id=?", (r["run_id"],))
    conn.commit()
    print(f"Closed '{name}'. NET P&L ${net:+,.2f} over {len(trades)} trades.")
    print("Recorded in the experiment ledger — compare with experiments.py")


def promote_survivors(conn, cfg: dict, limit: int = 5, stage: str = "validation",
                      order: str = "excess", run_id: str | None = None) -> list[str]:
    """
    Open a paper run for each of the best strategies that cleared `stage`.

    This is the join the ladder was missing. Paper trading could only ever run
    the classifier, so a Lab survivor had no path to the one measurement in this
    project with no survivorship bias — the stage every backtest figure is
    explicitly not trusted enough to skip.

    Deduplicated by structure: five settings of one idea would produce five
    correlated paper runs and look like five independent confirmations. One run
    per distinct idea, best setting first.
    """
    import ledger
    ledger.init(conn)
    rows = conn.execute("""
        SELECT s.id, s.genome, s.entry_desc, e.excess_pnl_usd, e.sharpe, e.n_trades
        FROM promotions p
        JOIN strategies s ON s.id = p.strategy_id
        JOIN evaluations e ON e.strategy_id = s.id
        WHERE p.stage = ? AND p.decision = 'pass'""" + (" AND s.run_id = ?" if run_id else "") + """
        ORDER BY e.excess_pnl_usd """ + ("ASC" if order == "reverse" else "DESC"),
        (stage, run_id) if run_id else (stage,)).fetchall()
    if not rows:
        log.warning(f"Nothing has passed {stage} — nothing to paper trade.")
        return []

    opened, shapes, entries = [], set(), {}
    for r in rows:
        if len(opened) >= limit:
            break
        try:
            g = json.loads(r["genome"])
            shp = gn.genome_shape(g)
        except Exception:
            continue
        if shp in shapes:
            continue
        shapes.add(shp)
        ent = gn.shape(g["entry"])
        entries[ent] = entries.get(ent, 0) + 1
        name = f"lab_{r['id'][:8]}"
        if conn.execute("SELECT 1 FROM paper_runs WHERE name=?", (name,)).fetchone():
            log.info(f"'{name}' already has a paper run; skipping.")
            continue
        start(conn, cfg, name, strategy=json.dumps(g))
        opened.append(name)
        log.info(f"  {name}: {(r['entry_desc'] or '')[:58]}  "
                 f"(search excess ${(r['excess_pnl_usd'] or 0):+,.0f}, "
                 f"Sharpe {(r['sharpe'] or 0):.2f})")

    dupes = {e: n for e, n in entries.items() if n > 1}
    print(f"\n  Opened {len(opened)} paper runs across {len(shapes)} distinct ideas.")
    if dupes:
        print(f"  Note: {sum(dupes.values())} of them share an entry rule and differ "
              f"only by exit —\n  they will move together. Read them as one result, "
              f"not as independent confirmations.")
    print("  Nothing is measured until these have run forward for weeks. Step them "
          "daily with\n  `python paper_trading.py --step`; the result is the only "
          "figure in this project\n  that carries no survivorship bias.")
    return opened


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", metavar="NAME", help="Open a new paper run.")
    parser.add_argument("--step", action="store_true", help="Advance open runs one day.")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run-id", default=None, help="With --promote: only this search run's survivors.")
    parser.add_argument("--close", metavar="NAME")
    parser.add_argument("--promote", action="store_true",
                        help="Open paper runs for the best strategies that passed validation.")
    parser.add_argument("--limit", type=int, default=5,
                        help="How many distinct ideas to promote (default 5).")
    parser.add_argument("--order", default="excess", choices=("excess", "reverse"),
                        help="'reverse' promotes the weakest survivors — useful for "
                             "running a low-exposure family alongside a high one.")
    args = parser.parse_args()

    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    init(conn)

    if args.promote:
        promote_survivors(conn, cfg, args.limit, order=args.order, run_id=args.run_id)
    elif args.start:
        start(conn, cfg, args.start)
    elif args.step:
        step(conn, cfg)
    elif args.close:
        close(conn, cfg, args.close)
    else:
        status(conn)
    conn.close()


if __name__ == "__main__":
    main()
