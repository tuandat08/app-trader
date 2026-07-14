# Hướng dẫn Paper Trading trên Binance Testnet (Giai đoạn 2)

Mục tiêu: chạy bot **tự động bằng tiền ảo** để xem chiến lược đã kiểm chứng hoạt động
ngoài đời thật thế nào (phí, trượt giá, độ trễ, tâm lý) — **trước khi** đụng tiền thật.

Bot đã được đồng bộ đúng cấu hình tốt nhất từ backtest:
**Top-10 gainer · Trend filter · Trailing 3% · Cắt chết yểu 12h · Né vùng tăng chết 5–10% · SL 2% · Rủi ro 2%/lệnh.**

---

## Các lớp an toàn (nhớ kỹ)
- **DRY_RUN=true**: bot chỉ mô phỏng, KHÔNG gửi lệnh nào. Chạy được ngay, không cần key.
- **TRADE_MODE=testnet**: nếu tắt dry_run, lệnh gửi lên **Binance Testnet = tiền ảo**, không phải tiền thật.
- Ngưng lỗ 5%/ngày, tự dừng khi sụt >20%, kill-switch bằng file `STOP`.
- Không có chức năng rút tiền trong code.

---

## Bước 1 — Chạy thử ở chế độ mô phỏng thuần (khuyến nghị làm trước)
Không cần API key. Chỉ để xem bot quét & ra quyết định thế nào.

Qua dashboard: tab **Bot** → **Bật bot**. Xem log chạy, tín hiệu, "vào/thoát lệnh [DRY]".
Hoặc dòng lệnh: `python run_paper.py`. Dừng: tạo file `STOP` hoặc nút Dừng.

Ở chế độ này mọi lệnh chỉ được **ghi log**, không có gì gửi đi. Cứ để chạy 1–2 ngày cho quen.

## Bước 2 — Lấy API key Testnet (khi muốn đặt lệnh ảo thật sự)
1. Vào **https://testnet.binance.vision** → đăng nhập bằng GitHub.
2. Bấm **Generate HMAC_SHA256 Key** → lưu lại **API Key** và **Secret Key** (key testnet, khác hoàn toàn key thật).
3. Testnet tự cấp sẵn số dư USDT ảo để giao dịch.

## Bước 3 — Cấu hình
Cách dễ: mở dashboard → tab **Cấu hình** → điền API Key/Secret → đặt `TRADE_MODE=testnet`,
`DRY_RUN=false` (để đặt lệnh ảo thật) → **Lưu cấu hình**.

Hoặc sửa file `.env` (sao chép từ `.env.example`):
```
TRADE_MODE=testnet
DRY_RUN=false
BINANCE_API_KEY=...(key testnet)...
BINANCE_API_SECRET=...(secret testnet)...
```
Giữ nguyên các dòng cải tiến (đã đặt sẵn đúng cấu hình tốt nhất).

## Bước 4 — Chạy bot
Dashboard tab **Bot** → **Bật bot**. Hoặc `python run_paper.py`.
Bot mỗi 5 phút sẽ: quét top-10 gainer → lọc tín hiệu → đặt lệnh mua + stop-loss (ảo) →
quản lý trailing/stall → thoát lệnh. Mọi hoạt động hiện ở tab Bot (log trực tiếp).

**Dừng an toàn bất cứ lúc nào:** nút Dừng, hoặc tạo file rỗng tên `STOP` trong thư mục.

## Bước 5 — Theo dõi & đánh giá (2–4 tuần)
Cần xem:
- Bot có vào/thoát lệnh đúng như thiết kế không (đối chiếu log với quy tắc).
- Kết quả thực tế so với backtest: chênh bao nhiêu do phí & trượt giá.
- Có lỗi kỹ thuật, kẹt lệnh, đặt trùng không.

**Cổng đi tiếp:** chỉ khi bot chạy ổn định, kết quả sát backtest (sau khi trừ phí/slippage),
mới cân nhắc tiền thật với vốn RẤT nhỏ — và đó là quyết định riêng của bạn.

---

## Hạn chế đã biết (cần xử lý trước khi dùng tiền thật)
- **Trailing quản lý bằng phần mềm**: stop-loss đặt ở sàn giữ mức ban đầu; nếu bot tắt giữa
  chừng khi lệnh đang lời to, mức bảo vệ ở sàn vẫn ở giá vào ban đầu. Trên testnet (bot chạy
  liên tục) thì ổn; trước khi lên tiền thật nên nâng cấp để cập nhật stop ở sàn theo trailing.
- Độ chính xác số lượng/giá theo từng cặp coin do ccxt xử lý — nên kiểm tra vài lệnh đầu trên
  testnet có khớp đúng không.
- Đây là công cụ giáo dục, không phải lời khuyên đầu tư. Tự chịu trách nhiệm khi dùng tiền thật.
