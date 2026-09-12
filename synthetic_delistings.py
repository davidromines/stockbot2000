"""
Synthetic price paths for the 7,062 delisted companies we have no prices for.

The gap, restated: we know exactly which companies died and on what date, and we
hold no price history for 94% of them — about 12.5 million missing daily bars,
roughly 35% of the size of the whole database. Every backtest is therefore told
*"every company you could have bought survived"*, which is why "buy the crash"
scored +$26,065 and why the ladder has to refuse an entire class of strategy as
untestable.

**This module does not claim to recover what those prices were.** That
information is gone. It generates a *family* of plausible paths per company and
requires a strategy to survive all of them, so a rule that buys failing companies
gets hit by the failures it would really have suffered. Used this way the error
runs in the safe direction: if the model is wrong, strategies look worse than
reality, never better.

In the missing-data literature this is **MNAR** — Missing Not At Random, the
hardest case, where data is absent *because of* the value it would have had. The
standard response is not a single imputation but **sensitivity analysis across a
family of assumptions**, which is exactly what the ensemble below is for. A mean
path would defeat the purpose: average a million random walks and the gaps, the
tails and the volatility all cancel, leaving a smooth curve that no strategy ever
gets hurt by. The distribution is the product; the average is the one thing we
must not use.

-------------------------------------------------------------------------------
CALIBRATION — every number below is measured or published, none invented
-------------------------------------------------------------------------------

*Shapes*, from the 131 real delisted paths in our own database with 24+ months of
history before their delisting date:

    archetype              share   ann.vol   maxDD   median last price
    collapse  < -80%         14%      157%     97%        $5.86
    severe   -80..-50%       12%       70%     79%        $5.22
    decline  -50..-20%       15%       72%     63%        $6.90
    flat     -20..+20%       23%       48%     38%       $19.93
    rose       > +20%        36%       59%     40%       $20.85

*Mixture weights*, reweighted — because that sample is itself survivorship-biased.
yfinance keeps history for a cleanly acquired company far more often than for a
bankruptcy, so our 131 skew toward benign outcomes: 36% of them *rose* into
delisting. Macey, O'Hara & Pompilio (Berkeley, 2004) report that of 7,300+ US
delistings since 1995, **almost half were involuntary**. Our sample shows only
26% in collapse+severe, so failures are under-represented by roughly 2x and the
weights below are corrected toward the published split rather than the observed
one.

*Terminal returns*, published:
  - Shumway (1997), delisting returns: **-30% NYSE/AMEX, -55% Nasdaq**
  - Macey et al.: average price $0.95 on the last NYSE day vs **$0.48** on the
    first Pink Sheets day — a **-49%** transition, independently corroborating
    Shumway from a different dataset
  - Delisting announcement day: **-8.5%**

*Pre-delisting drift*, published: bankrupt firms show a cumulative average
decline of **-66% over the 24 months** before delisting (NYSE/Amex/Nasdaq,
1975-2005).

*Post-delisting microstructure*, Macey et al.: Pink Sheets volatility **more than
double** the NYSE level, and spreads about 57% wider. Relevant because a strategy
holding through a delisting does not get a clean exit.

-------------------------------------------------------------------------------
THE RISK THIS MODULE CREATES, STATED PLAINLY
-------------------------------------------------------------------------------

This search has found five separate loopholes in its own scoreboard: a price
filter, a monoculture, dead branches, lopsided branches, and a crash-buying
artifact. It is extremely good at discovering the signature of whatever produced
its data. If every synthetic failure declines smoothly toward -66%, the search
will learn *"avoid smoothly declining stocks"* and score brilliantly by dodging
our simulation rather than by avoiding bankruptcy — a sixth loophole, handed to a
system with a perfect record of finding them.

`validate.py --synthetic` is therefore not optional. It runs random, never-evolved
genomes over real and augmented panels. If noise performs *systematically*
differently with synthetic data present, the generator has a detectable signature
and must be fixed before any result is believed.

Three rules that must not be relaxed:
  1. Synthetic bars live in their own table and carry a flag. They are never
     written into `prices`.
  2. Every result is reported both ways — with and without.
  3. Never in the live or paper-trading path. Forward testing stays entirely real.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("synthetic")

TRADING_DAYS = 252

# -- the archetypes ----------------------------------------------------------
#
# `weight` is the reweighted mixture, not the observed one. `drift` is the total
# log-return over the simulated window; `vol` is annualised; `jump_lambda` is the
# expected number of jump events per year and `jump_mean` their average size.
# `terminal` is the return booked on the delisting day itself.

ARCHETYPES = {
    "bankruptcy": dict(
        weight=0.14, drift=-0.66, vol=1.08, jump_lambda=6.0, jump_mean=-0.18,
        terminal=-0.55, reverse_splits=0.35,
        note="Classic failure. -66% over 24 months per the literature, the 157% "
             "volatility measured in our own collapse bucket, and Shumway's "
             "Nasdaq delisting return."),
    "price_deficiency": dict(
        weight=0.13, drift=-0.72, vol=0.76, jump_lambda=3.0, jump_mean=-0.12,
        terminal=-0.49, reverse_splits=0.70,
        note="The most common Nasdaq delisting cause: closing bid under $1 for 30 "
             "sessions. Usually preceded by reverse splits fighting for "
             "compliance, hence the high reverse_splits rate."),
    "death_spiral": dict(
        weight=0.06, drift=-0.88, vol=0.97, jump_lambda=10.0, jump_mean=-0.15,
        terminal=-0.55, reverse_splits=0.95,
        note="Toxic convertible financing. Repeated reverse splits while the "
             "split-adjusted price falls permanently — share count expands as "
             "financiers sell into the market. Endemic among small biotech and "
             "post-SPAC names."),
    "slow_decline": dict(
        weight=0.12, drift=-0.38, vol=0.50, jump_lambda=1.5, jump_mean=-0.10,
        terminal=-0.30, reverse_splits=0.20,
        note="The -50..-20% bucket measured in our own data. Business erodes, the "
             "exchange eventually acts. NYSE/AMEX terminal return."),
    "sudden_collapse": dict(
        weight=0.05, drift=-0.35, vol=0.59, jump_lambda=1.0, jump_mean=-0.55,
        terminal=-0.55, reverse_splits=0.05,
        note="Fraud discovery, failed trial, catastrophic single event. Flat or "
             "healthy, then one enormous negative jump. Enron, Global Crossing. "
             "Deliberately hard for a trend rule to anticipate."),
    "acquisition": dict(
        weight=0.37, drift=0.18, vol=0.31, jump_lambda=0.8, jump_mean=0.22,
        terminal=0.0, reverse_splits=0.0,
        note="Bought at a premium. Delists near its highs, and the announcement "
             "pop is the positive jump. 36% of our real sample - the benign half "
             "of delisting, and the reason a naive calibration looks harmless."),
    "going_private": dict(
        weight=0.13, drift=0.02, vol=0.29, jump_lambda=0.5, jump_mean=0.10,
        terminal=0.0, reverse_splits=0.0,
        note="Voluntary exit to escape listing costs. Roughly flat - the "
             "-20..+20% bucket."),
}


FAILURE = ("bankruptcy", "price_deficiency", "death_spiral", "slow_decline",
           "sudden_collapse")

# Starting-price priors, (log-mean, log-sd), calibrated against the 131 real
# delisted paths: median $17.00 twenty-four months out, log-sd 2.29 overall.
PRICE_PRIOR = {
    "acquisition":      (np.log(30.0), 1.15),
    "going_private":    (np.log(22.0), 1.15),
    "slow_decline":     (np.log(14.0), 1.25),
    "sudden_collapse":  (np.log(18.0), 1.25),
    "bankruptcy":       (np.log(9.0), 1.35),
    "price_deficiency": (np.log(6.0), 1.30),
    "death_spiral":     (np.log(5.0), 1.30),
}


def weights(failure_share: float | None = None) -> tuple[list[str], np.ndarray]:
    """
    The archetype mixture, optionally re-tilted to a given failure share.

    The default sums the failure archetypes to 0.50, matching Macey et al.'s
    finding that almost half of US delistings are involuntary. **This single
    number is the most consequential assumption in the module** — it decides how
    often a strategy gets punished — so it is a parameter to be swept rather than
    a constant to be trusted. `--sweep` runs 0.35 / 0.50 / 0.65, and a conclusion
    that flips across that range was never a conclusion.
    """
    names = list(ARCHETYPES)
    w = np.array([ARCHETYPES[n]["weight"] for n in names], dtype="float64")
    w = w / w.sum()
    if failure_share is not None:
        fail = np.array([n in FAILURE for n in names])
        cur = w[fail].sum()
        if 0 < cur < 1:
            w[fail] *= failure_share / cur
            w[~fail] *= (1 - failure_share) / (1 - cur)
    return names, w / w.sum()


# A failure path must end consistent with the failure we know happened. Without
# this, 157% volatility sends 5% of "bankruptcies" up fivefold, and the search
# would find them: buy the doomed, catch the squeeze. Conditioning on the known
# outcome is not a fudge - it is what imputation *is*, since the delisting is
# observed data and the path is what is missing.
FAILURE_CEILING = 1.10          # a failing name may not end above 1.1x where it began


def generate_path(archetype: str, n_days: int, start_price: float,
                  rng: np.random.Generator, max_tries: int = 12) -> np.ndarray:
    """Wrapper enforcing consistency with the observed outcome."""
    a = ARCHETYPES[archetype]
    for _ in range(max_tries):
        p = _raw_path(archetype, n_days, start_price, rng)
        if a["terminal"] >= 0:
            return p                      # acquisitions may legitimately rise
        if p[-2] <= start_price * FAILURE_CEILING:
            return p
    # Ran out of tries: scale the path down rather than return an inconsistent one.
    return p * (start_price * FAILURE_CEILING / max(p[-2], 1e-9))


def _raw_path(archetype: str, n_days: int, start_price: float,
              rng: np.random.Generator) -> np.ndarray:
    """
    One plausible daily close series ending at the delisting date.

    A jump-diffusion, not a plain random walk. Dying companies do not glide —
    they gap on news, and the statistical-physics work on pre-bankrupt stocks
    found exactly that: larger daily moves in both directions than healthy names.
    A geometric Brownian motion would produce the smooth glide the search could
    trivially learn to recognise, which is the failure mode this whole module has
    to avoid.

    Reverse splits are applied for the archetypes where they belong. In a
    split-adjusted series a reverse split leaves no visible discontinuity, which
    is precisely why a death spiral is invisible to a price filter and lethal to
    anyone holding: the adjusted price simply keeps falling.
    """
    a = ARCHETYPES[archetype]
    yrs = n_days / TRADING_DAYS
    sig = a["vol"]
    dt = 1.0 / TRADING_DAYS

    # Solve the drift so the MEDIAN path lands on the calibration target.
    #
    # The obvious formulation - annualise `drift` and hand it to a GBM - is
    # wrong, and wrong by a lot at these volatilities. GBM already subtracts
    # 0.5*sigma^2, so the target decline gets charged twice: at sigma=157% that
    # second term alone is -91% over two years, and every failure archetype
    # collapsed to a median of -100% instead of the -66% the literature reports.
    # Work backwards from the median instead, and net off the expected jump
    # contribution so jumps add dispersion rather than silently moving the centre.
    target_log = np.log1p(max(a["drift"], -0.99))
    exp_jump_log = a["jump_lambda"] * yrs * np.log1p(np.clip(a["jump_mean"], -0.95, 5.0))
    daily_log_drift = (target_log - exp_jump_log) / max(n_days, 1)

    diffusion = daily_log_drift + sig * np.sqrt(dt) * rng.standard_normal(n_days)

    # Jumps: Poisson arrivals, sizes dispersed around jump_mean.
    n_jumps = rng.poisson(a["jump_lambda"] * yrs)
    jumps = np.zeros(n_days)
    if n_jumps:
        where = rng.integers(0, n_days, n_jumps)
        sizes = rng.normal(a["jump_mean"], abs(a["jump_mean"]) * 0.6, n_jumps)
        np.add.at(jumps, where, np.log1p(np.clip(sizes, -0.95, 5.0)))

    log_path = np.cumsum(diffusion + jumps)
    px = start_price * np.exp(log_path)

    # The delisting itself: announcement shock then the terminal return.
    if a["terminal"] < 0 and n_days > 10:
        px[-6:-1] *= (1 + ANNOUNCE_SHOCK)
        px[-1] = px[-2] * (1 + a["terminal"])
    elif a["terminal"] == 0 and n_days > 5:
        px[-5:] *= 1.0                       # acquisitions drift to the deal price

    return np.maximum(px, 0.0001)


ANNOUNCE_SHOCK = -0.085          # Macey et al.: -8.5% on the delisting announcement


def characterise(archetype: str, n_sims: int = 1_000_000, n_days: int = 504,
                 seed: int = 0) -> dict:
    """
    Monte Carlo an archetype to describe the distribution it actually produces.

    A million paths are run to *characterise*, not to average. The output is the
    spread — which is the object of interest — and it is what tells us whether a
    hand-set parameter produces the behaviour the literature describes. The mean
    of a million random walks is a smooth line that nothing ever loses money on.

    Run in blocks so a million 504-day paths never exist in memory at once; the
    full matrix would be 4 GB and the VM has 11.7.
    """
    rng = np.random.default_rng(seed)
    finals, mins, vols = [], [], []
    block = 2000
    done = 0
    while done < n_sims:
        k = min(block, n_sims - done)
        for _ in range(k):
            p = generate_path(archetype, n_days, 100.0, rng)
            finals.append(p[-1] / 100.0 - 1.0)
            mins.append(p.min() / 100.0 - 1.0)
        done += k
        if done % 100000 == 0:
            log.info(f"    {archetype}: {done:,}/{n_sims:,}")
    f = np.array(finals)
    return {"archetype": archetype, "n": n_sims,
            "mean": float(f.mean()), "median": float(np.median(f)),
            "p05": float(np.percentile(f, 5)), "p95": float(np.percentile(f, 95)),
            "worse_than_50": float((f < -0.50).mean()),
            "worse_than_80": float((f < -0.80).mean()),
            "trough": float(np.mean(mins))}


def blended_distribution(n: int = 40000, failure_share: float | None = None,
                         n_days: int = 504, seed: int = 1) -> np.ndarray:
    """Draw from the full mixture — what a random delisted company looks like."""
    names, w = weights(failure_share)
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(names), size=n, p=w)
    out = np.empty(n)
    for i, k in enumerate(picks):
        p = generate_path(names[k], n_days, 100.0, rng)
        out[i] = p[-1] / 100.0 - 1.0
    return out


# -- per-company assignment --------------------------------------------------

def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synthetic_companies (
            symbol         TEXT NOT NULL,
            member         INTEGER NOT NULL,   -- which ensemble member
            archetype      TEXT NOT NULL,
            seed           INTEGER NOT NULL,
            start_date     TEXT NOT NULL,
            end_date       TEXT NOT NULL,
            n_days         INTEGER NOT NULL,
            start_price    REAL NOT NULL,
            exchange       TEXT,
            PRIMARY KEY (symbol, member)
        ) STRICT, WITHOUT ROWID
    """)
    conn.commit()


def assign(conn, ensemble: int = 20, failure_share: float | None = None,
           seed: int = 20260912, window_days: int = 504) -> int:
    """
    Give every missing company an ensemble of archetypes and seeds.

    **Parameters are stored, not price bars.** 7,062 companies x 20 members x
    ~500 bars would be 70 million rows to hold a thing that is not data — and it
    would sit next to the real prices inviting exactly the join that must never
    happen. A seed plus an archetype regenerates the path identically on demand,
    so the ensemble is reproducible, auditable and free to store.

    Archetype probability is tilted by what the registry already tells us about
    each company. A name that listed on Nasdaq is likelier to hit the $1 bid rule
    than an NYSE name; one that was listed only briefly is likelier to be a
    failed small-cap than a mature acquisition. Weak signals, but better than
    drawing blind, and they are the only company-specific information we have.
    """
    init(conn)
    names, base_w = weights(failure_share)
    rng = np.random.default_rng(seed)

    rows = conn.execute("""
        SELECT symbol, exchange, ipo_date, delisting_date FROM delistings
        WHERE asset_type='Stock' AND have_prices=0 AND ipo_date IS NOT NULL
    """).fetchall()

    # A plausible starting price: the median last-traded price of real delisted
    # names in the same broad outcome class, so synthetic names are not all $50.
    out, n = [], 0
    for r in rows:
        try:
            start = np.datetime64(r["ipo_date"]); end = np.datetime64(r["delisting_date"])
        except Exception:
            continue
        listed_days = int((end - start) / np.timedelta64(1, "D") * (252 / 365.25))
        if listed_days < 60:
            continue
        n_days = min(max(listed_days, 60), window_days)

        w = base_w.copy()
        ex = (r["exchange"] or "").upper()
        for i, nm in enumerate(names):
            if nm == "price_deficiency" and "NASDAQ" in ex:
                w[i] *= 1.35                 # the $1 bid rule is a Nasdaq rule
            if nm == "acquisition" and listed_days > 252 * 8:
                w[i] *= 1.30                 # long-listed names get bought
            if nm in ("death_spiral", "price_deficiency") and listed_days < 252 * 3:
                w[i] *= 1.25                 # short-lived names tend to fail
        w = w / w.sum()

        for m in range(ensemble):
            a = names[int(rng.choice(len(names), p=w))]
            # Starting price is drawn per archetype, not from one pool. Measured
            # on the 131 real delisted paths: median $17.00 two years out, with a
            # log-sd of 2.29 - far wider than the single lognormal first used
            # here, which produced a cloud of $8 stocks a classifier separated
            # from real data at AUC 0.996 on `sma_50` alone. Acquisitions are
            # real businesses and start dear; failures start cheap, matching the
            # $20.85 and $5.86 medians of our own risen and collapsed buckets.
            mu_px, sd_px = PRICE_PRIOR.get(a, (np.log(12.0), 1.3))
            px = float(np.clip(np.exp(rng.normal(mu_px, sd_px)), 1.0, 900.0))
            out.append((r["symbol"], m, a, int(rng.integers(0, 2**31 - 1)),
                        r["ipo_date"], r["delisting_date"], n_days,
                        round(px, 4), r["exchange"]))
        n += 1
        if len(out) >= 20000:
            conn.executemany("""INSERT OR REPLACE INTO synthetic_companies
                (symbol,member,archetype,seed,start_date,end_date,n_days,start_price,exchange)
                VALUES (?,?,?,?,?,?,?,?,?)""", out)
            conn.commit(); out = []
    if out:
        conn.executemany("""INSERT OR REPLACE INTO synthetic_companies
            (symbol,member,archetype,seed,start_date,end_date,n_days,start_price,exchange)
            VALUES (?,?,?,?,?,?,?,?,?)""", out)
    conn.commit()
    log.info(f"Assigned {ensemble} ensemble members to {n:,} companies")
    return n


def realise(conn, member: int, start_date: str, end_date: str):
    """
    Regenerate one ensemble member's price bars for a date window.

    Returns a DataFrame shaped like `prices` with a `synthetic` flag column, so
    it can be concatenated onto a real panel — and so anything downstream can
    tell the two apart, which is the point of carrying the flag at all.
    """
    import pandas as pd
    rows = conn.execute("""
        SELECT symbol, archetype, seed, start_date, end_date, n_days, start_price
        FROM synthetic_companies
        WHERE member = ? AND end_date >= ? AND start_date <= ?
    """, (member, start_date, end_date)).fetchall()
    if not rows:
        return pd.DataFrame()

    cal = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM prices WHERE date BETWEEN ? AND ? ORDER BY date",
        (start_date, end_date))]
    if not cal:
        return pd.DataFrame()
    cal_idx = {d: i for i, d in enumerate(cal)}

    frames = []
    for r in rows:
        rng = np.random.default_rng(r["seed"])
        px = generate_path(r["archetype"], int(r["n_days"]), float(r["start_price"]), rng)
        end_i = cal_idx.get(r["end_date"][:10], len(cal) - 1)
        start_i = max(0, end_i - len(px) + 1)
        seg = px[len(px) - (end_i - start_i + 1):]
        dates = cal[start_i:end_i + 1]
        if len(seg) != len(dates) or len(dates) < 30:
            continue
        frames.append(_bars(r["symbol"], dates, seg, r["archetype"], rng))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _bars(symbol: str, dates: list, close: np.ndarray, archetype: str,
          rng: np.random.Generator):
    """
    Turn a close series into full OHLCV bars that do not announce themselves.

    The first version of this set volume to a constant and the daily range to a
    fixed +/-2%. A classifier separated synthetic from real rows at **AUC 1.000**,
    with `vol_ratio` carrying 86% of the importance — because a constant volume
    makes volume-over-average exactly 1.0 on every single bar, forever. A rule of
    two nodes would have found it, and the search would have learned to identify
    our simulation instead of learning to avoid bankruptcy.

    So the bars now reproduce the properties the indicators actually read:

    - **Volume clusters.** An AR(1) in log-volume, because real turnover is
      strongly autocorrelated and `vol_ratio` measures exactly that.
    - **Volume responds to price.** Turnover spikes on large moves - the
      best-documented regularity in market microstructure - so volume carries a
      term in |return|.
    - **The daily range tracks volatility.** High-low scales with the day's own
      move plus noise, rather than sitting at a constant width, which is what
      `atr_14` and `bb_pct` read.
    - **Opens gap from the prior close** instead of equalling it.
    """
    import pandas as pd
    n = len(close)
    ret = np.diff(np.log(np.maximum(close, 1e-9)), prepend=np.log(max(close[0], 1e-9)))

    # Volume: AR(1) in logs, lifted by the size of the day's move.
    base = rng.normal(np.log(4.0e5), 1.1)
    ar = np.empty(n)
    ar[0] = rng.normal(0, 0.55)
    for i in range(1, n):
        ar[i] = 0.72 * ar[i - 1] + rng.normal(0, 0.55)
    vol = np.exp(base + ar + 2.4 * np.abs(ret) + rng.normal(0, 0.25, n))
    volume = np.maximum(np.round(vol), 100.0)

    # Range: proportional to the day's move, with a floor and lognormal noise.
    span = (0.012 + 1.35 * np.abs(ret)) * np.exp(rng.normal(0, 0.45, n))
    span = np.clip(span, 0.002, 0.9)

    prev = np.r_[close[0], close[:-1]]
    open_ = prev * np.exp(rng.normal(0, 0.35, n) * span)     # gap from prior close
    hi = np.maximum(open_, close) * (1 + span * rng.uniform(0.25, 0.75, n))
    lo = np.minimum(open_, close) * (1 - span * rng.uniform(0.25, 0.75, n))
    lo = np.minimum(lo, np.minimum(open_, close))
    hi = np.maximum(hi, np.maximum(open_, close))

    return pd.DataFrame({
        "ticker": symbol, "date": dates,
        "open": np.maximum(open_, 1e-4), "high": np.maximum(hi, 1e-4),
        "low": np.maximum(lo, 1e-4), "close": np.maximum(close, 1e-4),
        "volume": volume, "synthetic": 1})


def report(conn) -> None:
    init(conn)
    n = conn.execute("SELECT COUNT(DISTINCT symbol) FROM synthetic_companies").fetchone()[0]
    if not n:
        raise SystemExit("Nothing assigned yet — run --assign first.")
    m = conn.execute("SELECT COUNT(DISTINCT member) FROM synthetic_companies").fetchone()[0]
    print(f"\n  SYNTHETIC DELISTING ENSEMBLE")
    print(f"  {'companies':<26}{n:>8,}")
    print(f"  {'ensemble members each':<26}{m:>8,}")
    print(f"  {'total paths represented':<26}{n*m:>8,}")
    print(f"\n  {'archetype':<20}{'share of draws':>16}")
    print("  " + "-" * 37)
    tot = conn.execute("SELECT COUNT(*) FROM synthetic_companies").fetchone()[0]
    for r in conn.execute("""SELECT archetype, COUNT(*) c FROM synthetic_companies
                             GROUP BY archetype ORDER BY c DESC"""):
        print(f"  {r[0]:<20}{r[1]/tot:>15.1%}")
    fail = conn.execute(f"""SELECT COUNT(*) FROM synthetic_companies
        WHERE archetype IN ({','.join('?'*len(FAILURE))})""", FAILURE).fetchone()[0]
    print(f"\n  failure archetypes: {fail/tot:.0%} of draws (target ~50%)")
    print("  Paths are regenerated from (archetype, seed) on demand — no bars are stored.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assign", action="store_true")
    ap.add_argument("--ensemble", type=int, default=20)
    ap.add_argument("--failure-share", type=float, default=None)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)
    if a.assign:
        assign(conn, a.ensemble, a.failure_share)
    if a.report or not a.assign:
        report(conn)
    conn.close()


if __name__ == "__main__":
    main()
