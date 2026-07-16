"""Quét tín hiệu thời gian thực (chỉ dùng nến đã đóng)."""
import pandas as pd
from strategy import Params, latest_signal
from data import fetch_recent


def _closed_only(df: pd.DataFrame) -> pd.DataFrame:
    return df.iloc[:-1] if len(df) > 1 else df


def scan_symbol(symbol, p: Params, exchange) -> dict:
    h1 = _closed_only(fetch_recent(symbol, "1h", limit=200, exchange=exchange))
    d1 = _closed_only(fetch_recent(symbol, "1d", limit=120, exchange=exchange))
    if len(h1) < 30 or len(d1) < 10:
        return {"symbol": symbol, "signal": False, "reason": "thiếu dữ liệu"}
    sig = latest_signal(h1, d1, p)
    sig["symbol"] = symbol
    return sig


def scan(symbols, p: Params, exchange) -> list:
    out = []
    for s in symbols:
        try:
            out.append(scan_symbol(s, p, exchange))
        except Exception as e:
            out.append({"symbol": s, "signal": False, "reason": f"lỗi: {e}"})
    return out
