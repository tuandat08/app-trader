"""
Backtest DCA + MARGIN (theo ý tưởng Sheet3: khi rớt thì vừa mua spot vừa SHORT margin).

Mô hình (xấp xỉ, đủ để thấy rủi ro):
  - Spot: bình quân giá xuống như bản DCA thường.
  - Mỗi lần rớt 'drop_step' và mua thêm 1 tầng spot → đồng thời MỞ SHORT margin
    (mượn coin bán ra) với notional = 1 tầng, đòn bẩy 'leverage' (collateral = notional/leverage).
  - Short LỜI khi giá giảm tiếp (bù lỗ cho spot), LỖ khi giá bật lên.
  - Đóng toàn bộ short khi giá bật lên 'tp_pct' so với giá mở short gần nhất, hoặc khi spot chốt lời.
  - THANH LÝ: nếu giá bật lên đủ để lỗ short vượt collateral → cháy phần margin (mất sạch collateral).

Đây chính là chỗ nguy hiểm: margin bù được lúc sập, nhưng khi thị trường HỒI/ TĂNG mạnh
thì short lỗ liên tục và có thể bị thanh lý.
"""
import pandas as pd

FEE = 0.001


def dca_margin_backtest(close: pd.Series, capital=1000.0, n_tranches=10,
                        drop_step=0.03, tp_pct=0.01, leverage=3.0):
    tranche_cash = capital / n_tranches
    cash = capital
    sqty = 0.0; scost = 0.0; used = 0; last_buy = None; max_used = 0
    # short margin (gộp)
    short_qty = 0.0; short_proceeds = 0.0; short_coll = 0.0; last_short = None
    liquidations = 0
    curve = []; cycles = []; peak = capital; maxdd = 0.0

    def acct_equity(price):
        short_pnl = short_proceeds - short_qty * price          # + nếu giá giảm dưới giá short
        return cash + sqty * price + short_coll + short_pnl

    def open_short(price, notional):
        nonlocal cash, short_qty, short_proceeds, short_coll, last_short
        coll = notional / leverage
        if cash < coll:
            return
        q = notional / price
        cash -= coll
        short_coll += coll
        short_qty += q
        short_proceeds += q * price * (1 - FEE)
        last_short = price

    def close_shorts(price):
        nonlocal cash, short_qty, short_proceeds, short_coll, last_short
        if short_qty <= 0:
            return
        pnl = short_proceeds - short_qty * price * (1 + FEE)
        cash += short_coll + pnl
        short_qty = 0.0; short_proceeds = 0.0; short_coll = 0.0; last_short = None

    def buy_spot(price):
        nonlocal cash, sqty, scost, used, last_buy, max_used
        spend = min(tranche_cash, cash)
        if spend < 1:
            return False
        q = (spend / price) * (1 - FEE)
        cash -= spend; sqty += q; scost += spend; used += 1; last_buy = price
        max_used = max(max_used, used)
        return True

    for t, price in close.items():
        # 1) Kiểm tra thanh lý short
        if short_qty > 0:
            loss = short_qty * price - short_proceeds            # lỗ short (giá bật lên)
            if loss >= short_coll:
                liquidations += 1
                short_qty = 0.0; short_proceeds = 0.0; short_coll = 0.0; last_short = None  # cháy sạch collateral

        eq = acct_equity(price); peak = max(peak, eq); maxdd = min(maxdd, eq / peak - 1)
        curve.append((t, eq))

        if used == 0:
            buy_spot(price)
        else:
            avg = scost / sqty
            if price >= avg * (1 + tp_pct):                      # spot chốt lời → bán hết + đóng short
                proceeds = sqty * price * (1 - FEE)
                cycles.append({"exit_time": str(t)[:19], "profit": round(proceeds - scost, 2), "tranches": used})
                cash += proceeds; sqty = 0.0; scost = 0.0; used = 0; last_buy = None
                close_shorts(price)
            elif used < n_tranches and last_buy and price <= last_buy * (1 - drop_step):
                buy_spot(price)
                open_short(price, tranche_cash)                  # rớt → mua spot + short margin
            elif short_qty > 0 and last_short and price >= last_short * (1 + tp_pct):
                close_shorts(price)                              # giá bật 1% → chốt margin

    last_price = float(close.iloc[-1])
    final_equity = acct_equity(last_price)
    return {
        "capital": capital, "final_equity": round(final_equity, 2),
        "total_return": round((final_equity / capital - 1) * 100, 2),
        "max_drawdown": round(maxdd * 100, 2),
        "n_cycles": len(cycles), "cycle_profit": round(sum(c["profit"] for c in cycles), 2),
        "liquidations": liquidations, "leverage": leverage,
        "max_tranches_used": max_used, "still_holding": used > 0,
        "curve": curve, "cycles": cycles,
    }


def print_report(r, days=None):
    line = "─" * 64
    print(line); print(f"  BACKTEST DCA + MARGIN (đòn bẩy {r['leverage']}x)"); print(line)
    print(f"  Vốn: ${r['capital']:,.0f} → ${r['final_equity']:,.2f}  ({r['total_return']:+.2f}%"
          + (f" ~{r['total_return']/(days/365):.1f}%/năm)" if days else ")"))
    print(f"  ⚠️ Drawdown tối đa : {r['max_drawdown']:.2f}%")
    print(f"  Số lần THANH LÝ margin (cháy): {r['liquidations']}   ← rủi ro chết người")
    print(f"  Chu kỳ chốt lời   : {r['n_cycles']} (${r['cycle_profit']:+.2f})")
    print(f"  Tầng dùng nhiều nhất: {r['max_tranches_used']}/10")
    print(line)
    return r
