"""Engine backtest event-driven (long-only, Spot). Trailing/stall/gain-filter + chọn động top gainer."""
from dataclasses import dataclass
from typing import Dict, Tuple, List
import pandas as pd

from strategy import Params, compute_signals
from risk import position_size, DailyStop

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
    e_ret24: float = None
    e_osdepth: float = None
    e_hour: int = None
    bars_held: int = 0

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
    """Ma trận bool: tại mỗi nến, coin nằm top-N tăng 24h (không nhìn trước) & (min_ret, max_ret]."""
    rets = {}
    for s, (h1, _) in data.items():
        rets[s] = h1["close"] / h1["close"].shift(lookback_h) - 1.0
    wide = pd.DataFrame(rets).sort_index()
    rank = wide.rank(axis=1, ascending=False, method="first")
    elig = (rank <= top_n) & (wide > min_ret) & (wide <= max_ret)
    return elig.fillna(False)


def run_backtest(data: Dict[str, Tuple[pd.DataFrame, pd.DataFrame]], p: Params,
                 initial_capital: float = 1000.0, eligible: pd.DataFrame = None) -> Result:
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
            pp["peak"] = max(pp.get("peak", tr.entry), float(row["high"]))
            ex, reason = None, ""
            if p.use_trailing:
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
                cash += tr.qty * ex - exit_fee
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
                if eligible is not None:
                    try:
                        if not bool(eligible.at[ts, s]):
                            continue
                    except (KeyError, IndexError):
                        continue
                row = sig[s].iloc[i]
                entry = float(row["close"])
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
                cash -= sz["notional"] + fee
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
        exit_fee = px * pp["trade"].qty * FEE_RATE
        tr = pp["trade"]; tr.exit_time, tr.exit, tr.reason = last, px, "EndOfData"
        tr.fees += exit_fee
        cash += tr.qty * px - exit_fee; closed.append(tr)

    ec = pd.Series(dict(curve)).sort_index()
    return Result(ec, closed, p, initial_capital)
