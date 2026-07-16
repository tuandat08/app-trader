"""
Quét tín hiệu thời gian thực: với mỗi symbol, lấy nến H1 & D1 gần nhất
(chỉ dùng nến ĐÃ ĐÓNG) rồi áp dụng strategy.latest_signal.
"""
import pandas as pd
from strategy import Params, latest_signal
from data import fetch_recent


def _closed_only(df: pd.DataFrame) -> pd.DataFrame:
    """Bỏ nến cuối nếu nó chưa đóng (an toàn: luôn bỏ nến đang chạy)."""
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
