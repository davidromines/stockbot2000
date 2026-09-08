"""
Pulls daily OHLCV history for the full universe in batched calls via yfinance.
Saves one long-format parquet file: columns = [date, ticker, open, high, low, close, volume].

Run this daily (pre-market, via cron) to refresh data before scoring.
"""
import logging
import time

import pandas as pd
import yfinance as yf

from universe import load_config, get_universe

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("data_pull")

BATCH_SIZE = 50          # yfinance batch download size; keeps requests reasonable
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SEC = 5


def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def pull_batch(tickers: list[str], period_days: int, interval: str) -> pd.DataFrame:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            data = yf.download(
                tickers=tickers,
                period=f"{period_days}d",
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            return data
        except Exception as e:
            log.warning(f"Batch pull failed (attempt {attempt}/{RETRY_ATTEMPTS}): {e}")
            time.sleep(RETRY_BACKOFF_SEC * attempt)
    log.error(f"Giving up on batch: {tickers}")
    return pd.DataFrame()


def reshape_to_long(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """yfinance multi-ticker download returns wide/multiindex columns; convert to long format."""
    frames = []
    for t in tickers:
        try:
            sub = raw[t].copy() if len(tickers) > 1 else raw.copy()
        except (KeyError, TypeError):
            continue
        if sub.empty:
            continue
        sub = sub.reset_index()
        sub["ticker"] = t
        sub.columns = [c.lower() if isinstance(c, str) else c for c in sub.columns]
        frames.append(sub)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main():
    cfg = load_config()
    tickers = get_universe(cfg)
    period_days = cfg["data"]["lookback_days"]
    interval = cfg["data"]["interval"]

    all_long = []
    for i, batch in enumerate(chunked(tickers, BATCH_SIZE)):
        log.info(f"Pulling batch {i + 1} ({len(batch)} tickers)...")
        raw = pull_batch(batch, period_days, interval)
        if raw.empty:
            continue
        long_df = reshape_to_long(raw, batch)
        all_long.append(long_df)

    if not all_long:
        log.error("No data pulled at all. Aborting.")
        return

    full = pd.concat(all_long, ignore_index=True)
    full = full.dropna(subset=["close"])
    out_path = cfg["data"]["history_file"]
    full.to_parquet(out_path, index=False)
    log.info(f"Saved {len(full)} rows across {full['ticker'].nunique()} tickers to {out_path}")


if __name__ == "__main__":
    main()
