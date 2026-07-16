"""
Kiểm thử OFFLINE toàn bộ pipeline — không cần internet, không cần ccxt.

Kiểm tra:
  1) Chỉ báo, tín hiệu, engine backtest + metrics + validate (dữ liệu giả lập).
  2) Module live (scanner, executor, risk) bằng một "sàn giả" (FakeExchange) ở chế độ dry_run.

LƯU Ý: số liệu là DỮ LIỆU NGẪU NHIÊN, chỉ để xác nhận code chạy đúng — KHÔNG phản ánh
hiệu quả thật. Kết quả thật: python run_backtest.py --symbols ...
"""
import time
import numpy as np
import pandas as pd

from strategy import Params, compute_signals, latest_signal
from backtest import run_backtest
from metrics import print_report, monthly_table
from validate import walk_forward, print_walk_forward
from risk import position_size, DailyStop, total_drawdown_exceeded


# ---------- dữ liệu giả lập ----------
def synth(n_hours, seed, start=100.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n_hours, freq="h", tz="UTC")
    price = np.zeros(n_hours); price[0] = start
    trend = np.linspace(0, 0.25, n_hours); x = 0.0
    for i in range(1, n_hours):
        x = 0.9 * x + rng.normal(0, 0.015)
        price[i] = start * (1 + trend[i]) * (1 + x)
    price = np.maximum(price, 1.0)
    close = price; open_ = np.concatenate([[close[0]], close[:-1]])
    noise = np.abs(rng.normal(0, 0.004, n_hours)) * close
    high = np.maximum(open_, close) + noise
    low = np.minimum(open_, close) - noise
    vol = rng.uniform(1e5, 5e5, n_hours)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": vol}, index=idx)


def to_daily(h1):
    return h1.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                  "close": "last", "volume": "sum"}).dropna()


# ---------- sàn giả cho phần live ----------
class FakeExchange:
    rateLimit = 0
    def __init__(self):
        self._h1 = {s: synth(24 * 90, seed=i + 10, start=50 + 10 * i)
                    for i, s in enumerate(["AAA/USDT", "BBB/USDT"])}
    def milliseconds(self): return int(time.time() * 1000)
    def parse_timeframe(self, tf): return {"1h": 3600, "1d": 86400}[tf]
    def _klines(self, df):
        out = []
        for ts, r in df.iterrows():
            out.append([int(ts.timestamp() * 1000), r.open, r.high, r.low, r.close, r.volume])
        return out
    def fetch_ohlcv(self, symbol, timeframe="1h", since=None, limit=500):
        df = self._h1[symbol]
        if timeframe == "1d":
            df = to_daily(df)
        return self._klines(df)[-limit:]
    def fetch_ticker(self, symbol): return {"last": float(self._h1[symbol]["close"].iloc[-1])}
    def amount_to_precision(self, s, q): return round(q, 4)
    def price_to_precision(self, s, p): return round(p, 4)


def main():
    print("### 1) BACKTEST + KIỂM ĐỊNH (offline) ###")
    data = {s: (h1 := synth(24 * 120, seed=i + 1, start=100 + 20 * i), to_daily(h1))
            for i, s in enumerate(["AAA/USDT", "BBB/USDT", "CCC/USDT"])}
    total_sig = sum(int(compute_signals(h1, d1, Params())["entry_signal"].sum())
                    for (h1, d1) in data.values())
    print(f"[selftest] Tổng tín hiệu vào lệnh: {total_sig}")
    res = run_backtest(data, Params(), initial_capital=1000.0)
    print_report(res)
    assert len(res.equity_curve) > 0
    print("[selftest] monthly_table rows:", len(monthly_table(res)))
    print_walk_forward(walk_forward(data, splits=3))

    print("\n### 2) MODULE LIVE (offline, dry_run) ###")
    # risk
    sz = position_size(1000, 100, 98, 0.02, 1000)
    assert sz["qty"] > 0 and abs(sz["risk_amount"] - 20) < 1e-6, sz
    print(f"[selftest] position_size OK: {sz}")
    ds = DailyStop(0.05)
    assert ds.update("2024-01-01", 1000) is False
    assert ds.update("2024-01-01", 940) is True   # lỗ 6% > 5%
    print("[selftest] DailyStop OK")
    assert total_drawdown_exceeded(1000, 790, 0.20) is True
    print("[selftest] drawdown kill OK")

    # scanner + executor với sàn giả
    from config import Config
    from monitor import setup_logger, Notifier
    from scanner import scan
    from executor import Executor
    cfg = Config(); cfg.dry_run = True; cfg.mode = "testnet"; cfg.initial_capital = 1000.0
    ex = FakeExchange()
    note = Notifier(cfg, setup_logger("selftest.log"))
    signals = scan(["AAA/USDT", "BBB/USDT"], Params(), ex)
    print(f"[selftest] scan trả về {len(signals)} kết quả, ví dụ: "
          f"{ {k: signals[0][k] for k in ('symbol','signal','entry','sl','tp')} }")
    execu = Executor(ex, cfg, note)
    buy = execu.market_buy("AAA/USDT", 1.5)
    stop = execu.place_hard_stop("AAA/USDT", buy.qty, buy.price * 0.98)
    sell = execu.market_sell("AAA/USDT", buy.qty, "TP")
    assert buy.kind == "market_buy" and sell.kind == "market_sell"
    print("[selftest] Executor dry_run OK (buy/stop/sell)")

    print("\n[selftest] ✔ TẤT CẢ MODULE CHẠY KHÔNG LỖI.")
    print("[selftest] Nhắc lại: dữ liệu giả lập — chạy run_backtest.py để có số thật.")


if __name__ == "__main__":
    main()
