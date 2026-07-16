# Lấy API key Binance Testnet & chọn chế độ chạy

## Vì sao dùng Testnet + DRY_RUN?
Chiến lược này đánh **altcoin top-gainer**, mà Binance Testnet chỉ có vài cặp lớn — không khớp.
Vì vậy cấu hình khuyến nghị là:

- **TRADE_MODE=testnet** + **DRY_RUN=true**: bot lấy **dữ liệu thị trường THẬT** (Binance công khai,
  không cần key) để tính tín hiệu, và **mô phỏng** đặt lệnh trong bộ nhớ (không gửi lệnh thật).
  Đây là cách chạy paper trading chính xác nhất cho chiến lược này.

Nói cách khác: ở DRY_RUN, bạn **không bắt buộc** phải có API key. Chỉ cần key nếu muốn thật sự
gửi lệnh lên sàn.

## Lấy API key Testnet (nếu muốn thử đặt lệnh thật trên testnet)
1. Vào https://testnet.binance.vision → **Log in with GitHub**.
2. Bấm **Generate HMAC_SHA256 Key**.
3. Ghi lại **API Key** và **Secret Key** (Secret chỉ hiện 1 lần).
4. Điền vào `.env`:
   ```
   TRADE_MODE=testnet
   DRY_RUN=true          # để true cho an toàn; đổi false nếu muốn gửi lệnh testnet thật
   BINANCE_API_KEY=...
   BINANCE_API_SECRET=...
   ```

## Các chế độ
| TRADE_MODE | DRY_RUN | Ý nghĩa |
|------------|---------|---------|
| testnet | true  | **Khuyến nghị.** Dữ liệu thật, lệnh mô phỏng. Không cần key. |
| testnet | false | Gửi lệnh thật lên **testnet** (tiền ảo). Cần key testnet. Chỉ có vài cặp lớn. |
| live    | true  | Dữ liệu thật, lệnh mô phỏng, dùng key thật để đọc số dư. |
| live    | false | **TIỀN THẬT.** Chỉ bật khi đã kiểm chứng kỹ. Cần key sàn thật + đã rất tự tin. |

## Chuyển sang tiền thật (khi đã sẵn sàng) — thận trọng
1. Tạo API key trên Binance thật (bật quyền Spot Trading, KHÔNG bật rút tiền, giới hạn IP nếu được).
2. Đặt `TRADE_MODE=live`, `DRY_RUN=false`, điền key thật.
3. Đặt `MAX_CAPITAL` nhỏ (ví dụ 100–200) để giới hạn rủi ro dù ví có nhiều hơn.
4. Theo dõi sát vài ngày đầu qua Telegram + dashboard.

## An toàn
- Bắt đầu và ở lại DRY_RUN cho tới khi thống kê live khớp kỳ vọng.
- KHÔNG chia sẻ `.env`. KHÔNG bật quyền rút tiền cho API key.
- File `STOP` trong thư mục sẽ ép bot dừng khẩn cấp (kill switch).
