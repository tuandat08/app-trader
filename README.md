# Trader 3% — Bot Momentum Swing (Stoch RSI + Top Gainer)

Bot giao dịch crypto đã kiểm chứng: top-10 gainer · Stoch RSI (8,5,3,3) D1/H1 · Trend filter ·
Trailing stop · Cắt lệnh chết yểu · Né vùng tăng chết. Kèm dashboard backtest / quét tham số /
paper trading.

> ⚠️ Công cụ giáo dục, KHÔNG phải lời khuyên đầu tư. Giao dịch crypto có thể mất vốn.
> Mặc định Testnet + mô phỏng. Luôn kiểm chứng trước.

## Cài đặt
```bash
cd app-trader
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # rồi chỉnh nếu cần
```

## Chạy
```bash
python selftest.py     # kiểm thử offline (không cần mạng)
python webapp.py       # dashboard: http://127.0.0.1:5000
```

Dashboard 3 tab:
- **Bot**: bật/tắt paper trading, xem cấu hình đang chạy, vị thế mở, **Thống kê Live** (như backtest), log.
- **Quét tham số**: quét nhiều tổ hợp trên rổ coin (auto top theo thanh khoản), walk-forward,
  bảng thống kê theo tháng, lưu/mở lại kết quả, xuất CSV/JSON.
- **Cấu hình**: chỉnh mọi tham số + API key + Telegram, có nút "Gửi thử Telegram".

## Backtest dòng lệnh
```bash
python run_backtest.py --gainers 50 --days 730 --top-n 10 --walk 3
```

## Cấu hình đã đóng chốt (validate ngoài mẫu)
Top-10 gainer · Trend EMA 50 · Trailing 3% · Cắt chết yểu 12h · Né vùng 5–10% · SL 2% ·
Rủi ro 2%/lệnh · Vốn tối đa $1000 · Testnet + DRY_RUN.

## Lưu ý quan trọng
- Chiến lược đánh **altcoin top-gainer** mà Testnet không có → dùng **DRY_RUN=true**
  (mô phỏng trên dữ liệu thị trường THẬT). Bot lấy tín hiệu từ Binance công khai, đặt lệnh mô phỏng.
- Đây là chiến lược **tần suất thấp** (~vài lệnh/tuần) — không thấy tin Telegram cả ngày là bình thường.
- Kết quả kiểm chứng: ~12–21%/năm tuỳ giai đoạn, drawdown ~−10 tới −13%, lời dồn vào giai đoạn thị trường tăng.

## Cấu trúc
config, indicators, strategy, risk, backtest, metrics, validate, optimizer, data, demo_data,
scanner, executor, monitor, trader, livestats · webapp + templates/index.html ·
run_backtest / run_paper / selftest.
