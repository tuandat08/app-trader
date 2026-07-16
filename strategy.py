"""
Tín hiệu chiến lược Swing Stoch RSI (long-only). Dùng chung backtest & live.
Cải tiến đã kiểm chứng: lọc xu hướng (EMA), né vùng tăng chết. (Trailing & stall xử lý ở engine.)
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
    # --- Cải tiến (mặc định TẮT để giữ baseline) ---
    use_trend_filter: bool = False
    trend_ema: int = 50
    use_trailing: bool = False
    trail_pct: float = 0.03
    use_stall_exit: bool = False
    stall_bars: int = 12
    use_gain_filter: bool = False
    gain_avoid_lo: float = 0.05
    gain_avoid_hi: float = 0.10


def add_indicators(h1: pd.DataFrame, d1: pd.DataFrame, p: Params) -> pd.DataFrame:
    h1 = h1.copy()
    s = stoch_rsi(h1["close"], p.k_smooth, p.d_smooth, p.rsi_length, p.stoch_length)
    h1["k"], h1["d"] = s["k"], s["d"]
    h1["cross_up"] = cross_up(h1["k"], h1["d"])
    h1["cross_down"] = cross_down(h1["k"], h1["d"])
    sd = stoch_rsi(d1["close"], p.k_smooth, p.d_smooth, p.rsi_length, p.stoch_length)
    daily = pd.DataFrame({"dk": sd["k"], "dd": sd["d"]}).shift(1)
    daily = daily.reindex(h1.index, method="ffill")
    h1["dk"], h1["dd"] = daily["dk"], daily["dd"]
    if p.use_trend_filter:
        ema = d1["close"].ewm(span=p.trend_ema, adjust=False, min_periods=p.trend_ema).mean().shift(1)
        h1["trend_ema"] = ema.reindex(h1.index, method="ffill")
    return h1


def compute_signals(h1: pd.DataFrame, d1: pd.DataFrame, p: Params) -> pd.DataFrame:
    h1 = add_indicators(h1, d1, p)
    d1_ok = (h1["dk"] > h1["dd"]) & (h1["dk"] < p.ob_level)
    green = h1["close"] > h1["open"]
    from_oversold = h1[["k", "d"]].min(axis=1) < p.os_level
    cond = d1_ok & h1["cross_up"] & from_oversold & green
    if p.use_trend_filter and "trend_ema" in h1.columns:
        cond = cond & (h1["close"] > h1["trend_ema"])
    h1["entry_signal"] = cond
    return h1


def params_from_config(cfg) -> Params:
    return Params(
        tp_pct=cfg.tp_pct, max_sl_pct=cfg.max_sl_pct,
        risk_per_trade=cfg.risk_per_trade, max_open_trades=cfg.max_open_trades,
        daily_stop=cfg.daily_stop,
        use_trend_filter=cfg.use_trend_filter, trend_ema=cfg.trend_ema,
        use_trailing=cfg.use_trailing, trail_pct=cfg.trail_pct,
        use_stall_exit=cfg.use_stall_exit, stall_bars=cfg.stall_bars,
        use_gain_filter=cfg.use_gain_filter,
        gain_avoid_lo=cfg.gain_avoid_lo, gain_avoid_hi=cfg.gain_avoid_hi,
    )


def latest_signal(h1: pd.DataFrame, d1: pd.DataFrame, p: Params) -> dict:
    """Dùng cho LIVE: xét nến H1 vừa đóng gần nhất."""
    sig = compute_signals(h1, d1, p)
    last = sig.iloc[-1]
    entry = float(last["close"])
    lo = max(0, len(sig) - 1 - p.swing_lookback)
    swing_low = float(sig["low"].iloc[lo:].min())
    sl = max(swing_low, entry * (1 - p.max_sl_pct))
    ret24 = float(entry / sig["close"].iloc[-25] - 1) if len(sig) >= 25 else None
    signal = bool(last["entry_signal"]) and sl < entry
    if signal and p.use_gain_filter and ret24 is not None \
            and p.gain_avoid_lo <= ret24 < p.gain_avoid_hi:
        signal = False
    return {
        "time": sig.index[-1], "signal": signal, "entry": entry, "sl": sl,
        "tp": entry * (1 + p.tp_pct), "ret24": ret24,
        "k": float(last["k"]), "d": float(last["d"]),
        "dk": float(last["dk"]) if pd.notna(last["dk"]) else None,
        "dd": float(last["dd"]) if pd.notna(last["dd"]) else None,
    }
