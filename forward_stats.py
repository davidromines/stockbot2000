"""
Statistics for forward-trading results, shared by funnel.py and audit_forward.py (Addendum F, A3-A4).

Pure functions, no database. The point of the module: a trade-level t-statistic assumes the trades are
independent, and forward paper trades are not (many funds take the same ticker on the same date, and a
single market move drives a whole day's entries). So every family is also measured with errors clustered
by entry date and by ticker, a date-block bootstrap, a design effect / effective n, and a comparison with
the level that luck alone reaches among N independent tests.
"""
import math
from statistics import NormalDist

import numpy as np
import pandas as pd

N_LUCK = {"88 families": 88, "1,405 specs": 1405, "127,652 Lab structures": 127652}
CA_THRESHOLD = 0.015         # |recorded close / adjusted close on that date - 1| above this = adjusted since the trade
MIN_DATE_CLUSTERS = 20       # fewer independent entry dates than this cannot support a label above 'unresolved'
BOOT = 4000
SEED = 20261013


def iid_stats(x) -> dict:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return {"n": n, "mean": float(x.mean()) if n else float("nan"), "sd": float("nan"), "t": float("nan")}
    sd = float(x.std(ddof=1))
    se = sd / math.sqrt(n)
    return {"n": n, "mean": float(x.mean()), "sd": sd, "se": se, "t": float(x.mean() / se) if se else float("nan")}


def cluster_stats(x, groups) -> dict:
    """CR1 cluster-robust standard error of a mean; t with G-1 degrees of freedom noted."""
    x = np.asarray(x, dtype=float)
    g = pd.Series(groups).reset_index(drop=True)
    n = len(x)
    G = g.nunique()
    m = x.mean()
    s = pd.Series(x - m).groupby(g).sum()
    var = (G / (G - 1)) * float((s ** 2).sum()) / (n ** 2) if G > 1 else float("nan")
    se = math.sqrt(var) if var == var and var > 0 else float("nan")
    return {"clusters": int(G), "se": se, "t": float(m / se) if se == se and se else float("nan")}


def dedupe(df: pd.DataFrame, keys=("ticker", "entry_date")) -> pd.DataFrame:
    """One observation per key: mean return over every fund that took it, plus how many did."""
    return df.groupby(list(keys), as_index=False).agg(pnl_pct=("pnl_pct", "mean"), funds=("run_id", "nunique"),
                                                       rows=("pnl_pct", "size"))


def bootstrap_by_cluster(x, groups, reps=BOOT, seed=SEED) -> dict:
    """Resample whole clusters (entry dates) with replacement; interval for the mean and P(mean <= 0)."""
    x = np.asarray(x, dtype=float)
    g = pd.Series(groups).reset_index(drop=True)
    sums = pd.Series(x).groupby(g).sum().to_numpy()
    cnts = pd.Series(x).groupby(g).size().to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(reps, len(sums)))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return {"lo": float(np.percentile(means, 2.5)), "hi": float(np.percentile(means, 97.5)),
            "p_le_zero": float((means <= 0).mean())}


def luck_threshold(n_tests: int, level: float = 0.95) -> float:
    """t that the maximum of n_tests independent standard-normal statistics exceeds with prob 1 - level."""
    return NormalDist().inv_cdf(level ** (1.0 / n_tests))


def classify(t_cluster: float, ci_lo: float, date_clusters: int) -> str:
    """Mechanical, provisional. Never returns an 'eligible' or 'supported' label: that needs a human."""
    if not (t_cluster == t_cluster):
        return "Unresolved (cannot compute)"
    if date_clusters < MIN_DATE_CLUSTERS:
        return f"Unresolved: only {date_clusters} independent entry dates (need {MIN_DATE_CLUSTERS}+)"
    if t_cluster < 2.0 or ci_lo <= 0:
        return "Unresolved: not significant after the dependence correction"
    if t_cluster < luck_threshold(88):
        return "Unresolved: significant, but inside the range luck produces among 88 families"
    return "Promising but unproven: survives dependence and the 88-family luck bar"


def fill_basis_sql(conn, alias: str = "t") -> str:
    """SQL selecting a paper trade's `fill_basis` (the ENTRY leg: NULL = 'close') and `exit_basis` ('next_open' when the
    exit was filled at an open, `exit_fill_date` set; else 'close'). Constants where paper_trading.init has not added
    the columns yet — a reader of an older table must not fail because the engine has not run. A trade opened before
    2026-10-20 and closed after it is mixed: a close entry and a next-open exit."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(paper_trades)")}
    e = f"COALESCE({alias}.fill_basis, 'close')" if "fill_basis" in have else "'close'"
    x = (f"CASE WHEN {alias}.exit_fill_date IS NOT NULL THEN 'next_open' ELSE 'close' END"
         if "exit_fill_date" in have else "'close'")
    return f"{e} AS fill_basis, {x} AS exit_basis"


def corporate_action_flag(df: pd.DataFrame, thr: float = CA_THRESHOLD) -> pd.Series:
    """The engine records the price it paid; the prices table is back-adjusted later. A gap means an adjustment.
    A close fill paid the close of its decision date; a next-open fill (`fill_basis` 'next_open', Stage AD item 3)
    paid the open of the session after it, so it is compared with that open — against the decision-day close every
    overnight gap above the threshold would read as a corporate action."""
    ce, cx = df["close_entry"], df["close_exit"]
    if "fill_basis" in df.columns and {"open_next_entry", "open_next_exit"} <= set(df.columns):
        nxt = df["fill_basis"].eq("next_open")
        nxt_x = df["exit_basis"].eq("next_open") if "exit_basis" in df.columns else nxt     # per leg (mixed rows)
        ce, cx = ce.where(~nxt, df["open_next_entry"]), cx.where(~nxt_x, df["open_next_exit"])
    re = (df["entry_price"] / ce - 1).abs()
    rx = (df["exit_price"] / cx - 1).abs()
    return ((re > thr) | (rx > thr)).fillna(False)




# --- multiple testing across families (Addendum F, A4) -----------------------------------
def t_pvalue_one_sided(t: float, df: float) -> float:
    """P(T >= t) for a Student t with df degrees of freedom (df = independent entry dates - 1)."""
    from scipy import stats
    return float(stats.t.sf(t, df)) if t == t and df and df > 0 else float("nan")


def holm(p: list) -> list:
    """Holm step-down adjusted p-values; NaN stays NaN and is not counted."""
    idx = [i for i, x in enumerate(p) if x == x]
    order = sorted(idx, key=lambda i: p[i])
    m = len(order)
    out = [float("nan")] * len(p)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * p[i]))
        out[i] = run
    return out


def benjamini_hochberg(p: list) -> list:
    """BH q-values (false-discovery-rate adjusted p-values)."""
    idx = [i for i, x in enumerate(p) if x == x]
    order = sorted(idx, key=lambda i: p[i], reverse=True)
    m = len(idx)
    out = [float("nan")] * len(p)
    prev = 1.0
    for k, i in enumerate(order):
        rank = m - k
        prev = min(prev, p[i] * m / rank)
        out[i] = min(1.0, prev)
    return out


def nyholt_meff(corr) -> float:
    """Effective number of independent tests from a correlation matrix (Nyholt 2004 eigenvalue form)."""
    c = np.asarray(corr, dtype=float)
    m = c.shape[0]
    if m < 2:
        return float(m)
    ev = np.linalg.eigvalsh(np.nan_to_num(c, nan=0.0))
    return float(1 + (m - 1) * (1 - np.var(ev, ddof=1) / m))


def maxt_signflip(date_means: pd.DataFrame, reps: int = 20000, seed: int = SEED, min_dates: int = 3) -> pd.DataFrame:
    """
    Westfall-Young style max-T test across families, with the same random sign applied to a date for every family
    (so cross-family dependence is preserved). `date_means`: index = entry dates, columns = families, NaN where a
    family has no trades that date. Statistic per family: one-sample t of its date means. Null: date means are
    symmetric about zero. Returns observed t, the family's own sign-flip p, and the max-T adjusted p, one-sided
    (large positive t). Absolute-return nulls are rejected by a market drift: use an excess return for edge claims.
    """
    X = date_means.to_numpy(dtype=float)
    M = ~np.isnan(X)
    X = np.nan_to_num(X, nan=0.0)
    n = M.sum(axis=0).astype(float)
    sumsq = (X ** 2).sum(axis=0)
    ok = n >= min_dates

    def tstat(s):
        mean = s / np.where(n > 0, n, 1)
        var = (sumsq - n * mean ** 2) / np.where(n > 1, n - 1, 1)
        se = np.sqrt(np.where(var > 0, var, np.nan) / np.where(n > 0, n, 1))
        return mean / se

    obs = tstat(X.sum(axis=0))
    rng = np.random.default_rng(seed)
    exceed_own = np.zeros(X.shape[1])
    exceed_max = np.zeros(X.shape[1])
    done = 0
    while done < reps:
        b = min(2000, reps - done)
        S = rng.choice([-1.0, 1.0], size=(b, X.shape[0]))
        tt = tstat(S @ X)                                   # b x F
        tt = np.where(ok[None, :], tt, -np.inf)
        mx = np.nanmax(tt, axis=1)
        exceed_own += (np.nan_to_num(tt, nan=-np.inf) >= np.where(ok, obs, np.inf)[None, :]).sum(axis=0)
        exceed_max += (mx[:, None] >= np.where(ok, obs, np.inf)[None, :]).sum(axis=0)
        done += b
    out = pd.DataFrame({"t": obs, "dates": n.astype(int), "p_own": (exceed_own + 1) / (reps + 1),
                        "p_maxT": (exceed_max + 1) / (reps + 1)}, index=date_means.columns)
    out.loc[~ok, ["p_own", "p_maxT"]] = np.nan
    return out
