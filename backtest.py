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


def run_backtest(data: Dict[str, Tuple[pd.DataFrame, pd.DataFrame]], p: Params,
                 initial_capital: float = 1000.0) -> Result:
    sig = {s: compute_signals(h1, d1, p) for s, (h1, d1) in data.items()}
    pos_index = {s: {ts: i for i, ts in enumerate(df.index)} for s, df in sig.items()}
    timeline = sorted(set().union(*[set(df.index) for df in sig.values()]))

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
            ex, reason = None, ""
            if row["low"] <= tr.sl:
                ex, reason = tr.sl, "SL"
            elif row["high"] >= tr.tp:
                ex, reason = tr.tp, "TP"
            elif row["k"] > p.ob_level and row["d"] > p.ob_level and row["cross_down"]:
                ex, reason = float(row["close"]), "Reversal"
            elif pp["bars"] >= p.max_hold_bars:
                ex, reason = float(row["close"]), "TimeStop"
            if ex is not None:
                tr.exit_time, tr.exit, tr.reason = ts, ex, reason
                tr.fees += ex * tr.qty * FEE_RATE
                cash += tr.qty * ex
                closed.append(tr); del open_pos[s]

        # 2) Ngưng lỗ ngày
        eq = equity_at(ts)
        blocked = dstop.update(ts.date(), eq)

        # 3) Vào lệnh
        if not blocked and len(open_pos) < p.max_open_trades:
            for s in sig.keys():
                if s in open_pos or len(open_pos) >= p.max_open_trades:
                    continue
                i = pos_index[s].get(ts)
                if i is None or i < 2 or not bool(sig[s].iloc[i]["entry_signal"]):
                    continue
                row = sig[s].iloc[i]
                entry = float(row["close"])
                sl = max(_swing_low(sig[s], i, p.swing_lookback), entry * (1 - p.max_sl_pct))
                if sl >= entry:
                    continue
                tp = entry * (1 + p.tp_pct)
                sz = position_size(eq, entry, sl, p.risk_per_trade, cash)
                if sz["qty"] <= 0 or sz["notional"] < 10:
                    continue
                fee = sz["notional"] * FEE_RATE
                cash -= sz["notional"]
                tr = Trade(s, ts, entry, sl, tp, sz["qty"], sz["risk_amount"], fees=fee)
                open_pos[s] = {"trade": tr, "bars": 0}

        curve.append((ts, equity_at(ts)))

    last = timeline[-1]
    for s, pp in list(open_pos.items()):
        i = pos_index[s].get(last)
        px = float(sig[s]["close"].iloc[i]) if i is not None else pp["trade"].entry
        tr = pp["trade"]; tr.exit_time, tr.exit, tr.reason = last, px, "EndOfData"
        tr.fees += px * tr.qty * FEE_RATE
        cash += tr.qty * px; closed.append(tr)

    ec = pd.Series(dict(curve)).sort_index()
    return Result(ec, closed, p, initial_capital)
