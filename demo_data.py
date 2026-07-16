"""Dữ liệu OHLCV giả lập cho demo/kiểm thử offline (KHÔNG phản ánh hiệu quả thật)."""
import numpy as np
import pandas as pd


def synth_h1(n_hours: int, seed: int, start: float = 100.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n_hours, freq="h", tz="UTC")
    price = np.zeros(n_hours); price[0] = start
    trend = np.linspace(0, 0.25, n_hours); x = 0.0
    for i in range(1, n_hours):
        x = 0.9 * x + rng.normal(0, 0.015)
        price[i] = start * (1 + trend[i]) * (1 + x)
    price = np.maximum(price, 1.0)
    close = price; open_ = np.concatenate([[close[0]], close[:-1]])
    noise = np.abs(rng.normal(0, 0.004, n_hours)) * close
    high = np.maximum(open_, close) + noise
    low = np.minimum(open_, close) - noise
    vol = rng.uniform(1e5, 5e5, n_hours)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def to_daily(h1: pd.DataFrame) -> pd.DataFrame:
    return h1.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"}).dropna()


def demo_dataset(symbols, days=120):
    data = {}
    for i, s in enumerate(symbols):
        h1 = synth_h1(24 * days, seed=i + 1, start=60 + 20 * i)
        data[s] = (h1, to_daily(h1))
    return data
