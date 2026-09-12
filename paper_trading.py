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
    conn.commit()


def start(conn, cfg: dict, name: str, strategy: str = "model") -> str:
    capital = cfg["risk"]["position_size_usd"] * cfg["risk"]["max_open_positions"]
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
    latest["score"] = model.predict_proba(latest[FEATURE_COLS])[:, 1] * 100
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
        return g if isinstance(g, dict) and "entry" in g else None
    except (ValueError, TypeError):
        log.warning(f"Run '{run.get('name')}' has an unreadable strategy; "
                    f"falling back to the classifier.")
        return None


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
    cap = cfg["risk"]["max_open_positions"]
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

        open_pos = [dict(r) for r in conn.execute(
            "SELECT * FROM paper_positions WHERE run_id = ?", (run["run_id"],))]
        cash = run["cash_usd"]
        closed = 0

        # --- exits first, so freed slots can be refilled the same day ---------
        for pos in open_pos[:]:
            px = prices.get(pos["ticker"])
            elapsed = days_since(pos["entry_date"])
            held = elapsed if elapsed >= 0 else pos["days_held"] + 1
            reason = None
            if px is None:
                # No current price. Not necessarily wrong — it may have stopped
                # trading — but a position we cannot price cannot be managed.
                if held >= horizon * 4:
                    reason, px = "unpriceable", pos["entry_price"]
            elif pos["stop_price"] and px <= pos["stop_price"]:
                reason = "stop_loss"
            elif (genome and genome.get("risk", {}).get("take_profit_pct")
                  and px >= pos["entry_price"] * (1 + float(
                      genome["risk"]["take_profit_pct"]) / 100)):
                reason = "take_profit"
            elif pos["ticker"] in exits_today:
                reason = "exit_rule"
            elif held >= run_horizon:
                reason = "horizon_timeout"

            if reason:
                notional = pos["shares"] * pos["entry_price"]
                gross = pos["shares"] * (px - pos["entry_price"])
                cost = cost_model.round_trip(notional, dv.get(pos["ticker"], 0),
                                             pos["shares"])
                conn.execute("""
                    INSERT OR REPLACE INTO paper_trades
                        (run_id, ticker, entry_date, exit_date, entry_price, exit_price,
                         shares, gross_pnl_usd, costs_usd, net_pnl_usd, pnl_pct, exit_reason)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (run["run_id"], pos["ticker"], pos["entry_date"], today,
                      pos["entry_price"], px, pos["shares"], gross, float(cost),
                      gross - float(cost), (px / pos["entry_price"] - 1) * 100, reason))
                conn.execute("DELETE FROM paper_positions WHERE run_id=? AND ticker=?",
                             (run["run_id"], pos["ticker"]))
                cash += pos["shares"] * px - float(cost)
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
            conn.execute("""
                INSERT OR REPLACE INTO paper_positions
                    (run_id, ticker, entry_date, entry_price, shares, stop_price, days_held)
                VALUES (?,?,?,?,?,?,0)
            """, (run["run_id"], t, today, px, shares, float(stop)))
            cash -= size
            open_pos.append({"ticker": t, "shares": shares, "entry_price": px})
            held_tickers.add(t)
            opened += 1

        positions_value = sum(p["shares"] * prices.get(p["ticker"], p["entry_price"])
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
                      order: str = "excess") -> list[str]:
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
        WHERE p.stage = ? AND p.decision = 'pass'
        ORDER BY e.excess_pnl_usd """ + ("ASC" if order == "reverse" else "DESC"),
        (stage,)).fetchall()
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
        promote_survivors(conn, cfg, args.limit, order=args.order)
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
