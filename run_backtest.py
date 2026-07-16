"""GĐ1 — Backtest + kiểm định trên dữ liệu Binance thật."""
import argparse
import pandas as pd
from strategy import Params
from backtest import run_backtest, gainer_eligibility
from metrics import print_report
from validate import export_equity_curve, export_monthly, walk_forward


def main():
    ap = argparse.ArgumentParser(description="Backtest Swing Stoch RSI")
    ap.add_argument("--symbols", nargs="*", default=["SOL/USDT", "AVAX/USDT", "LINK/USDT"])
    ap.add_argument("--gainers", type=int, default=0)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--risk", type=float, default=0.02)
    ap.add_argument("--tp", type=float, default=0.03)
    ap.add_argument("--sl", type=float, default=0.02)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--walk", type=int, default=0)
    args = ap.parse_args()

    from data import fetch_ohlcv, top_symbols_by_volume, make_exchange
    ex = make_exchange()
    symbols = top_symbols_by_volume(args.gainers, exchange=ex) if args.gainers > 0 else args.symbols
    print(f"Cặp: {symbols}")
    data = {}
    for s in symbols:
        print(f"  Tải {s} ...")
        data[s] = (fetch_ohlcv(s, "1h", args.days, exchange=ex),
                   fetch_ohlcv(s, "1d", args.days + 10, exchange=ex))
    p = Params(tp_pct=args.tp, max_sl_pct=args.sl, risk_per_trade=args.risk,
               use_trend_filter=True, use_trailing=True, use_stall_exit=True, use_gain_filter=True)
    elig = gainer_eligibility(data, top_n=args.top_n)
    res = run_backtest(data, p, initial_capital=args.capital, eligible=elig)
    print_report(res)
    export_equity_curve(res); export_monthly(res)
    if args.walk > 1:
        print(walk_forward(data, splits=args.walk, p=p, initial_capital=args.capital).to_string(index=False))


if __name__ == "__main__":
    main()
