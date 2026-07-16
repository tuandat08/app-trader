"""Kiểm thử OFFLINE toàn pipeline (không cần internet/ccxt). Dữ liệu giả lập."""
import numpy as np
import pandas as pd

from strategy import Params, compute_signals
from backtest import run_backtest, gainer_eligibility
from metrics import print_report
from validate import walk_forward
from risk import position_size, DailyStop, total_drawdown_exceeded
from demo_data import demo_dataset


def main():
    print("### BACKTEST + KIỂM ĐỊNH (offline) ###")
    data = demo_dataset([f"C{i}/USDT" for i in range(10)], days=120)
    total = sum(int(compute_signals(h1, d1, Params())["entry_signal"].sum()) for (h1, d1) in data.values())
    print(f"[selftest] Tổng tín hiệu: {total}")
    res = run_backtest(data, Params(use_trend_filter=True, use_trailing=True), 1000,
                       eligible=gainer_eligibility(data, top_n=10))
    print_report(res)
    assert len(res.equity_curve) > 0
    print(walk_forward(data, splits=3).to_string(index=False))

    print("\n### RISK ###")
    sz = position_size(1000, 100, 98, 0.02, 1000)
    assert sz["qty"] > 0
    ds = DailyStop(0.05)
    assert ds.update("d", 1000) is False and ds.update("d", 940) is True
    assert total_drawdown_exceeded(1000, 790, 0.20) is True
    print("[selftest] risk OK")

    print("\n[selftest] ✔ TẤT CẢ MODULE CHẠY KHÔNG LỖI.")
    print("[selftest] Nhắc lại: dữ liệu giả lập — chạy run_backtest.py để có số thật.")


if __name__ == "__main__":
    main()
