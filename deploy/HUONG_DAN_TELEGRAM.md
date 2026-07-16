# Nhận thông báo bot qua Telegram (group hoặc chat riêng)

Bot sẽ tự nhắn khi: khởi động, **vào lệnh** (coin, giá, SL, khối lượng), **thoát lệnh**
(lời/lỗ $ và %, R, lý do) kèm **tổng tích luỹ** (số lệnh, thắng/thua, ròng), và khi dừng
hoặc chạm ngưỡng an toàn.

## Bước 1 — Tạo bot Telegram
1. Trong Telegram, tìm **@BotFather** → gõ `/newbot` → đặt tên → nhận **TOKEN**
   (dạng `123456:ABC-xyz...`). Lưu lại.

## Bước 2 — Lấy Chat ID
**Nếu gửi vào GROUP:**
1. Tạo group (hoặc dùng group sẵn có) → **thêm bot bạn vừa tạo vào group**.
2. Gửi một tin bất kỳ trong group (vd "hello").
3. Mở trình duyệt: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   (thay `<TOKEN>` bằng token của bạn).
4. Tìm dòng `"chat":{"id":-100xxxxxxxxxx` — số **âm** đó là **Chat ID của group**.

**Nếu gửi vào chat riêng với bot:** nhắn `/start` cho bot, rồi cũng mở link getUpdates,
lấy `"chat":{"id":123456...}` (số dương).

> Mẹo nếu không thấy update: dùng thêm bot **@RawDataBot** hoặc **@userinfobot** trong group
> để lấy nhanh Chat ID.

## Bước 3 — Điền vào cấu hình
Trên dashboard → tab **Cấu hình** → điền:
- **Telegram Token** = TOKEN ở Bước 1
- **Telegram Chat ID** = Chat ID ở Bước 2 (nhớ dấu `-` nếu là group)
→ **Lưu cấu hình**, rồi **tắt/bật lại bot**.

Ngay khi bật lại, bạn sẽ nhận tin "▶️ BOT KHỞI ĐỘNG…" trong group — đó là xác nhận đã nối thành công.

## Cần cài thư viện `requests`
Đã có trong `requirements.txt`. Nếu thiếu: `pip install requests`.

## Ví dụ tin nhắn bạn sẽ nhận
```
🟢 VÀO LỆNH SOL/USDT · đã tăng 12.3%/24h
• Giá vào: $185.40
• SL: $181.69 (-2.0%)
• Khối lượng: 5.39 (~$1000)
• Rủi ro tối đa: $20.00

✅ ĐÓNG SOL/USDT — LỜI (+$47.30)
• Lý do: Trail
• Giá ra: $194.18 (+4.73%) · +2.37R
• Giữ: 6h
📊 Tổng: 12 lệnh · Thắng 5/Thua 7 (41.7%) · Ròng $+118.40 (+11.84%)
```
