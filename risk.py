"""
Quản trị rủi ro dùng chung — tính khối lượng lệnh và các giới hạn danh mục.
Tách riêng để backtest và live dùng cùng một logic.
"""
from dataclasses import dataclass


def position_size(equity: float, entry: float, sl: float, risk_per_trade: float,
                  cash_available: float, max_equity_per_trade: float = 0.0) -> dict:
    """
    Trả về {'qty', 'notional', 'risk_amount'} theo quy tắc rủi ro cố định.
      - risk_amount = equity * risk_per_trade
      - qty = risk_amount / (entry - sl)
      - Không đòn bẩy: notional không vượt quá tiền mặt khả dụng.
      - V2 max_equity_per_trade > 0: TRẦN vốn/lệnh = equity * tỷ lệ này. Khi SL quá hẹp,
        rủi ro 2% có thể đòi dùng 40% ví → hàm min chặn lại, chỉ cho dùng tối đa trần này
        (chống bẫy thanh khoản). Rủi ro thực khi đó sẽ NHỎ hơn 2%.
    """
    if entry <= sl:
        return {"qty": 0.0, "notional": 0.0, "risk_amount": 0.0}
    risk_amount = equity * risk_per_trade
    risk_per_unit = entry - sl
    qty = risk_amount / risk_per_unit
    notional = qty * entry
    # Trần vốn: min(tiền mặt, equity * max_equity_per_trade)
    cap = cash_available
    if max_equity_per_trade and max_equity_per_trade > 0:
        cap = min(cap, equity * max_equity_per_trade)
    if notional > cap:
        qty = cap / entry
        notional = qty * entry
        risk_amount = qty * risk_per_unit  # rủi ro thực sau khi thu nhỏ
    return {"qty": qty, "notional": notional, "risk_amount": risk_amount}


@dataclass
class DailyStop:
    """Theo dõi ngưng lỗ trong ngày (UTC)."""
    threshold: float                 # ví dụ 0.05 = 5%
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


def total_drawdown_exceeded(peak_equity: float, equity: float, max_dd: float) -> bool:
    """True nếu sụt giảm từ đỉnh vượt ngưỡng (dùng cho kill-switch tự động)."""
    if peak_equity <= 0:
        return False
    return (equity / peak_equity - 1.0) <= -abs(max_dd)
