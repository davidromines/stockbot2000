"""
The null hypothesis, measured. What does doing nothing clever earn?

Every fitness score and every promotion gate in this project compared results
against **zero**. That is not a test of skill. Measured on our own data, buying at
random and holding five days earned:

    2018-19   +0.206% per trade   (+0.003% net of costs)
    2020-22   +0.269% per trade   (+0.066% net of costs)
    2023-26   +0.385% per trade   (+0.182% net of costs)

Positive in every window, because the market went up. So "net P&L > 0" tests
whether a strategy was long during a bull market, not whether it picked well —
which is why 52% of *random, never-evolved* strategies passed the validation gate.

This module computes that null so everything downstream can be scored as **excess
over it**. A strategy that beats zero is uninteresting; one that beats buying at
random, after costs, is the entire point.

The null is a **surface, not a number**: it varies with how long a strategy holds
*and* with how expensive the stocks it buys are. Both dimensions are loopholes if
left flat — see `null_surface`.

Benchmarks are cached per window because the null does not depend on the strategy
being tested, and recomputing it for every candidate would dominate a search.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np

import costs as costs_mod
import storage
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("benchmark")

ANCHORS = (1, 2, 3, 5, 8, 13, 21, 34, 45, 60)

# Price-band edges in dollars. The open band above the last edge is closed at
# PRICE_CEIL so the value can sit in a STRICT table's primary key.
PRICE_BAND_EDGES = (10.0, 20.0, 50.0, 100.0)
PRICE_CEIL = 1e12
ALL_PRICES = (0.0, PRICE_CEIL)


class Surface:
    """
    The measured null, indexed by price band and holding period.

    Behaves like the plain `{band: {hold: pct}}` dict it replaced, so existing
    `surface[band][5]` lookups still work, but it also carries each band's
    representative price. Those anchors are what let the charge vary continuously
    with price instead of in steps — see `null_vector`.

    Plain attributes, so it survives the fork pool without a custom reducer.
    """

    def __init__(self, cells: dict, anchors: dict):
        self.cells = cells
        self.anchors = anchors      # band -> median entry price within it

    def __getitem__(self, band):
        return self.cells[band]

    def __contains__(self, band):
        return band in self.cells

    def __iter__(self):
        return iter(self.cells)

    def __bool__(self):
        return bool(self.cells)

    def get(self, band, default=None):
        return self.cells.get(band, default)

    def ladder(self, hold_days: float) -> list[tuple[float, float]]:
        """(price, null %) pairs at this holding period, ascending by price."""
        pts = [(self.anchors[b], null_for_hold(self.cells[b], hold_days))
               for b in self.cells
               if b != ALL_PRICES and self.anchors.get(b)]
        return sorted(pts)


def price_bands(cfg: dict) -> list[tuple[float, float]]:
    """The price bands the null is measured in, from config or the default."""
    edges = tuple(cfg.get("benchmark", {}).get("price_band_edges") or PRICE_BAND_EDGES)
    lo = float(cfg.get("risk", {}).get("min_price") or 0.0)
    bounds = [lo] + [e for e in sorted(float(e) for e in edges) if e > lo] + [PRICE_CEIL]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def init(conn) -> None:
    """
    Create the cache table, replacing the pre-bucketed schema if present.

    The old table keyed the null on (window, horizon) alone. Price is now part of
    the key, and a STRICT table's primary key cannot be altered in place — so an
    old cache is dropped rather than migrated. It is a cache; recomputing is the
    correct response to it being wrong.
    """
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                       "AND name='benchmarks'").fetchone()
    if row:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(benchmarks)")}
        if "price_lo" not in cols or "median_price" not in cols:
            log.info("Dropping the pre-bucketed benchmark cache — price is now part of the key")
            conn.execute("DROP TABLE benchmarks")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS benchmarks (
            window_start  TEXT NOT NULL,
            window_end    TEXT NOT NULL,
            horizon_days  INTEGER NOT NULL,
            price_lo      REAL NOT NULL,   -- entry-price band, inclusive
            price_hi      REAL NOT NULL,   -- exclusive
            min_price     REAL, min_dollar_volume REAL,
            median_price  REAL,             -- the band's representative price
            n_obs         INTEGER NOT NULL,
            gross_pct     REAL NOT NULL,    -- avg forward return per trade
            cost_pct      REAL NOT NULL,
            net_pct       REAL NOT NULL,    -- what a random entry actually earns
            computed_at   TEXT NOT NULL,
            PRIMARY KEY (window_start, window_end, horizon_days, price_lo, price_hi,
                         min_price, min_dollar_volume)
        ) STRICT
    """)
    conn.commit()


def _load(conn, cfg, window):
    return storage.load_training_frame(
        conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
        start_date=window[0], end_date=window[1],
        min_price=cfg["risk"].get("min_price"),
        min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
        include_liquidity=True)


def _cached(conn, window, horizon, band, mp, mv):
    return conn.execute("""
        SELECT * FROM benchmarks WHERE window_start=? AND window_end=?
          AND horizon_days=? AND price_lo=? AND price_hi=?
          AND min_price IS ? AND min_dollar_volume IS ?
    """, (window[0], window[1], horizon, band[0], band[1], mp, mv)).fetchone()


def _store(conn, rec) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO benchmarks
            (window_start, window_end, horizon_days, price_lo, price_hi,
             min_price, min_dollar_volume, median_price, n_obs, gross_pct, cost_pct,
             net_pct, computed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, tuple(rec[k] for k in ("window_start", "window_end", "horizon_days", "price_lo",
                                "price_hi", "min_price", "min_dollar_volume",
                                "median_price", "n_obs", "gross_pct", "cost_pct",
                                "net_pct", "computed_at")))


def _forward(df, horizon: int):
    """
    Forward return over `horizon` bars, computed on the **whole** frame.

    Computed before any price filtering, deliberately. Filtering to a price band
    first and then calling pct_change would measure the gap between a ticker's
    surviving rows — two observations that happen to both sit under $10, whatever
    the calendar distance between them — instead of its return over the next
    `horizon` trading days.
    """
    return df.groupby("ticker", observed=True)["close"].pct_change(horizon).shift(-horizon)


def _cell(df, fwd, cfg, window, horizon, band, mp, mv) -> dict:
    """The null for one (holding period, price band) cell, from an in-memory frame."""
    rec = {"window_start": window[0], "window_end": window[1], "horizon_days": horizon,
           "price_lo": band[0], "price_hi": band[1], "min_price": mp,
           "min_dollar_volume": mv, "median_price": None, "n_obs": 0, "gross_pct": 0.0,
           "cost_pct": 0.0, "net_pct": 0.0, "computed_at": storage._now()}

    in_band = (slice(None) if band == ALL_PRICES
               else (df["close"] >= band[0]) & (df["close"] < band[1]))
    sub = df if band == ALL_PRICES else df[in_band]
    valid = (fwd if band == ALL_PRICES else fwd[in_band]).dropna()
    if sub.empty or valid.empty:
        return rec

    cm = costs_mod.CostModel(cfg)
    size = cfg["risk"]["position_size_usd"]
    # Cost of the median name actually traded in THIS band, not of a hypothetical
    # one. Cheap stocks are less liquid and pay a wider spread; charging them the
    # whole market's cost would understate what they have to overcome.
    median_dv = float(sub["dollar_volume_20"].median()) if "dollar_volume_20" in sub else 0.0
    median_px = float(sub["close"].median()) or 1.0
    cost_pct = float(cm.round_trip(size, median_dv, size / median_px) / size * 100)

    gross = float(valid.mean()) * 100
    rec.update(n_obs=int(len(valid)), gross_pct=gross, cost_pct=cost_pct,
               net_pct=gross - cost_pct, median_price=median_px)
    return rec


def compute(conn, cfg: dict, window: tuple[str, str], horizon: int | None = None,
            band: tuple[float, float] = ALL_PRICES, refresh: bool = False) -> dict:
    """
    Average net return of a random entry held `horizon` days in this window.

    This is the number a strategy has to beat to have demonstrated anything. It
    is computed over the same filtered universe the strategy trades, so the
    comparison is like for like — benchmarking a liquid-large-cap strategy
    against the whole market including microcaps would be its own kind of
    cheating.
    """
    init(conn)
    horizon = horizon or cfg["labeling"]["horizon_days"]
    mp, mv = cfg["risk"].get("min_price"), cfg["risk"].get("min_dollar_volume")

    if not refresh:
        row = _cached(conn, window, horizon, band, mp, mv)
        if row:
            return dict(row)

    log.info(f"Computing the null for {window[0]} -> {window[1]} ({horizon}d hold, "
             f"${band[0]:,.0f}-${band[1]:,.0f})")
    df = _load(conn, cfg, window)
    if df.empty:
        return {"net_pct": 0.0, "gross_pct": 0.0, "cost_pct": 0.0, "n_obs": 0}
    df = df.sort_values(["ticker", "date"])
    rec = _cell(df, _forward(df, horizon), cfg, window, horizon, band, mp, mv)
    _store(conn, rec)
    conn.commit()
    log.info(f"  null: {rec['gross_pct']:+.3f}% gross, {rec['cost_pct']:.3f}% costs, "
             f"{rec['net_pct']:+.3f}% net over {rec['n_obs']:,} observations")
    return rec


def null_surface(conn, cfg: dict, window: tuple[str, str],
                 anchors: tuple[int, ...] = ANCHORS,
                 refresh: bool = False) -> Surface:
    """
    The null at every holding period **and every price level**, not just one.

    Two dimensions, because a flat null is a loophole in each of them:

    *Holding period.* The null is +0.066% at a 5-day hold and +2.128% at 40 days,
    so benchmarking a 40-day strategy against the 5-day figure understates what it
    should beat by a factor of 32. Market drift accrues with time held, and the
    search duly learned to hold longer, drifting to a median hold of 20.5 days.

    *Price.* This is the one that mattered. Charged a single market-wide null, the
    search's best answer was `sma_200 < 8` — "buy stocks under about eight
    dollars" — which is a price filter, not a strategy. Cheap stocks have their
    own return and volatility profile, and they are also exactly where
    survivorship bias bites hardest, since the sub-$8 names that went to zero are
    absent from this database. Scored against other cheap stocks instead of
    against the whole market, that rule has to show it picked *well among them*.

    Computed at anchor horizons and interpolated between them, and cached cell by
    cell. The frame is loaded from SQL once for the whole surface: fifty separate
    passes over five million rows would cost far more than the accuracy is worth.
    """
    init(conn)
    mp, mv = cfg["risk"].get("min_price"), cfg["risk"].get("min_dollar_volume")
    bands = price_bands(cfg) + [ALL_PRICES]

    surface: dict[tuple[float, float], dict[int, float]] = {b: {} for b in bands}
    centres: dict[tuple[float, float], float] = {}
    missing = []
    for b in bands:
        for h in anchors:
            row = None if refresh else _cached(conn, window, h, b, mp, mv)
            if row:
                surface[b][h] = float(row["net_pct"])
                if row["median_price"]:
                    centres[b] = float(row["median_price"])
            else:
                missing.append((b, h))

    if missing:
        log.info(f"Computing {len(missing)} null cells for {window[0]} -> {window[1]}")
        df = _load(conn, cfg, window)
        if df.empty:
            return Surface({b: {h: 0.0 for h in anchors} for b in bands}, {})
        df = df.sort_values(["ticker", "date"])
        # Grouped by horizon so each forward-return pass over five million rows is
        # computed once and reused across every price band.
        for h in sorted({h for _, h in missing}):
            fwd = _forward(df, h)
            for b in [b for b, hh in missing if hh == h]:
                rec = _cell(df, fwd, cfg, window, h, b, mp, mv)
                _store(conn, rec)
                surface[b][h] = float(rec["net_pct"])
                if rec["median_price"]:
                    centres[b] = float(rec["median_price"])
            del fwd
        conn.commit()
        del df

    # A band with too little data to measure falls back to the market-wide null
    # rather than to zero. Zero would be a free pass for any strategy that found
    # a thinly populated corner of the price range.
    for b in bands:
        if b == ALL_PRICES:
            continue
        for h in anchors:
            if not np.isfinite(surface[b].get(h, np.nan)) or _thin(conn, window, h, b, mp, mv):
                surface[b][h] = surface[ALL_PRICES][h]
                centres.pop(b, None)
    return Surface(surface, centres)


def _thin(conn, window, horizon, band, mp, mv, floor: int = 5000) -> bool:
    row = _cached(conn, window, horizon, band, mp, mv)
    return bool(row) and int(row["n_obs"]) < floor


def null_for_hold(curve: dict[int, float], hold_days: float) -> float:
    """Interpolate the null for an arbitrary holding period."""
    if not curve:
        return 0.0
    ks = sorted(curve)
    h = max(ks[0], min(float(hold_days), ks[-1]))
    for a, b in zip(ks, ks[1:]):
        if a <= h <= b:
            if b == a:
                return curve[a]
            w = (h - a) / (b - a)
            return curve[a] * (1 - w) + curve[b] * w
    return curve[ks[-1]]


def null_vector(surface, entry_prices, hold_days: float, bands=None):
    """
    The null charged to each trade individually, as an array of percentages.

    **Interpolated across price, not stepped.** Bands are a convenience for
    measuring; the market has no edge at $10.00. Charging a flat rate inside each
    band leaves a gradient the search will ride straight to the band floor — and
    it did: with hard bands the surviving rules moved from `sma_200 < 8` to
    `sma_200 < 6.81`, entering at a median $6.64 against a $5-10 band whose own
    median was nearer $7.30, collecting the difference as "excess". Interpolating
    between band centres in log price removes that step, so buying cheaper raises
    the bar continuously rather than for free until the next edge.

    Per trade rather than per strategy because the excess P&L *series* — not just
    its total — feeds Sharpe and drawdown. Subtracting one average null from every
    trade would leave a strategy that mixes $6 and $600 names looking steadier
    than it was.
    """
    px = np.asarray(entry_prices, dtype="float64") if entry_prices is not None else np.array([])
    market = null_for_hold(surface.get(ALL_PRICES, {}), hold_days) if surface else 0.0
    if px.size == 0 or not surface:
        return np.full(px.shape, market, dtype="float64")

    ladder = surface.ladder(hold_days) if hasattr(surface, "ladder") else []
    if len(ladder) >= 2:
        xs = np.log(np.array([p for p, _ in ladder], dtype="float64"))
        ys = np.array([v for _, v in ladder], dtype="float64")
        safe = np.where(np.isfinite(px) & (px > 0), px, np.exp(xs[-1]))
        lp = np.log(safe)
        out = np.interp(lp, xs, ys)

        # Below the cheapest measured band, extend the slope rather than clamping.
        # Clamping leaves a flat floor between min_price and the lowest anchor —
        # exactly the stretch the search was already exploiting, so a clamp just
        # moves the free gradient down instead of closing it. The null keeps
        # rising as price falls; extrapolating the measured slope says so.
        below = lp < xs[0]
        if below.any() and xs[1] > xs[0]:
            slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
            out[below] = ys[0] + slope * (lp[below] - xs[0])
        return out

    # Not enough measured bands to interpolate — fall back to hard buckets.
    out = np.full(px.shape, market, dtype="float64")
    for b in (bands or [b for b in surface if b != ALL_PRICES]):
        sel = np.isfinite(px) & (px >= b[0]) & (px < b[1])
        if sel.any():
            out[sel] = null_for_hold(surface[b], hold_days)
    return out


def null_for_trades(surface: dict, entry_prices, hold_days: float,
                    bands: list[tuple[float, float]] | None = None) -> float:
    """
    The null for a strategy that bought *these* stocks at *these* prices.

    Each trade is charged the null of the price band it entered in, and the
    result is the trade-weighted average. A strategy that only buys sub-$10 names
    is therefore measured against sub-$10 names — which is the whole correction.
    Falls back to the market-wide curve when no prices are available.
    """
    if not surface:
        return 0.0
    vec = null_vector(surface, entry_prices, hold_days, bands)
    if vec.size == 0:
        return null_for_hold(surface.get(ALL_PRICES, {}), hold_days)
    return float(np.mean(vec))


def report(conn, cfg: dict) -> None:
    lab = cfg["lab"]
    windows = [
        (lab["search_start"], lab["search_end"], "search"),
        (lab["validation_start"], lab["validation_end"], "validation"),
        (lab["sealed_start"], "2099-12-31", "sealed"),
    ]
    bands = price_bands(cfg)
    for a, b, label in windows:
        surface = null_surface(conn, cfg, (a, b))
        print(f"\n  {label}  {a} -> {b}   net null %, by entry price and holding period")
        print(f"  {'price band':<18}" + "".join(f"{h:>9}d" for h in (2, 5, 13, 21, 45)))
        print("  " + "-" * 68)
        for band in bands + [ALL_PRICES]:
            name = ("whole market" if band == ALL_PRICES else
                    f"${band[0]:,.0f}-${band[1]:,.0f}" if band[1] < PRICE_CEIL
                    else f"${band[0]:,.0f}+")
            cells = "".join(f"{null_for_hold(surface[band], h):>+9.3f} " for h in (2, 5, 13, 21, 45))
            print(f"  {name:<18}{cells}")
    print("\n  A strategy is charged the null of the stocks it actually bought.")
    print("  Beating zero only demonstrates it was long in a rising market;")
    print("  beating the market-wide null can still just mean it bought cheap stocks.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    init(conn)
    if args.refresh:
        lab = cfg["lab"]
        for a, b in [(lab["search_start"], lab["search_end"]),
                     (lab["validation_start"], lab["validation_end"]),
                     (lab["sealed_start"], "2099-12-31")]:
            null_surface(conn, cfg, (a, b), refresh=True)
    report(conn, cfg)
    conn.close()


if __name__ == "__main__":
    main()
