"""
CLI chạy backtest chiến lược Swing Stoch RSI trên dữ liệu Binance.

Ví dụ:
    python run.py --symbols SOL/USDT AVAX/USDT LINK/USDT --days 180 --capital 1000
    python run.py --gainers 10 --days 120        # tự lấy top gainer đã lọc

Bước đầu tiên nên chạy:
    python selftest.py     # kiểm tra logic bằng dữ liệu giả lập, không cần internet
"""
import argparse
import pandas as pd

from strategy import Params
from backtest import run_backtest, print_report


def main():
    ap = argparse.ArgumentParser(description="Backtest chiến lược Swing Stoch RSI (Binance)")
    ap.add_argument("--symbols", nargs="*", default=["SOL/USDT", "AVAX/USDT", "LINK/USDT"],
                    help="Danh sách cặp coin (vd: SOL/USDT AVAX/USDT)")
    ap.add_argument("--gainers", type=int, default=0,
                    help="Nếu >0: bỏ qua --symbols, tự lấy N top gainer đã lọc an toàn")
    ap.add_argument("--days", type=int, default=180, help="Số ngày dữ liệu lịch sử")
    ap.add_argument("--capital", type=float, default=1000.0, help="Vốn ban đầu (USDT)")
    ap.add_argument("--risk", type=float, default=0.02, help="Rủi ro mỗi lệnh (0.02 = 2%%)")
    ap.add_argument("--tp", type=float, default=0.03, help="Take Profit (0.03 = 3%%)")
    ap.add_argument("--sl", type=float, default=0.02, help="Stop Loss tối đa (0.02 = 2%%)")
    ap.add_argument("--max-open", type=int, default=3, help="Số lệnh mở đồng thời tối đa")
    args = ap.parse_args()

    from data import fetch_ohlcv, top_gainers  # import muộn để selftest không cần ccxt

    symbols = top_gainers(args.gainers) if args.gainers > 0 else args.symbols
    print(f"Cặp giao dịch: {symbols}")

    data = {}
    for sym in symbols:
        print(f"  Tải {sym} ...")
        h1 = fetch_ohlcv(sym, "1h", args.days)
        d1 = fetch_ohlcv(sym, "1d", args.days + 10)
        data[sym] = (h1, d1)

    p = Params(tp_pct=args.tp, max_sl_pct=args.sl,
               risk_per_trade=args.risk, max_open_trades=args.max_open)
    res = run_backtest(data, p, initial_capital=args.capital)
    print_report(res)

    # Lưu nhật ký lệnh
    if res.trades:
        rows = [{
            "symbol": t.symbol, "entry_time": t.entry_time, "entry": t.entry,
            "sl": t.sl, "tp": t.tp, "qty": t.qty, "exit_time": t.exit_time,
            "exit": t.exit, "reason": t.reason, "pnl": t.pnl, "R": t.r_multiple,
        } for t in res.trades]
        pd.DataFrame(rows).to_csv("trade_log.csv", index=False)
        print("Đã lưu nhật ký lệnh -> trade_log.csv")


if __name__ == "__main__":
    main()
