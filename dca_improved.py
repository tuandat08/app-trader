"""
DCA spot CẢI TIẾN — vá các lỗi logic của thuật toán gốc:
  - Chỉ mua khi GIẢM (bỏ mua-khi-tăng vô nghĩa), không margin.
  - Chốt lời TRAILING (để lời chạy trong sóng tăng) thay vì cắt cứng +1%.
  - Lọc xu hướng: chỉ mở/nạp tầng khi giá > EMA dài (uptrend); rơi xuống downtrend thì
    NGỪNG nạp thêm → giữ đạn, tránh đổ hết vốn vào cú sập.
"""
import pandas as pd

FEE = 0.001


def _ema(s, span):
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def dca_improved(close: pd.Series, capital=1000.0, n_tranches=10, drop_step=0.03,
                 tp_pct=0.01, use_trend=True, trend_ema=200,
                 use_trail=True, trail_pct=0.02):
    e = _ema(close, trend_ema) if use_trend else None
    tranche_cash = capital / n_tranches
    cash = capital
    qty = 0.0; cost = 0.0; used = 0; last_buy = None
    tp_peak = None                      # đỉnh giá sau khi đã có lời (cho trailing)
    curve = []; cycles = []; peak = capital; maxdd = 0.0; max_used = 0

    def buy(price):
        nonlocal cash, qty, cost, used, last_buy, max_used
        spend = min(tranche_cash, cash)
        if spend < 1:
            return
        qty += (spend / price) * (1 - FEE)
        cash -= spend; cost += spend; used += 1; last_buy = price
        max_used = max(max_used, used)

    def sell_all(price, t):
        nonlocal cash, qty, cost, used, last_buy, tp_peak
        proceeds = qty * price * (1 - FEE)
        cycles.append({"exit_time": str(t)[:19], "profit": round(proceeds - cost, 2), "tranches": used})
        cash += proceeds; qty = 0.0; cost = 0.0; used = 0; last_buy = None; tp_peak = None

    vals = list(close.items())
    for i, (t, price) in enumerate(vals):
        equity = cash + qty * price
        peak = max(peak, equity); maxdd = min(maxdd, equity / peak - 1)
        curve.append((t, equity))
        trend_ok = True if e is None else (not pd.isna(e.iloc[i]) and price > e.iloc[i])

        if used == 0:
            if trend_ok:
                buy(price)                                   # chỉ mở giỏ khi uptrend
        else:
            avg = cost / qty
            in_profit = price >= avg * (1 + tp_pct)
            if use_trail:
                if in_profit:
                    tp_peak = max(tp_peak or price, price)
                    if price <= tp_peak * (1 - trail_pct):   # lời rồi, giá quay đầu → chốt hết
                        sell_all(price, t)
                elif used < n_tranches and last_buy and price <= last_buy * (1 - drop_step) and trend_ok:
                    buy(price)                               # bình quân xuống (chỉ khi còn uptrend)
            else:
                if in_profit:
                    sell_all(price, t)
                elif used < n_tranches and last_buy and price <= last_buy * (1 - drop_step) and trend_ok:
                    buy(price)

    last_price = float(close.iloc[-1])
    final_equity = cash + qty * last_price
    return {
        "capital": capital, "final_equity": round(final_equity, 2),
        "total_return": round((final_equity / capital - 1) * 100, 2),
        "max_drawdown": round(maxdd * 100, 2),
        "n_cycles": len(cycles), "cycle_profit": round(sum(c["profit"] for c in cycles), 2),
        "max_tranches_used": max_used, "still_holding": used > 0,
        "buyhold_return": round((last_price / float(close.iloc[0]) - 1) * 100, 2),
        "curve": curve, "cycles": cycles,
    }
