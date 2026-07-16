"""
GIAI ĐOẠN 2 — Chạy bot paper trading (mặc định Testnet + dry_run).

An toàn theo lớp:
  - dry_run=True  : chỉ mô phỏng, KHÔNG gửi lệnh (chạy được ngay, không cần API key).
  - mode=testnet  : gửi lệnh THẬT nhưng trên Binance Testnet (tiền ảo) — cần API key testnet.
  - mode=live     : Binance thật — CHỈ khi đã kiểm chứng kỹ. Tự chịu rủi ro.

Cấu hình qua file .env (xem .env.example). Dừng an toàn: tạo file 'STOP'.
"""
from config import CONFIG
from trader import run

if __name__ == "__main__":
    print("=" * 60)
    print(" BOT PAPER TRADING — Swing Stoch RSI")
    print(f"  mode      = {CONFIG.mode}")
    print(f"  dry_run   = {CONFIG.dry_run}  (True = không gửi lệnh thật)")
    print(f"  symbols   = {CONFIG.symbols if CONFIG.use_gainers == 0 else f'top {CONFIG.use_gainers} gainers'}")
    print(f"  risk/lệnh = {CONFIG.risk_per_trade*100:.1f}%  | TP +{CONFIG.tp_pct*100:.1f}% | SL -{CONFIG.max_sl_pct*100:.1f}%")
    print(f"  kill-file = '{CONFIG.kill_file}'  (tạo file này để dừng)")
    print("=" * 60)
    run(CONFIG)
