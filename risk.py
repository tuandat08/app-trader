"""Quản trị rủi ro dùng chung — sizing 2%/lệnh, ngưng lỗ ngày, kill drawdown."""
from dataclasses import dataclass


def position_size(equity, entry, sl, risk_per_trade, cash_available) -> dict:
    if entry <= sl:
        return {"qty": 0.0, "notional": 0.0, "risk_amount": 0.0}
    risk_amount = equity * risk_per_trade
    risk_per_unit = entry - sl
    qty = risk_amount / risk_per_unit
    notional = qty * entry
    if notional > cash_available:
        qty = cash_available / entry
        notional = qty * entry
        risk_amount = qty * risk_per_unit
    return {"qty": qty, "notional": notional, "risk_amount": risk_amount}


@dataclass
class DailyStop:
    threshold: float
    _day = None
    _day_start_equity: float = 0.0
    blocked: bool = False

    def update(self, day, equity: float):
        if day != self._day:
            self._day = day
            self._day_start_equity = equity
            self.blocked = False
        if not self.blocked and equity <= self._day_start_equity * (1 - self.threshold):
            self.blocked = True
        return self.blocked


def total_drawdown_exceeded(peak_equity, equity, max_dd) -> bool:
    if peak_equity <= 0:
        return False
    return (equity / peak_equity - 1.0) <= -abs(max_dd)
