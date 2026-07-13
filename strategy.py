"""
Tín hiệu chiến lược (long-only) — số hoá quy tắc trong tài liệu tối ưu.
Dùng chung cho cả BACKTEST và LIVE để đảm bảo hành vi nhất quán.

Vào lệnh:
  D1 (cần): %K > %D và %K < ob_level (không quá mua).
  H1 (đủ) : %K cắt LÊN %D từ vùng quá bán (min(K,D) < os_level) và nến H1 đóng cửa XANH.
Thoát:
  TP = entry*(1+tp_pct); SL = max(đáy N nến H1, entry*(1-max_sl_pct));
  Đảo chiều sớm: K,D > ob_level và K cắt XUỐNG D; Hết hạn giữ: > max_hold_bars nến.
"""
from dataclasses import dataclass
import pandas as pd
from indicators import stoch_rsi, cross_up, cross_down


@dataclass
class Params:
    k_smooth: int = 8
    d_smooth: int = 5
    rsi_length: int = 3
    stoch_length: int = 3
    os_level: float = 20.0
    ob_level: float = 80.0
    tp_pct: float = 0.03
    max_sl_pct: float = 0.02
    swing_lookback: int = 6
    max_hold_bars: int = 24
    risk_per_trade: float = 0.02
    max_open_trades: int = 3
    daily_stop: float = 0.05


def add_indicators(h1: pd.DataFrame, d1: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Gắn các cột chỉ báo H1 + map chỉ báo D1 (đã đóng) vào từng giờ."""
    h1 = h1.copy()
    s = stoch_rsi(h1["close"], p.k_smooth, p.d_smooth, p.rsi_length, p.stoch_length)
    h1["k"], h1["d"] = s["k"], s["d"]
    h1["cross_up"] = cross_up(h1["k"], h1["d"])
    h1["cross_down"] = cross_down(h1["k"], h1["d"])

    sd = stoch_rsi(d1["close"], p.k_smooth, p.d_smooth, p.rsi_length, p.stoch_length)
    daily = pd.DataFrame({"dk": sd["k"], "dd": sd["d"]}).shift(1)  # dùng nến D1 đã đóng
    daily = daily.reindex(h1.index, method="ffill")
    h1["dk"], h1["dd"] = daily["dk"], daily["dd"]
    return h1


def compute_signals(h1: pd.DataFrame, d1: pd.DataFrame, p: Params) -> pd.DataFrame:
    h1 = add_indicators(h1, d1, p)
    d1_ok = (h1["dk"] > h1["dd"]) & (h1["dk"] < p.ob_level)
    green = h1["close"] > h1["open"]
    from_oversold = h1[["k", "d"]].min(axis=1) < p.os_level
    h1["entry_signal"] = d1_ok & h1["cross_up"] & from_oversold & green
    return h1


def latest_signal(h1: pd.DataFrame, d1: pd.DataFrame, p: Params) -> dict:
    """
    Dùng cho LIVE: xét NẾN H1 vừa đóng gần nhất. Trả về dict mô tả tín hiệu.
    Giả định caller truyền dữ liệu chỉ gồm các nến ĐÃ ĐÓNG.
    """
    sig = compute_signals(h1, d1, p)
    last = sig.iloc[-1]
    entry = float(last["close"])
    lo = max(0, len(sig) - 1 - p.swing_lookback)
    swing_low = float(sig["low"].iloc[lo:].min())
    sl = max(swing_low, entry * (1 - p.max_sl_pct))
    return {
        "time": sig.index[-1],
        "signal": bool(last["entry_signal"]) and sl < entry,
        "entry": entry,
        "sl": sl,
        "tp": entry * (1 + p.tp_pct),
        "k": float(last["k"]), "d": float(last["d"]),
        "dk": float(last["dk"]) if pd.notna(last["dk"]) else None,
        "dd": float(last["dd"]) if pd.notna(last["dd"]) else None,
    }
