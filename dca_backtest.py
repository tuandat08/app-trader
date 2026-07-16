"""
Backtester cho chiến lược DCA SPOT (bình quân giá xuống — ý tưởng "BOT TRADE").

Quy tắc (phiên bản spot, KHÔNG margin):
  - Chia vốn làm n_tranches phần bằng nhau (vd 10 phần, mỗi phần 10%).
  - Mua tầng đầu tiên ngay.
  - Nếu giá GIẢM 'drop_step' (vd 3%) so với lần mua gần nhất → mua thêm 1 tầng (bình quân xuống),
    cho tới khi dùng hết n_tranches.
  - Khi giá VƯỢT giá trung bình 'tp_pct' (vd 1%) → BÁN HẾT, chốt lời, quay lại từ đầu.
  - Nếu giá cứ giảm và đã vào hết tầng → GIỮ (spot không bị thanh lý) và chờ hồi. Đây là rủi ro:
    vốn kẹt dưới đáy trong drawdown sâu/dài.

Chỉ số quan trọng cần nhìn: MAX DRAWDOWN (sụt giá trị tài khoản) và có bị "kẹt đáy" cuối kỳ không —
KHÔNG chỉ nhìn tổng lời, vì martingale/DCA đẹp cho tới đúng cú sập.
"""
import pandas as pd

FEE = 0.001  # 0.1% mỗi lần khớp (Binance spot)


def dca_backtest(close: pd.Series, capital=1000.0, n_tranches=10,
                 drop_step=0.03, tp_pct=0.01):
    tranche_cash = capital / n_tranches
    cash = capital
    qty = 0.0        # số coin đang giữ
    cost = 0.0       # tổng USDT đã bỏ ra cho vị thế hiện tại (gồm phí)
    used = 0         # số tầng đã vào
    last_buy = None
    curve = []
    cycles = []
    peak = capital
    maxdd = 0.0
    max_tranches_used = 0

    def buy(price):
        nonlocal cash, qty, cost, used, last_buy, max_tranches_used
        spend = min(tranche_cash, cash)
        if spend < 1:
            return False
        q = (spend / price) * (1 - FEE)
        cash -= spend
        qty += q
        cost += spend
        used += 1
        last_buy = price
        max_tranches_used = max(max_tranches_used, used)
        return True

    for t, price in close.items():
        equity = cash + qty * price
        peak = max(peak, equity)
        maxdd = min(maxdd, equity / peak - 1)
        curve.append((t, equity))

        if used == 0:
            buy(price)
        else:
            avg = cost / qty if qty > 0 else price
            if price >= avg * (1 + tp_pct):                       # chốt lời: bán hết
                proceeds = qty * price * (1 - FEE)
                cycles.append({"exit_time": str(t)[:19], "profit": round(proceeds - cost, 2),
                               "tranches": used, "price": round(float(price), 2)})
                cash += proceeds
                qty = 0.0; cost = 0.0; used = 0; last_buy = None
            elif used < n_tranches and last_buy and price <= last_buy * (1 - drop_step):
                buy(price)                                        # bình quân xuống

    last_price = float(close.iloc[-1])
    final_equity = cash + qty * last_price
    return {
        "capital": capital, "final_equity": round(final_equity, 2),
        "total_return": round((final_equity / capital - 1) * 100, 2),
        "max_drawdown": round(maxdd * 100, 2),
        "n_cycles": len(cycles),
        "cycle_profit": round(sum(c["profit"] for c in cycles), 2),
        "max_tranches_used": max_tranches_used, "n_tranches": n_tranches,
        "still_holding": used > 0,
        "open_tranches": used,
        "open_avg": round(cost / qty, 2) if qty > 0 else None,
        "last_price": round(last_price, 2),
        "underwater_pct": round((last_price / (cost / qty) - 1) * 100, 2) if qty > 0 else 0.0,
        "curve": curve, "cycles": cycles,
    }


def print_report(r, days=None):
    line = "─" * 62
    print(line); print("  BACKTEST DCA SPOT — bình quân giá xuống"); print(line)
    print(f"  Vốn ban đầu        : ${r['capital']:,.2f}")
    print(f"  Vốn cuối kỳ        : ${r['final_equity']:,.2f}")
    print(f"  Tổng lợi nhuận     : {r['total_return']:+.2f}%" + (f"  (~{r['total_return']/ (days/365):.1f}%/năm)" if days else ""))
    print(f"  ⚠️ Drawdown tối đa : {r['max_drawdown']:.2f}%   ← nhìn kỹ con số này")
    print(f"  Số chu kỳ chốt lời : {r['n_cycles']} (tổng lời ${r['cycle_profit']:+.2f})")
    print(f"  Tầng dùng nhiều nhất: {r['max_tranches_used']}/{r['n_tranches']}")
    if r["still_holding"]:
        print(f"  ⚠️ CUỐI KỲ CÒN KẸT : {r['open_tranches']} tầng, giá TB ${r['open_avg']}, "
              f"giá hiện tại ${r['last_price']} → đang lỗ {r['underwater_pct']:.1f}%")
    else:
        print(f"  Cuối kỳ           : không còn vị thế mở (đã chốt hết)")
    print(line)
    verdict = ("NGUY HIỂM: drawdown quá sâu / kẹt đáy — dễ cháy khi thị trường sập"
               if r["max_drawdown"] <= -30 or (r["still_holding"] and r["underwater_pct"] <= -25)
               else "Tạm ổn trong giai đoạn này — nhưng phải test qua NHIỀU cú sập lớn")
    print(f"  Nhận định: {verdict}")
    print(line)
    return r
