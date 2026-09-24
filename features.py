"""
Computes technical features per ticker from the raw OHLCV history.
Produces one row per (ticker, date) with the indicator set used by the model.

No third-party TA library required (pandas_ta was dropped — its `numba` pin
doesn't support newer Python versions and the project shouldn't be blocked
on that upstream lag). All indicators below are plain pandas/numpy.
"""
import runtime  # noqa: F401  — must precede numpy/pandas/xgboost
import logging
import numpy as np
import pandas as pd
from universe import load_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("features")


# --- Indicator helpers -------------------------------------------------

def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def roc(close: pd.Series, length: int = 10) -> pd.Series:
    return (close - close.shift(length)) / close.shift(length) * 100


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    atr_w = atr(high, low, close, length)
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_w
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_w
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / length, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bbands(close: pd.Series, length: int = 20, n_std: float = 2.0):
    mid = sma(close, length)
    std = close.rolling(length).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    return upper, lower


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_length: int = 14,
                smooth_k: int = 3, d_length: int = 3):
    lowest_low = low.rolling(k_length).min()
    highest_high = high.rolling(k_length).max()
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_length).mean()
    return k, d


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).cumsum()


def cci(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = sma(tp, length)
    mean_dev = tp.rolling(length).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mean_dev)


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    highest_high = high.rolling(length).max()
    lowest_low = low.rolling(length).min()
    return -100 * (highest_high - close) / (highest_high - lowest_low)


def chaikin_osc(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
                 fast: int = 3, slow: int = 10) -> pd.Series:
    mf_multiplier = ((close - low) - (high - close)) / (high - low)
    mf_multiplier = mf_multiplier.replace([np.inf, -np.inf], 0).fillna(0)
    adl = (mf_multiplier * volume).cumsum()
    return ema(adl, fast) - ema(adl, slow)


# --- Feature assembly ----------------------------------------------------

def compute_features_for_ticker(df: pd.DataFrame, min_rows: int = 210) -> pd.DataFrame:
    # min_rows: 210 for real tickers (enough history for the 200-day SMA etc.).
    # survivorship_backtest.py passes less for synthetic dead companies: a
    # short-lived failure is exactly the company a survivorship test needs, and
    # its long-window indicators simply stay NaN until they exist.
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < min_rows:
        return pd.DataFrame()

    high, low, close, volume = df["high"], df["low"], df["close"], df["volume"]

    df["sma_50"] = sma(close, 50)
    df["sma_200"] = sma(close, 200)
    df["rsi_14"] = rsi(close, 14)
    df["roc_10"] = roc(close, 10)
    df["adx_14"] = adx(high, low, close, 14)

    macd_line, macd_signal, macd_hist = macd(close)
    df["macd"] = macd_line
    df["macd_signal"] = macd_signal
    df["macd_hist"] = macd_hist

    bb_upper, bb_lower = bbands(close, 20)
    df["bb_upper"] = bb_upper
    df["bb_pct"] = (close - bb_lower) / (bb_upper - bb_lower)

    df["vol_sma_20"] = sma(volume, 20)
    df["vol_ratio"] = volume / df["vol_sma_20"]
    # Tradeability, not signal: average dollars traded per day over 20 sessions.
    # Kept out of FEATURE_COLS on purpose — see storage.LIQUIDITY_COLS.
    df["dollar_volume_20"] = close * df["vol_sma_20"]

    # --- Additional indicators (added after competitive-landscape review) ---
    df["atr_14"] = atr(high, low, close, 14)  # volatility -> feeds stop-loss sizing

    stoch_k, stoch_d = stochastic(high, low, close)
    df["stoch_k"] = stoch_k
    df["stoch_d"] = stoch_d

    df["obv"] = obv(close, volume)
    df["obv_sma_20"] = sma(df["obv"], 20)
    df["obv_rising"] = (df["obv"] > df["obv_sma_20"]).astype(int)  # confirms volume flow supports the trend

    df["cci_20"] = cci(high, low, close, 20)
    df["willr_14"] = williams_r(high, low, close, 14)
    df["chaikin_osc"] = chaikin_osc(high, low, close, volume)

    # -- position within the longer-run range -------------------------------
    #
    # Three additions (2026-09-13) that use only data already held and close
    # genuine gaps in what the search could see.
    #
    # `pct_of_52w_high` is proximity to the 52-week high, one of the better
    # documented momentum anomalies (George & Hwang, 2004): stocks near their
    # yearly high tend to keep outperforming, and the effect is distinct from
    # ordinary price momentum. The search previously had no way to express it —
    # the longest window available to it was a 50-day z-score, which is a fifth
    # of a year.
    #
    # `drawdown_200` is the mirror image: how far below the trailing 200-day peak
    # a name sits. `bias_exposure.py` has been computing exactly this to decide
    # which strategies are untestable, and it was never exposed to the search
    # itself — so the Lab could be judged on a variable it could not reference.
    #
    # Both are scale-free ratios rather than dollar levels, deliberately. Raw
    # price levels are what the search turned into `sma_200 < 8`, and a ratio
    # cannot be used as a price filter.
    # Liquidity on a usable scale. `dollar_volume_20` already exists and
    # `rank(dollar_volume_20)` already gave the search a cross-sectional size
    # percentile — but the raw column spans six orders of magnitude ($1M to
    # $50B), so any direct comparison against a constant is dominated by scale
    # rather than by meaning. The log is comparable across the whole universe.
    # This is a liquidity proxy, not market capitalisation: true market cap
    # needs shares outstanding, which this database does not hold.
    df["log_dollar_volume"] = np.log10(df["dollar_volume_20"].clip(lower=1.0))

    win_52w = 252
    roll_high = close.rolling(win_52w, min_periods=60).max()
    roll_low = close.rolling(win_52w, min_periods=60).min()
    df["pct_of_52w_high"] = close / roll_high
    df["pct_off_52w_low"] = (close - roll_low) / roll_low.replace(0, np.nan)
    peak_200 = close.rolling(200, min_periods=20).max()
    df["drawdown_200"] = 1.0 - (close / peak_200)

    # Derived binary/relative features (mirror the original indicator list)
    df["price_above_sma50"] = (close > df["sma_50"]).astype(int)
    df["price_above_sma200"] = (close > df["sma_200"]).astype(int)
    df["golden_cross"] = (df["sma_50"] > df["sma_200"]).astype(int)

    return df


def main():
    cfg = load_config()
    history = pd.read_parquet(cfg["data"]["history_file"])
    all_feats = []
    for ticker, group in history.groupby("ticker"):
        feats = compute_features_for_ticker(group)
        if feats.empty:
            continue
        all_feats.append(feats)
    if not all_feats:
        log.error("No features computed for any ticker.")
        return
    full = pd.concat(all_feats, ignore_index=True)
    full.to_parquet(cfg["data"]["features_file"], index=False)
    log.info(f"Saved features for {full['ticker'].nunique()} tickers to {cfg['data']['features_file']}")


if __name__ == "__main__":
    main()
