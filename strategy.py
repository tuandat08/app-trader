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
    max_equity_per_trade: float = 0.0   # V2: trần vốn tối đa/lệnh (0 = không giới hạn; 0.15 = 15%)
    stall_min_profit: float = 0.0       # V2: mốc lời tối thiểu để KHÔNG bị cắt "chết yểu" (0.01 = 1%)
    # --- V2.1 (thử nghiệm giả thuyết) ---
    use_reversal_exit: bool = True      # thoát khi StochRSI cắt xuống. TẮT = để Trailing/SL/Stall tự quyết
    use_pullback_entry: bool = False    # vào lúc "nghỉ lấy đà": nến H1 ĐỎ + StochRSI vùng thấp (thay vì xanh + cross up)
    # --- Cải tiến (mặc định TẮT để giữ nguyên baseline) ---
    use_trend_filter: bool = False   # chỉ vào khi giá > EMA (lọc downtrend)
    trend_ema: int = 50
    use_trailing: bool = False       # bỏ chốt cứng TP, dời stop theo giá
    trail_pct: float = 0.03          # trailing stop cách đỉnh 3%
    use_market_filter: bool = False  # chỉ vào lệnh khi thị trường (BTC) đang tăng
    market_ema: int = 100            # BTC > EMA này (nến ngày) mới cho vào lệnh
    market_symbol: str = "BTC/USDT"
    use_stall_exit: bool = False     # cắt lệnh "chết yểu": sau N giờ chưa có lời thì thoát
    stall_bars: int = 12
    use_gain_filter: bool = False    # né coin đã tăng trong "vùng chết" [lo, hi] khi vào
    gain_avoid_lo: float = 0.05
    gain_avoid_hi: float = 0.10


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

    # EMA xu hướng trên D1 (dùng nến đã đóng), map sang H1
    if p.use_trend_filter:
        ema = d1["close"].ewm(span=p.trend_ema, adjust=False, min_periods=p.trend_ema).mean().shift(1)
        h1["trend_ema"] = ema.reindex(h1.index, method="ffill")
    return h1


def compute_signals(h1: pd.DataFrame, d1: pd.DataFrame, p: Params) -> pd.DataFrame:
    h1 = add_indicators(h1, d1, p)
    d1_ok = (h1["dk"] > h1["dd"]) & (h1["dk"] < p.ob_level)
    green = h1["close"] > h1["open"]
    red = h1["close"] < h1["open"]
    from_oversold = h1[["k", "d"]].min(axis=1) < p.os_level
    if p.use_pullback_entry:
        # Mua lúc "nghỉ lấy đà": nến H1 ĐỎ (giảm nhẹ) + StochRSI về vùng thấp,
        # coin vẫn trong uptrend D1 / top-gainer. Tránh mua đu đỉnh lúc dựng cột xanh.
        cond = d1_ok & red & from_oversold
    else:
        cond = d1_ok & h1["cross_up"] & from_oversold & green
    if p.use_trend_filter and "trend_ema" in h1.columns:
        cond = cond & (h1["close"] > h1["trend_ema"])  # chỉ vào khi trên EMA
    h1["entry_signal"] = cond
    return h1


def params_from_config(cfg) -> Params:
    """Dựng Params từ config (bao gồm mọi cải tiến đã kiểm chứng) cho bot live."""
    return Params(
        tp_pct=cfg.tp_pct, max_sl_pct=cfg.max_sl_pct,
        risk_per_trade=cfg.risk_per_trade, max_open_trades=cfg.max_open_trades,
        daily_stop=cfg.daily_stop,
        use_trend_filter=cfg.use_trend_filter, trend_ema=cfg.trend_ema,
        use_trailing=cfg.use_trailing, trail_pct=cfg.trail_pct,
        use_stall_exit=cfg.use_stall_exit, stall_bars=cfg.stall_bars,
        use_gain_filter=cfg.use_gain_filter,
        gain_avoid_lo=cfg.gain_avoid_lo, gain_avoid_hi=cfg.gain_avoid_hi,
        # V2
        use_market_filter=getattr(cfg, "use_market_filter", False),
        market_ema=getattr(cfg, "market_ema", 50),
        market_symbol=getattr(cfg, "market_symbol", "BTC/USDT"),
        max_equity_per_trade=getattr(cfg, "max_equity_per_trade", 0.0),
        stall_min_profit=getattr(cfg, "stall_min_profit", 0.0),
        use_reversal_exit=getattr(cfg, "use_reversal_exit", True),
        use_pullback_entry=getattr(cfg, "use_pullback_entry", False),
    )


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
    ret24 = float(entry / sig["close"].iloc[-25] - 1) if len(sig) >= 25 else None

    signal = bool(last["entry_signal"]) and sl < entry
    # Lọc né "vùng tăng chết" (khớp backtest)
    if signal and p.use_gain_filter and ret24 is not None \
            and p.gain_avoid_lo <= ret24 < p.gain_avoid_hi:
        signal = False
    return {
        "time": sig.index[-1],
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": entry * (1 + p.tp_pct),
        "ret24": ret24,
        "k": float(last["k"]), "d": float(last["d"]),
        "dk": float(last["dk"]) if pd.notna(last["dk"]) else None,
        "dd": float(last["dd"]) if pd.notna(last["dd"]) else None,
    }
