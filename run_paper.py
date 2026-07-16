"""GĐ2 — Chạy bot paper trading (mặc định Testnet + dry_run)."""
from config import CONFIG
from trader import run

if __name__ == "__main__":
    print("=" * 60)
    print(" BOT PAPER TRADING — Swing Stoch RSI")
    print(f"  mode={CONFIG.mode}  dry_run={CONFIG.dry_run}  (True = không gửi lệnh thật)")
    print(f"  top-{CONFIG.use_gainers} gainer | vốn tối đa ${CONFIG.max_capital:.0f} | rủi ro {CONFIG.risk_per_trade*100:.0f}%/lệnh")
    print(f"  kill-file: '{CONFIG.kill_file}' (tạo file này để dừng)")
    print("=" * 60)
    run(CONFIG)
