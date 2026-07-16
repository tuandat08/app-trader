"""
Engine backtest event-driven (long-only, Spot). Không nhìn trước tương lai.
Dùng risk.position_size để khớp đúng logic sizing với module live.
"""
from dataclasses import dataclass
from typing import Dict, Tuple, List
import pandas as pd

from strategy import Params, compute_signals
from risk import position_size, DailyStop

# Phí giao dịch giả định mỗi chiều (Binance Spot ~0.1%). Đặt 0 để bỏ qua.
FEE_RATE = 0.001


@dataclass
class Trade:
    symbol: str
    entry_time: pd.Timestamp
    entry: float
    sl: float
    tp: float
    qty: float
    risk_amount: float
    exit_time: pd.Timestamp = None
    exit: float = None
    reason: str = ""
    fees: float = 0.0
    # Đặc điểm lúc VÀO lệnh (để phân tích thắng/thua)
    e_ret24: float = None     # % coin đã tăng 24h trước khi vào
    e_osdepth: float = None   # độ sâu quá bán (min K,D) lúc vào
    e_hour: int = None        # giờ vào lệnh (UTC)
    bars_held: int = 0        # số nến H1 đã giữ

    @property
    def pnl(self) -> float:
        return (self.exit - self.entry) * self.qty - self.fees

    @property
    def r_multiple(self) -> float:
        return self.pnl / self.risk_amount if self.risk_amount else 0.0


@dataclass
class Result:
    equity_curve: pd.Series
    trades: List[Trade]
    params: Params
    initial_capital: float


def _swing_low(df, idx, lookback):
    lo = max(0, idx - lookback)
    return float(df["low"].iloc[lo:idx + 1].min())


def gainer_eligibility(data, top_n=10, lookback_h=24, min_ret=0.0, max_ret=0.40):
    """
    Ma trận eligibility (index=timeline, cột=symbol, bool): tại mỗi nến H1, coin có
    'đủ điều kiện vào lệnh' nếu nó nằm TOP-N tăng mạnh nhất trong 'lookback_h' giờ qua
    (tính bằng dữ liệu ĐÃ ĐÓNG, không nhìn trước) và mức tăng nằm trong (min_ret, max_ret].
    Đây là cách 'focus vào coin đang tăng' đúng với tinh thần chiến lược.
    """
    rets = {}
    for s, (h1, _) in data.items():
        r = h1["close"] / h1["close"].shift(lookback_h) - 1.0
        rets[s] = r
    wide = pd.DataFrame(rets).sort_index()
    # rank giảm dần theo % tăng, tại mỗi hàng (thời điểm)
    rank = wide.rank(axis=1, ascending=False, method="first")
    elig = (rank <= top_n) & (wide > min_ret) & (wide <= max_ret)
    return elig.fillna(False)


def run_backtest(data: Dict[str, Tuple[pd.DataFrame, pd.DataFrame]], p: Params,
                 initial_capital: float = 1000.0, eligible: pd.DataFrame = None) -> Result:
    """
    eligible: (tuỳ chọn) ma trận bool từ gainer_eligibility(). Nếu truyền vào, chỉ cho
    vào lệnh với coin đủ điều kiện top-gainer tại thời điểm đó. None = không lọc.
    """
    if getattr(p, "strategy_mode", "stochrsi") == "vab":
        return _run_vab(data, p, initial_capital)
    if getattr(p, "strategy_mode", "stochrsi") == "funding":
        return _run_funding(data, p, initial_capital)
    sig = {s: compute_signals(h1, d1, p) for s, (h1, d1) in data.items()}
    pos_index = {s: {ts: i for i, ts in enumerate(df.index)} for s, df in sig.items()}
    timeline = sorted(set().union(*[set(df.index) for df in sig.values()]))

    # Bộ lọc thị trường: chỉ cho vào lệnh khi BTC (đại diện) đang trên EMA dài hạn
    market_set = None
    if p.use_market_filter and p.market_symbol in data:
        btc_d1 = data[p.market_symbol][1]
        c = btc_d1["close"]
        ema = c.ewm(span=p.market_ema, adjust=False, min_periods=p.market_ema).mean()
        reg = (c > ema).shift(1)  # trạng thái ngày đã đóng, tránh nhìn trước
        market_ser = reg.reindex(pd.Index(timeline), method="ffill")
        market_set = {ts: (v is True) for ts, v in market_ser.items()}  # NaN -> False

    cash = initial_capital
    open_pos: Dict[str, dict] = {}
    closed: List[Trade] = []
    curve = []
    dstop = DailyStop(threshold=p.daily_stop)

    def equity_at(ts):
        eq = cash
        for s, pp in open_pos.items():
            i = pos_index[s].get(ts)
            px = float(sig[s]["close"].iloc[i]) if i is not None else pp["trade"].entry
            eq += pp["trade"].qty * px
        return eq

    for ts in timeline:
        # 1) Thoát lệnh
        for s in list(open_pos.keys()):
            i = pos_index[s].get(ts)
            if i is None:
                continue
            row = sig[s].iloc[i]
            pp = open_pos[s]; tr = pp["trade"]; pp["bars"] += 1
            pp["peak"] = max(pp.get("peak", tr.entry), float(row["high"]))
            ex, reason = None, ""
            if p.use_trailing:
                # Bỏ chốt cứng TP: để lời chạy, dời stop theo đỉnh
                trail_stop = pp["peak"] * (1 - p.trail_pct)
                eff_sl = max(tr.sl, trail_stop)
                if row["low"] <= eff_sl:
                    ex, reason = eff_sl, ("Trail" if trail_stop > tr.sl else "SL")
                elif p.use_reversal_exit and row["k"] > p.ob_level and row["d"] > p.ob_level and row["cross_down"]:
                    ex, reason = float(row["close"]), "Reversal"
                elif p.use_stall_exit and pp["bars"] >= p.stall_bars and float(row["close"]) <= tr.entry * (1 + p.stall_min_profit):
                    ex, reason = float(row["close"]), "Stall"
                elif pp["bars"] >= p.max_hold_bars:
                    ex, reason = float(row["close"]), "TimeStop"
            else:
                if row["low"] <= tr.sl:
                    ex, reason = tr.sl, "SL"
                elif row["high"] >= tr.tp:
                    ex, reason = tr.tp, "TP"
                elif p.use_reversal_exit and row["k"] > p.ob_level and row["d"] > p.ob_level and row["cross_down"]:
                    ex, reason = float(row["close"]), "Reversal"
                elif p.use_stall_exit and pp["bars"] >= p.stall_bars and float(row["close"]) <= tr.entry * (1 + p.stall_min_profit):
                    ex, reason = float(row["close"]), "Stall"
                elif pp["bars"] >= p.max_hold_bars:
                    ex, reason = float(row["close"]), "TimeStop"
            if ex is not None:
                exit_fee = ex * tr.qty * FEE_RATE
                tr.exit_time, tr.exit, tr.reason = ts, ex, reason
                tr.fees += exit_fee
                tr.bars_held = pp["bars"]
                cash += tr.qty * ex - exit_fee   # trừ phí vào tiền mặt để khớp PnL
                closed.append(tr); del open_pos[s]

        # 2) Ngưng lỗ ngày
        eq = equity_at(ts)
        blocked = dstop.update(ts.date(), eq)

        # 3) Vào lệnh (thêm điều kiện thị trường đang tăng nếu bật)
        market_now = True if market_set is None else bool(market_set.get(ts, False))
        if not blocked and market_now and len(open_pos) < p.max_open_trades:
            for s in sig.keys():
                if s in open_pos or len(open_pos) >= p.max_open_trades:
                    continue
                i = pos_index[s].get(ts)
                if i is None or i < 2 or not bool(sig[s].iloc[i]["entry_signal"]):
                    continue
                # Lọc top-gainer động: chỉ vào lệnh nếu coin đang trong nhóm tăng mạnh
                if eligible is not None:
                    try:
                        if not bool(eligible.at[ts, s]):
                            continue
                    except (KeyError, IndexError):
                        continue
                row = sig[s].iloc[i]
                entry = float(row["close"])
                # Bộ lọc né "vùng tăng chết": bỏ qua nếu coin đã tăng trong [lo, hi]
                ret24 = (entry / float(sig[s]["close"].iloc[i - 24]) - 1) if i >= 24 else None
                if (p.use_gain_filter and ret24 is not None
                        and p.gain_avoid_lo <= ret24 < p.gain_avoid_hi):
                    continue
                sl = max(_swing_low(sig[s], i, p.swing_lookback), entry * (1 - p.max_sl_pct))
                if sl >= entry:
                    continue
                tp = entry * (1 + p.tp_pct)
                sz = position_size(eq, entry, sl, p.risk_per_trade, cash,
                                   max_equity_per_trade=p.max_equity_per_trade)
                if sz["qty"] <= 0 or sz["notional"] < 10:
                    continue
                fee = sz["notional"] * FEE_RATE
                cash -= sz["notional"] + fee   # trừ cả phí mua vào tiền mặt
                tr = Trade(s, ts, entry, sl, tp, sz["qty"], sz["risk_amount"], fees=fee)
                tr.e_ret24 = ret24
                tr.e_osdepth = float(min(row["k"], row["d"]))
                tr.e_hour = int(ts.hour)
                open_pos[s] = {"trade": tr, "bars": 0}

        curve.append((ts, equity_at(ts)))

    last = timeline[-1]
    for s, pp in list(open_pos.items()):
        i = pos_index[s].get(last)
        px = float(sig[s]["close"].iloc[i]) if i is not None else pp["trade"].entry
        exit_fee = px * tr.qty * FEE_RATE
        tr = pp["trade"]; tr.exit_time, tr.exit, tr.reason = last, px, "EndOfData"
        tr.fees += exit_fee
        cash += tr.qty * px - exit_fee; closed.append(tr)

    ec = pd.Series(dict(curve)).sort_index()
    return Result(ec, closed, p, initial_capital)


# ============================ VAB (Volume Anomaly Breakout) ============================
def _resample_ohlcv(h1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Gộp nến H1 -> H4 (nếu cần). tf: '1h' | '4h'."""
    if tf == "1h":
        return h1
    o = h1["open"].resample("4h").first()
    hi = h1["high"].resample("4h").max()
    lo = h1["low"].resample("4h").min()
    c = h1["close"].resample("4h").last()
    v = h1["volume"].resample("4h").sum()
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": v}).dropna()


def _vab_indicators(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Bollinger Bands + Bandwidth (squeeze) + MA khối lượng + ATR."""
    df = df.copy()
    mid = df["close"].rolling(p.bb_period).mean()
    std = df["close"].rolling(p.bb_period).std(ddof=0)
    df["bb_mid"] = mid
    df["bb_up"] = mid + p.bb_mult * std
    df["bb_lo"] = mid - p.bb_mult * std
    df["bbw"] = (df["bb_up"] - df["bb_lo"]) / mid
    # "Nén": BBW nằm ở 25% thấp nhất của biên độ N nến gần nhất
    lo_bbw = df["bbw"].rolling(p.squeeze_lookback).min()
    hi_bbw = df["bbw"].rolling(p.squeeze_lookback).max()
    rng = (hi_bbw - lo_bbw).replace(0, float("nan"))
    df["squeeze_on"] = ((df["bbw"] - lo_bbw) / rng) < 0.25
    df["vol_ma"] = df["volume"].rolling(p.vol_ma_period).mean()
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(p.atr_period).mean()
    return df


def _run_vab(data, p: Params, initial_capital: float = 1000.0) -> Result:
    """Engine VAB: nén (squeeze) -> breakout qua dải trên BB kèm volume đột biến.
    SL dưới đáy nến breakout; breakeven 1R; ATR trailing; false-breakout; stall."""
    tf = getattr(p, "vab_timeframe", "1h")
    sig = {s: _vab_indicators(_resample_ohlcv(h1, tf), p) for s, (h1, d1) in data.items()}
    d1s = {s: d1 for s, (h1, d1) in data.items()}
    pos_index = {s: {ts: i for i, ts in enumerate(df.index)} for s, df in sig.items()}
    timeline = sorted(set().union(*[set(df.index) for df in sig.values()])) if sig else []

    # Bộ lọc thị trường BTC > EMA (nến ngày)
    market_set = None
    if p.use_market_filter and p.market_symbol in d1s:
        c = d1s[p.market_symbol]["close"]
        ema = c.ewm(span=p.market_ema, adjust=False, min_periods=p.market_ema).mean()
        reg = (c > ema).shift(1)
        ser = reg.reindex(pd.Index(timeline), method="ffill")
        market_set = {ts: (v is True) for ts, v in ser.items()}

    cash = initial_capital
    open_pos, closed, curve = {}, [], []
    dstop = DailyStop(threshold=p.daily_stop)

    def equity_at(ts):
        eq = cash
        for s, pp in open_pos.items():
            i = pos_index[s].get(ts)
            px = float(sig[s]["close"].iloc[i]) if i is not None else pp["trade"].entry
            eq += pp["trade"].qty * px
        return eq

    for ts in timeline:
        # 1) Thoát lệnh
        for s in list(open_pos.keys()):
            i = pos_index[s].get(ts)
            if i is None:
                continue
            row = sig[s].iloc[i]
            pp = open_pos[s]; tr = pp["trade"]; pp["bars"] += 1
            pp["peak"] = max(pp.get("peak", tr.entry), float(row["high"]))
            R = tr.entry - tr.sl
            ex, reason = None, ""
            eff_sl = tr.sl
            # Breakeven: đạt 1R -> dời SL về hoà vốn
            if p.use_breakeven and R > 0 and pp["peak"] >= tr.entry + R:
                eff_sl = max(eff_sl, tr.entry)
            # ATR trailing
            atr = float(row["atr"]) if pd.notna(row["atr"]) else None
            if p.use_atr_trailing and atr:
                eff_sl = max(eff_sl, pp["peak"] - p.atr_mult * atr)
            if float(row["low"]) <= eff_sl:
                ex = eff_sl
                reason = "Trail" if eff_sl > tr.entry else ("BE" if eff_sl == tr.entry and eff_sl > tr.sl else "SL")
            elif p.false_breakout_exit and float(row["close"]) < float(row["bb_mid"]):
                ex, reason = float(row["close"]), "FalseBO"
            elif p.use_stall_exit and pp["bars"] >= p.stall_bars and float(row["close"]) <= tr.entry * (1 + p.stall_min_profit):
                ex, reason = float(row["close"]), "Stall"
            elif pp["bars"] >= p.max_hold_bars:
                ex, reason = float(row["close"]), "TimeStop"
            if ex is not None:
                fee = ex * tr.qty * FEE_RATE
                tr.exit_time, tr.exit, tr.reason = ts, ex, reason
                tr.fees += fee; tr.bars_held = pp["bars"]
                cash += tr.qty * ex - fee
                closed.append(tr); del open_pos[s]

        # 2) Ngưng lỗ ngày
        eq = equity_at(ts)
        blocked = dstop.update(ts.date(), eq)
        market_now = True if market_set is None else bool(market_set.get(ts, False))

        # 3) Vào lệnh
        if not blocked and market_now and len(open_pos) < p.max_open_trades:
            for s in sig.keys():
                if s in open_pos or len(open_pos) >= p.max_open_trades:
                    continue
                i = pos_index[s].get(ts)
                if i is None or i < max(p.bb_period, p.squeeze_lookback, p.atr_period) + 1:
                    continue
                row = sig[s].iloc[i]; prev = sig[s].iloc[i - 1]
                if not (bool(prev["squeeze_on"]) and pd.notna(row["bb_up"]) and pd.notna(row["vol_ma"])):
                    continue
                entry = float(row["close"]); low_i = float(row["low"])
                breakout = entry > float(row["bb_up"]) and entry > float(row["open"])
                vol_ok = float(row["volume"]) > p.vol_mult * float(row["vol_ma"])
                if not (breakout and vol_ok):
                    continue
                # Lọc nến quá dài: entry -> đáy nến > vab_max_candle thì bỏ
                if entry <= 0 or (entry - low_i) / entry > p.vab_max_candle:
                    continue
                sl = min(low_i, entry * (1 - 1e-4))
                sl = max(sl, entry * (1 - p.max_sl_pct))   # không để SL xa hơn max_sl
                if sl >= entry:
                    continue
                sz = position_size(eq, entry, sl, p.risk_per_trade, cash,
                                   max_equity_per_trade=p.max_equity_per_trade)
                if sz["qty"] <= 0 or sz["notional"] < 10:
                    continue
                fee = sz["notional"] * FEE_RATE
                cash -= sz["notional"] + fee
                tr = Trade(s, ts, entry, sl, entry * (1 + p.tp_pct), sz["qty"], sz["risk_amount"], fees=fee)
                tr.e_hour = int(ts.hour)
                open_pos[s] = {"trade": tr, "bars": 0, "peak": entry}

        curve.append((ts, equity_at(ts)))

    if timeline:
        last = timeline[-1]
        for s, pp in list(open_pos.items()):
            i = pos_index[s].get(last)
            tr = pp["trade"]
            px = float(sig[s]["close"].iloc[i]) if i is not None else tr.entry
            fee = px * tr.qty * FEE_RATE
            tr.exit_time, tr.exit, tr.reason = last, px, "EndOfData"
            tr.fees += fee; cash += tr.qty * px - fee; closed.append(tr)

    ec = pd.Series(dict(curve)).sort_index() if curve else pd.Series(dtype=float)
    return Result(ec, closed, p, initial_capital)


# ==================== FUNDING CONTRARIAN LONG (FCL) ====================
def _run_funding(data, p: Params, initial_capital: float = 1000.0) -> Result:
    """Long coin có funding ÂM cực đoan (short chen chúc -> kỳ vọng squeeze lên).
    Cần cột 'funding' trong h1 (gắn qua data.attach_funding). Long-only spot."""
    sig = {s: h1 for s, (h1, d1) in data.items() if "funding" in h1.columns}
    if not sig:
        return Result(pd.Series(dtype=float), [], p, initial_capital)
    d1s = {s: d1 for s, (h1, d1) in data.items()}
    pos_index = {s: {ts: i for i, ts in enumerate(df.index)} for s, df in sig.items()}
    timeline = sorted(set().union(*[set(df.index) for df in sig.values()]))

    # Ma trận funding rộng (index=timeline, cột=symbol) + ngưỡng quantile theo từng hàng
    fund_wide = pd.DataFrame({s: sig[s]["funding"] for s in sig}).reindex(pd.Index(timeline)).ffill()
    thr = fund_wide.quantile(p.funding_quantile, axis=1)   # giá trị funding ở nhóm thấp nhất mỗi thời điểm

    market_set = None
    if p.use_market_filter and p.market_symbol in d1s:
        c = d1s[p.market_symbol]["close"]
        ema = c.ewm(span=p.market_ema, adjust=False, min_periods=p.market_ema).mean()
        reg = (c > ema).shift(1)
        ser = reg.reindex(pd.Index(timeline), method="ffill")
        market_set = {ts: (v is True) for ts, v in ser.items()}

    cash = initial_capital
    open_pos, closed, curve = {}, [], []
    dstop = DailyStop(threshold=p.daily_stop)

    def equity_at(ts):
        eq = cash
        for s, pp in open_pos.items():
            i = pos_index[s].get(ts)
            px = float(sig[s]["close"].iloc[i]) if i is not None else pp["trade"].entry
            eq += pp["trade"].qty * px
        return eq

    for ts in timeline:
        thr_ts = thr.get(ts, float("nan"))
        # 1) Thoát
        for s in list(open_pos.keys()):
            i = pos_index[s].get(ts)
            if i is None:
                continue
            row = sig[s].iloc[i]
            pp = open_pos[s]; tr = pp["trade"]; pp["bars"] += 1
            pp["peak"] = max(pp.get("peak", tr.entry), float(row["high"]))
            fund = float(row["funding"]) if pd.notna(row["funding"]) else None
            ex, reason = None, ""
            eff_sl = tr.sl
            if p.use_trailing:
                eff_sl = max(eff_sl, pp["peak"] * (1 - p.trail_pct))
            if float(row["low"]) <= eff_sl:
                ex, reason = eff_sl, ("Trail" if eff_sl > tr.sl else "SL")
            elif p.funding_exit_pos and fund is not None and fund >= 0:
                ex, reason = float(row["close"]), "Funding+"
            elif p.use_stall_exit and pp["bars"] >= p.stall_bars and float(row["close"]) <= tr.entry * (1 + p.stall_min_profit):
                ex, reason = float(row["close"]), "Stall"
            elif pp["bars"] >= p.max_hold_bars:
                ex, reason = float(row["close"]), "TimeStop"
            if ex is not None:
                fee = ex * tr.qty * FEE_RATE
                tr.exit_time, tr.exit, tr.reason = ts, ex, reason
                tr.fees += fee; tr.bars_held = pp["bars"]
                cash += tr.qty * ex - fee
                closed.append(tr); del open_pos[s]

        eq = equity_at(ts)
        blocked = dstop.update(ts.date(), eq)
        market_now = True if market_set is None else bool(market_set.get(ts, False))

        # 2) Vào lệnh: coin có funding <= ngưỡng nhóm thấp nhất VÀ < funding_max
        if not blocked and market_now and len(open_pos) < p.max_open_trades and pd.notna(thr_ts):
            cands = []
            for s in sig.keys():
                if s in open_pos:
                    continue
                f = fund_wide.at[ts, s] if ts in fund_wide.index else float("nan")
                if pd.notna(f) and f <= thr_ts and f < p.funding_max:
                    cands.append((s, f))
            cands.sort(key=lambda x: x[1])   # âm nhất trước
            for s, f in cands:
                if len(open_pos) >= p.max_open_trades:
                    break
                i = pos_index[s].get(ts)
                if i is None:
                    continue
                entry = float(sig[s]["close"].iloc[i])
                sl = entry * (1 - p.max_sl_pct)
                if sl >= entry:
                    continue
                sz = position_size(eq, entry, sl, p.risk_per_trade, cash,
                                   max_equity_per_trade=p.max_equity_per_trade)
                if sz["qty"] <= 0 or sz["notional"] < 10:
                    continue
                fee = sz["notional"] * FEE_RATE
                cash -= sz["notional"] + fee
                tr = Trade(s, ts, entry, sl, entry * (1 + p.tp_pct), sz["qty"], sz["risk_amount"], fees=fee)
                tr.e_ret24 = float(f)   # lưu funding lúc vào để phân tích
                tr.e_hour = int(ts.hour)
                open_pos[s] = {"trade": tr, "bars": 0, "peak": entry}

        curve.append((ts, equity_at(ts)))

    if timeline:
        last = timeline[-1]
        for s, pp in list(open_pos.items()):
            i = pos_index[s].get(last)
            tr = pp["trade"]
            px = float(sig[s]["close"].iloc[i]) if i is not None else tr.entry
            fee = px * tr.qty * FEE_RATE
            tr.exit_time, tr.exit, tr.reason = last, px, "EndOfData"
            tr.fees += fee; cash += tr.qty * px - fee; closed.append(tr)

    ec = pd.Series(dict(curve)).sort_index() if curve else pd.Series(dtype=float)
    return Result(ec, closed, p, initial_capital)
