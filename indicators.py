"""
Chỉ báo kỹ thuật — Stochastic RSI theo cấu hình tài liệu (8, 5, 3, 3).

Ánh xạ thông số TradingView (đọc từ trên xuống): K=8, D=5, RSI Length=3, Stoch Length=3.
Đường "xanh" = %K, "đỏ" = %D. Quá bán < 20 | Quá mua > 80.
"""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50.0)


def stoch_rsi(close, k_smooth=8, d_smooth=5, rsi_length=3, stoch_length=3) -> pd.DataFrame:
    r = rsi(close, rsi_length)
    lowest = r.rolling(stoch_length, min_periods=stoch_length).min()
    highest = r.rolling(stoch_length, min_periods=stoch_length).max()
    denom = (highest - lowest).replace(0, np.nan)
    stoch = (100 * (r - lowest) / denom).clip(0, 100)
    k = stoch.rolling(k_smooth, min_periods=1).mean()
    d = k.rolling(d_smooth, min_periods=1).mean()
    return pd.DataFrame({"k": k, "d": d}, index=close.index)


def cross_up(k: pd.Series, d: pd.Series) -> pd.Series:
    return (k > d) & (k.shift(1) <= d.shift(1))


def cross_down(k: pd.Series, d: pd.Series) -> pd.Series:
    return (k < d) & (k.shift(1) >= d.shift(1))
