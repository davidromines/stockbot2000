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

def compute_features_for_ticker(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    if len(df) < 210:  # need enough history for 200-day SMA etc.
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
