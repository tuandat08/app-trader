"""
Chạy DCA CẢI TIẾN trên dữ liệu Binance thật (nên dùng BTC/USDT, giai đoạn dài).

Ví dụ:
    python run_dca_improved.py --symbol BTC/USDT --days 1460 --tf 4h
    python run_dca_improved.py --symbol ETH/USDT --days 1460 --no-trend   # so sánh khi tắt lọc xu hướng
"""
import argparse
import pandas as pd
from dca_improved import dca_improved


def main():
    ap = argparse.ArgumentParser(description="Backtest DCA cải tiến (spot, lọc xu hướng, trailing TP)")
    ap.add_argument("--symbol", default="BTC/USDT")
    ap.add_argument("--days", type=int, default=1460)      # ~4 năm
    ap.add_argument("--tf", default="4h")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--tranches", type=int, default=10)
    ap.add_argument("--drop", type=float, default=3.0)
    ap.add_argument("--tp", type=float, default=1.0)
    ap.add_argument("--trend-ema", type=int, default=200)
    ap.add_argument("--trail", type=float, default=2.0)
    ap.add_argument("--no-trend", action="store_true", help="tắt lọc xu hướng (để so sánh)")
    ap.add_argument("--no-trail", action="store_true", help="tắt trailing, chốt cứng")
    args = ap.parse_args()

    from data import fetch_ohlcv, make_exchange
    ex = make_exchange()
    print(f"Tải {args.symbol} {args.tf} {args.days} ngày…")
    df = fetch_ohlcv(args.symbol, args.tf, args.days, exchange=ex)
    r = dca_improved(df["close"], capital=args.capital, n_tranches=args.tranches,
                     drop_step=args.drop / 100, tp_pct=args.tp / 100,
                     use_trend=not args.no_trend, trend_ema=args.trend_ema,
                     use_trail=not args.no_trail, trail_pct=args.trail / 100)

    yrs = args.days / 365
    line = "─" * 64
    print(line); print(f"  DCA CẢI TIẾN — {args.symbol} ({args.days} ngày ~{yrs:.1f} năm)"); print(line)
    print(f"  Lọc xu hướng: {'BẬT (EMA '+str(args.trend_ema)+')' if not args.no_trend else 'TẮT'}"
          f"  ·  Trailing: {'BẬT '+str(args.trail)+'%' if not args.no_trail else 'TẮT'}")
    print(line)
    print(f"  Vốn ${r['capital']:,.0f} → ${r['final_equity']:,.2f}")
    print(f"  DCA cải tiến   : {r['total_return']:+.1f}%  (~{((1+r['total_return']/100)**(1/yrs)-1)*100:.1f}%/năm)")
    print(f"  ⚠️ Drawdown tối đa: {r['max_drawdown']:.1f}%")
    print(f"  So với GIỮ (hold): {r['buyhold_return']:+.1f}%  (~{((1+r['buyhold_return']/100)**(1/yrs)-1)*100:.1f}%/năm)")
    print(f"  Số chu kỳ chốt lời: {r['n_cycles']} (${r['cycle_profit']:+.2f})")
    print(f"  Tầng dùng nhiều nhất: {r['max_tranches_used']}/{args.tranches}"
          + ("  · CUỐI KỲ CÒN GIỮ HÀNG" if r['still_holding'] else "  · cuối kỳ đã chốt hết"))
    print(line)
    if r["total_return"] < r["buyhold_return"]:
        print("  → DCA vẫn THUA việc chỉ giữ tài sản (bình thường trong thị trường tăng).")
    else:
        print("  → DCA THẮNG giữ tài sản ở giai đoạn này (thường do có bear lớn giữa kỳ).")
    print(line)

    if r["cycles"]:
        pd.DataFrame(r["cycles"]).to_csv("dca_improved_cycles.csv", index=False)
        pd.Series(dict(r["curve"])).to_csv("dca_improved_equity.csv")
        print("Đã lưu: dca_improved_cycles.csv, dca_improved_equity.csv")


if __name__ == "__main__":
    main()
