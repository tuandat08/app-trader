# Trader 3% — Bot giao dịch Swing Stoch RSI (Binance)

App tự động hoá chiến lược trong tài liệu tối ưu, xây theo lộ trình an toàn:
**backtest → paper trading (Testnet) → tiền thật vốn nhỏ**.

> ⚠️ Công cụ kỹ thuật & giáo dục, KHÔNG phải lời khuyên đầu tư. Giao dịch crypto có
> thể mất toàn bộ vốn. Luôn kiểm chứng trên Testnet trước; tự chịu trách nhiệm khi
> dùng tiền thật.

## Mục tiêu đánh giá (đã chốt)
Lợi nhuận **5–15%/tháng** · Tỷ lệ thắng **45–55%** · R:R thực tế **≥ 1:1,5**.

---

## Cài đặt
```bash
cd trader3_bot
python3 -m venv .venv && source .venv/bin/activate     # tuỳ chọn
pip install -r requirements.txt
cp .env.example .env        # rồi mở .env chỉnh cấu hình
```

## ⭐ Cách dễ nhất — Dashboard web (giao diện bấm nút)
```bash
python webapp.py
```
Mở trình duyệt vào **http://127.0.0.1:5000**. Trên dashboard bạn có thể:
- **Tổng quan**: trạng thái bot, vốn, vị thế đang mở.
- **Backtest**: chọn coin/tham số → bấm *Chạy Demo* (offline, dữ liệu giả lập) hoặc
  *Chạy thật* (tải Binance) → xem biểu đồ đường vốn, bảng lệnh, walk-forward, đối chiếu mục tiêu.
- **Quét tham số**: có tuỳ chọn **"Tự lấy top coin toàn thị trường"** — hệ thống quét cả sàn,
  lấy N coin thanh khoản cao nhất làm universe, rồi engine chọn động **top-N coin tăng mạnh nhất trong 24h** tại mỗi nến
  (không nhìn trước tương lai — đúng tinh thần "chỉ đánh coin đang tăng"), rồi quét nhiều
  tổ hợp TP/SL/top-N và xếp hạng theo hiệu quả + độ ổn định (walk-forward). Có **thanh tiến độ
  trực tiếp** (chạy tới đâu hiện tới đó) và **tự động lưu mỗi lần quét** vào thư mục `scans/`
  — mục "Kết quả đã lưu" cho phép mở lại phân tích sau mà không cần chạy lại.
- **Bot**: bật/tắt paper trading (mặc định Testnet + mô phỏng), xem log trực tiếp.
- **Cấu hình**: nhập API key, chỉnh risk/TP/SL… và lưu vào `.env` — không cần sửa file tay.

> Mẹo: chưa cấu hình gì cũng bấm được *Chạy Demo* để xem toàn bộ giao diện hoạt động.

## Bước 0 — Kiểm thử offline (không cần mạng/API)
```bash
python selftest.py
```
Xác nhận toàn bộ code chạy đúng. (Số liệu selftest là dữ liệu giả lập.)

## Bước 1 (GĐ1) — Backtest dữ liệu Binance thật
```bash
python run_backtest.py --symbols SOL/USDT AVAX/USDT LINK/USDT --days 180 --walk 3
# hoặc tự lấy top gainer đã lọc:
python run_backtest.py --gainers 10 --days 120 --walk 3
```
Xuất ra: `trade_log.csv`, `equity_curve.csv`, `monthly_returns.csv`, bảng đối chiếu
mục tiêu và phân tích **walk-forward** (độ ổn định qua các giai đoạn).

**Cổng GO/NO-GO:** chỉ đi tiếp nếu kết quả dương ổn định qua nhiều coin & giai đoạn.

## Bước 2 (GĐ2) — Paper trading trên Testnet
1. Tạo API key testnet tại https://testnet.binance.vision, điền vào `.env`.
2. Trong `.env`: `TRADE_MODE=testnet`. Để `DRY_RUN=true` chạy mô phỏng thuần,
   hoặc `DRY_RUN=false` để đặt lệnh THẬT trên testnet (tiền ảo).
3. Chạy:
```bash
python run_paper.py
```
Dừng an toàn bất cứ lúc nào: tạo file rỗng tên `STOP` trong thư mục (mặc định).

## Bước 3 (GĐ4) — Tiền thật (chỉ khi đã kiểm chứng)
Đổi `.env`: `TRADE_MODE=live`, `DRY_RUN=false`, dùng key thật (chỉ quyền Spot, KHÔNG
quyền rút tiền, bật IP whitelist), bắt đầu với vốn rất nhỏ. Giám sát chặt.

---

## Cấu trúc
| File | Vai trò |
|---|---|
| `config.py` | Cấu hình tập trung (đọc từ `.env`) |
| `indicators.py` | RSI, Stochastic RSI (8,5,3,3), giao cắt |
| `strategy.py` | Điều kiện vào/thoát lệnh (dùng chung backtest & live) |
| `risk.py` | Sizing 2%/lệnh, ngưng lỗ ngày, kill drawdown |
| `backtest.py` | Engine backtest (có phí) |
| `metrics.py` | Chỉ số + đối chiếu mục tiêu |
| `validate.py` | Equity curve, thống kê tháng, walk-forward |
| `data.py` | Kết nối Binance/Testnet, tải OHLCV, top gainer |
| `scanner.py` | Quét tín hiệu real-time |
| `executor.py` | Đặt lệnh Market + STOP-LOSS (dry_run an toàn) |
| `monitor.py` | Log + cảnh báo Telegram + kill-switch |
| `trader.py` | Vòng lặp giao dịch chính (có khôi phục trạng thái) |
| `run_backtest.py` / `run_paper.py` | Điểm vào GĐ1 / GĐ2 |
| `selftest.py` | Kiểm thử offline toàn bộ |

## Các lớp an toàn đã tích hợp
- `DRY_RUN` mặc định **bật** — không gửi lệnh thật cho tới khi bạn tắt.
- `TRADE_MODE=testnet` mặc định — dùng tiền ảo.
- Stop Loss phía sàn (phao cứu sinh nếu bot chết) + Stop Loss phần mềm.
- Ngưng lỗ 5%/ngày, tự dừng bot khi sụt >20% từ đỉnh.
- Kill-switch bằng file `STOP`. Lưu trạng thái `state.json` để khôi phục.
- Long-only, Spot, không đòn bẩy; không có chức năng rút tiền trong code.

## Điều cần bạn tự xác thực trên Testnet
Tham số lệnh (độ chính xác số lượng/giá, `minNotional`) khác nhau theo cặp coin và
do ccxt xử lý; hành vi đặt STOP-LOSS phía sàn nên được kiểm tra thực tế trên testnet
trước khi tin dùng. Đây chính là mục đích của GĐ2.

## Lời nhắc trung thực
Rất có thể backtest cho thấy chiến lược **chưa đạt** 5–15%/tháng ổn định. Đó là kết
quả có giá trị — nó giúp bạn tránh mất tiền thật. Hãy để dữ liệu quyết định, đừng để
kỳ vọng quyết định.
