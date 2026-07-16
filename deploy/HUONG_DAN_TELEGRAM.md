# Cài thông báo Telegram (tuỳ chọn)

Bot sẽ nhắn tin cho bạn khi khởi động, vào lệnh, thoát lệnh (kèm PnL và thống kê dồn).

## 1. Tạo bot Telegram → lấy TOKEN
1. Mở Telegram, tìm **@BotFather**.
2. Gõ `/newbot` → đặt tên và username (kết thúc bằng `bot`, ví dụ `trader3_kas_bot`).
3. BotFather trả về một chuỗi dạng `123456789:ABCdef...` → đây là **TELEGRAM_TOKEN**.

## 2. Lấy CHAT_ID của bạn
1. Bấm vào link bot vừa tạo, nhấn **Start** và gửi cho nó một tin bất kỳ (ví dụ "hi").
2. Mở trình duyệt, thay `<TOKEN>` rồi truy cập:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Tìm `"chat":{"id":123456789` — số đó là **TELEGRAM_CHAT_ID**.
   (Nếu thấy rỗng, gửi thêm 1 tin cho bot rồi tải lại trang.)

## 3. Điền vào `.env`
```
TELEGRAM_TOKEN=123456789:ABCdef...
TELEGRAM_CHAT_ID=123456789
```

## 4. Kiểm tra
- Trên dashboard → tab **Cấu hình** → nút **"Gửi thử Telegram"**. Nếu điện thoại nhận được tin là OK.
- Hoặc khởi động bot: bạn sẽ nhận tin "Bot đã khởi động".

## Gỡ lỗi
- Không nhận tin: kiểm tra đã bấm **Start** với bot chưa; TOKEN/CHAT_ID đúng chưa (không dư dấu cách).
- Muốn gửi vào nhóm: thêm bot vào nhóm, CHAT_ID nhóm là số ÂM (bắt đầu bằng `-`).
- Telegram là tuỳ chọn — để trống 2 dòng trên thì bot vẫn chạy, chỉ không có thông báo.
