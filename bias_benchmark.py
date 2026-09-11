"""
Puts a number on our survivorship bias, in percent per year, using free data.

`reconstruct_universe.py` measures how many companies are missing. It cannot say
what their absence is worth, because we have no prices for them. This does.

Ken French's 48 Industry Portfolios are built from CRSP, which includes delisted
firms — so those series are survivorship-bias free. Reconstructing an
equal-weighted market return from them and comparing it against the same measure
computed on our own survivor-only database gives the bias directly, measured on
our data rather than borrowed from a paper.

Method:
  1. French publishes equal-weighted monthly returns per industry, and the number
     of firms in each. Sum(n_i * r_i) / Sum(n_i) reconstructs the equal-weighted
     market return across all CRSP stocks — the bias-free benchmark.
  2. The same equal-weighted monthly return is computed from our `prices` table
     over currently-listed common stock.
  3. The difference is what survivorship is worth to us per year.

What the number includes: survivorship, plus composition differences — CRSP
covers microcaps and OTC names our directory-built universe never had. It is
therefore an upper bound on survivorship alone, and should be read as "our
universe's returns are overstated by at most this much".

Source: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/
Free for research use. No account, no purchase.

Usage:
    python bias_benchmark.py              # download if needed, then report
    python bias_benchmark.py --start 2008 # restrict the comparison window
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bias_benchmark")

FF_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
          "48_Industry_Portfolios_CSV.zip")
EW_HEADER = "Average Equal Weighted Returns -- Monthly"
NFIRMS_HEADER = "Number of Firms in Portfolios"
MISSING = (-99.99, -999.0)


def download(cache: Path) -> Path:
    """Fetch the French archive once and keep it. It is ~470 KB and rarely changes."""
    cache.mkdir(parents=True, exist_ok=True)
    csv_path = cache / "48_Industry_Portfolios.csv"
    if csv_path.exists():
        return csv_path
    log.info("Downloading Ken French 48 Industry Portfolios...")
    resp = requests.get(FF_URL, timeout=120,
                        headers={"User-Agent": "stockbot2000 research"})
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        csv_path.write_bytes(z.read(name))
    log.info(f"Saved {csv_path}")
    return csv_path


def _section(lines: list[str], header: str) -> pd.DataFrame:
    """
    Extract one labelled block from French's multi-section CSV.

    The file stacks several tables in one CSV separated by prose headers, so it
    cannot be read with a single `read_csv`. Each block runs from its header to
    the next blank line followed by a non-numeric row.
    """
    start = next(i for i, l in enumerate(lines) if header in l)
    cols = [c.strip() for c in lines[start + 1].split(",")][1:]
    rows = []
    for line in lines[start + 2:]:
        parts = [p.strip() for p in line.split(",")]
        if not parts[0].isdigit() or len(parts[0]) != 6:
            if rows:
                break
            continue
        rows.append([parts[0]] + [float(x) for x in parts[1:]])
    df = pd.DataFrame(rows, columns=["ym"] + cols)
    df["ym"] = df["ym"].str[:4] + "-" + df["ym"].str[4:]
    return df.set_index("ym")


def french_ew_market(csv_path: Path) -> pd.Series:
    """
    Equal-weighted market return per month, reconstructed from the 48 industries.

    French publishes equal-weighted returns per industry but no equal-weighted
    market series. Weighting each industry by its firm count recovers one, since
    an equal-weighted average of equal-weighted industry portfolios is not the
    equal-weighted market unless industry sizes are accounted for.
    """
    lines = Path(csv_path).read_text(encoding="latin-1").splitlines()
    ret = _section(lines, EW_HEADER)
    nfirms = _section(lines, NFIRMS_HEADER)

    common = ret.index.intersection(nfirms.index)
    ret, nfirms = ret.loc[common], nfirms.loc[common]

    valid = ~ret.isin(MISSING) & (nfirms > 0)
    weighted = (ret.where(valid, 0) * nfirms.where(valid, 0)).sum(axis=1)
    counts = nfirms.where(valid, 0).sum(axis=1)
    out = (weighted / counts).replace([float("inf"), float("-inf")], pd.NA).dropna()
    out.name = "french_ew"
    return out / 100.0


def our_ew_market(config: dict, start: str) -> pd.Series:
    """
    The same measure over our own database: equal-weighted monthly return across
    currently-listed common stock.

    Month-end closes come from a window function rather than a correlated
    subquery — at 35M rows the latter is unusably slow.
    """
    conn = storage.connect(config["database"]["market_data_path"])
    types = config["universe"]["tradeable_types"]
    ph = ",".join("?" * len(types))
    sql = f"""
        SELECT ticker, ym, close FROM (
            SELECT ticker, substr(date, 1, 7) AS ym, close,
                   ROW_NUMBER() OVER (PARTITION BY ticker, substr(date, 1, 7)
                                      ORDER BY date DESC) AS rn
            FROM prices
            WHERE date >= ?
              AND ticker IN (SELECT ticker FROM symbols WHERE security_type IN ({ph})
                             AND data_quality IS NULL)
        ) WHERE rn = 1
    """
    log.info("Computing month-end closes from the prices table...")
    df = pd.read_sql_query(sql, conn, params=[f"{start}-01-01", *types])
    conn.close()
    log.info(f"  {len(df):,} ticker-months across {df['ticker'].nunique():,} tickers")

    df = df.sort_values(["ticker", "ym"])
    df["ret"] = df.groupby("ticker", observed=True)["close"].pct_change()
    # A month is only comparable if the prior month exists for that ticker; the
    # first observation of every ticker is dropped by pct_change, which is what we
    # want — a new listing is not a return.
    out = df.dropna(subset=["ret"]).groupby("ym")["ret"].mean()
    out.name = "ours_ew"
    return out


def annualise(monthly: pd.Series) -> float:
    """Compound a monthly return series to an annual rate."""
    return float((1 + monthly).prod() ** (12 / len(monthly)) - 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2006", help="First year to compare (default 2006).")
    args = parser.parse_args()

    config = load_config()
    runtime.be_nice()
    cache = Path(config["universe"].get("archive_cache_dir", "data/archive_snapshots")).parent / "french"

    french = french_ew_market(download(cache))
    ours = our_ew_market(config, args.start)

    both = pd.concat([ours, french], axis=1, join="inner").dropna()
    both = both[both.index >= f"{args.start}-01"]
    if both.empty:
        print("No overlapping months.")
        return

    print(f"\nEqual-weighted monthly returns, {both.index[0]} -> {both.index[-1]} "
          f"({len(both)} months)\n")
    print(f"{'year':<8}{'ours':>10}{'CRSP (bias-free)':>20}{'gap':>10}")
    print("-" * 48)
    for year, grp in both.groupby(both.index.str[:4]):
        a, b = annualise(grp["ours_ew"]), annualise(grp["french_ew"])
        print(f"{year:<8}{a:>9.1%}{b:>20.1%}{a - b:>10.1%}")

    a, b = annualise(both["ours_ew"]), annualise(both["french_ew"])
    print("-" * 48)
    print(f"{'ALL':<8}{a:>9.1%}{b:>20.1%}{a - b:>10.1%}")
    print(f"\nOur universe overstates equal-weighted returns by "
          f"{(a - b) * 100:.1f} percentage points a year.")
    print("Upper bound on survivorship: also includes CRSP microcap/OTC coverage\n"
          "our directory-built universe never had.")


if __name__ == "__main__":
    main()
