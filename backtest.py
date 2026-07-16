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
                elif row["k"] > p.ob_level and row["d"] > p.ob_level and row["cross_down"]:
                    ex, reason = float(row["close"]), "Reversal"
                elif p.use_stall_exit and pp["bars"] >= p.stall_bars and float(row["close"]) <= tr.entry:
                    ex, reason = float(row["close"]), "Stall"
                elif pp["bars"] >= p.max_hold_bars:
                    ex, reason = float(row["close"]), "TimeStop"
            else:
                if row["low"] <= tr.sl:
                    ex, reason = tr.sl, "SL"
                elif row["high"] >= tr.tp:
                    ex, reason = tr.tp, "TP"
                elif row["k"] > p.ob_level and row["d"] > p.ob_level and row["cross_down"]:
                    ex, reason = float(row["close"]), "Reversal"
                elif p.use_stall_exit and pp["bars"] >= p.stall_bars and float(row["close"]) <= tr.entry:
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
                sz = position_size(eq, entry, sl, p.risk_per_trade, cash)
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
