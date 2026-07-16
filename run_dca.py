"""
Chạy backtest DCA spot trên dữ liệu Binance thật.

Ví dụ:
    python run_dca.py --symbol BTC/USDT --days 1460 --tranches 10 --drop 3 --tp 1

Nên chạy trên giai đoạn DÀI có cả cú sập (2021-2024 gồm bear 2022) để thấy rủi ro thật.
"""
import argparse
from dca_backtest import dca_backtest, print_report


def main():
    ap = argparse.ArgumentParser(description="Backtest DCA spot")
    ap.add_argument("--symbol", default="BTC/USDT")
    ap.add_argument("--days", type=int, default=1460)   # ~4 năm
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--tranches", type=int, default=10)
    ap.add_argument("--drop", type=float, default=3.0, help="giảm %% thì mua thêm tầng")
    ap.add_argument("--tp", type=float, default=1.0, help="vượt giá TB %% thì chốt hết")
    ap.add_argument("--tf", default="4h", help="khung nến (1h/4h/1d)")
    args = ap.parse_args()

    from data import fetch_ohlcv, make_exchange
    ex = make_exchange()
    print(f"Tải {args.symbol} {args.tf} {args.days} ngày…")
    df = fetch_ohlcv(args.symbol, args.tf, args.days, exchange=ex)
    r = dca_backtest(df["close"], capital=args.capital, n_tranches=args.tranches,
                     drop_step=args.drop / 100, tp_pct=args.tp / 100)
    print_report(r, days=args.days)

    if r["cycles"]:
        import pandas as pd
        pd.DataFrame(r["cycles"]).to_csv("dca_cycles.csv", index=False)
        pd.Series(dict(r["curve"])).to_csv("dca_equity.csv")
        print("Đã lưu: dca_cycles.csv, dca_equity.csv")


if __name__ == "__main__":
    main()
