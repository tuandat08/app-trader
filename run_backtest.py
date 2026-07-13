"""
GIAI ĐOẠN 1 — Chạy backtest + kiểm định trên dữ liệu Binance thật.

Ví dụ:
    python run_backtest.py --symbols SOL/USDT AVAX/USDT LINK/USDT --days 180
    python run_backtest.py --gainers 10 --days 120 --walk 3
"""
import argparse
import pandas as pd

from strategy import Params
from backtest import run_backtest, Trade
from metrics import print_report
from validate import export_equity_curve, export_monthly, walk_forward, print_walk_forward


def main():
    ap = argparse.ArgumentParser(description="Backtest & kiểm định chiến lược Swing Stoch RSI")
    ap.add_argument("--symbols", nargs="*", default=["SOL/USDT", "AVAX/USDT", "LINK/USDT"])
    ap.add_argument("--gainers", type=int, default=0)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--risk", type=float, default=0.02)
    ap.add_argument("--tp", type=float, default=0.03)
    ap.add_argument("--sl", type=float, default=0.02)
    ap.add_argument("--max-open", type=int, default=3)
    ap.add_argument("--walk", type=int, default=0, help="Số đoạn walk-forward (0 = bỏ qua)")
    args = ap.parse_args()

    from data import fetch_ohlcv, top_gainers, make_exchange
    ex = make_exchange()
    symbols = top_gainers(args.gainers, exchange=ex) if args.gainers > 0 else args.symbols
    print(f"Cặp giao dịch: {symbols}")

    data = {}
    for s in symbols:
        print(f"  Tải {s} ...")
        data[s] = (fetch_ohlcv(s, "1h", args.days, exchange=ex),
                   fetch_ohlcv(s, "1d", args.days + 10, exchange=ex))

    p = Params(tp_pct=args.tp, max_sl_pct=args.sl,
               risk_per_trade=args.risk, max_open_trades=args.max_open)
    res = run_backtest(data, p, initial_capital=args.capital)
    print_report(res)

    export_equity_curve(res)
    _, mt = export_monthly(res)
    print("\n── Lợi nhuận theo tháng ──")
    print(mt.to_string(index=False) if not mt.empty else "  (chưa có lệnh)")

    if args.walk > 1:
        print_walk_forward(walk_forward(data, splits=args.walk, p=p, initial_capital=args.capital))

    if res.trades:
        pd.DataFrame([{
            "symbol": t.symbol, "entry_time": t.entry_time, "entry": t.entry,
            "sl": t.sl, "tp": t.tp, "qty": t.qty, "exit_time": t.exit_time,
            "exit": t.exit, "reason": t.reason, "pnl": t.pnl, "R": t.r_multiple,
        } for t in res.trades]).to_csv("trade_log.csv", index=False)
        print("\nĐã lưu: trade_log.csv, equity_curve.csv, monthly_returns.csv")


if __name__ == "__main__":
    main()
