# Chạy bot 24/7 miễn phí trên Oracle Cloud (Always-Free)

Mục tiêu: đưa bot lên một máy ảo Linux miễn phí chạy liên tục, tự khởi động lại nếu lỗi,
tự bật lại khi máy reboot. Toàn bộ dùng cho **paper trading Testnet (tiền ảo)**.

> Mẹo: đọc chậm, làm từng bước. Không cần biết Linux nhiều — chỉ copy/paste lệnh.

---

## Phần A — Tạo máy ảo miễn phí

1. Vào **https://cloud.oracle.com** → **Sign up**. Cần thẻ để xác minh, nhưng gói
   **Always Free** không bị tính tiền. Chọn **Home Region** gần bạn (vd Singapore).
2. Sau khi vào Console: menu ☰ → **Compute** → **Instances** → **Create instance**.
3. Cấu hình:
   - **Name**: trader-bot
   - **Image**: bấm *Edit* → chọn **Canonical Ubuntu 22.04**.
   - **Shape**: bấm *Edit* → chọn shape có nhãn **"Always Free eligible"**
     (VM.Standard.A1.Flex — ARM, hoặc VM.Standard.E2.1.Micro — AMD). Cả hai đều đủ dùng.
   - **SSH keys**: chọn **Generate a key pair for me** → **Download private key**
     (lưu file `.key` này thật kỹ, đây là chìa khoá vào máy).
4. Bấm **Create**. Chờ ~1 phút tới khi trạng thái **RUNNING**. Ghi lại **Public IP address**.

---

## Phần B — Kết nối vào máy

Trên máy Mac của bạn, mở Terminal, vào thư mục chứa file key vừa tải:
```bash
chmod 600 ~/Downloads/ssh-key-*.key           # đổi đúng tên file key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<PUBLIC_IP>
```
Gõ `yes` nếu được hỏi. Khi thấy dấu nhắc `ubuntu@...:~$` là đã vào máy ảo.

---

## Phần C — Cài đặt bot

Chạy lần lượt (trên máy ảo):
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git

# Lấy code về. Cách 1: từ GitHub của bạn (nếu repo private, dùng token/SSH):
git clone https://github.com/tuandat08/app-trader.git
cd app-trader

# Môi trường ảo + thư viện
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Kiểm thử (không cần mạng Binance)
python selftest.py
```

Nếu repo private và `git clone` đòi mật khẩu, cách đơn giản: từ máy Mac đẩy code lên bằng `scp`:
```bash
# chạy trên MÁY MAC, không phải máy ảo:
scp -i ~/Downloads/ssh-key-*.key -r "/đường/dẫn/app-trader" ubuntu@<PUBLIC_IP>:/home/ubuntu/
```

---

## Phần D — Cấu hình API Testnet
Tạo file `.env` trên máy ảo:
```bash
cp .env.example .env
nano .env
```
Điền: `TRADE_MODE=testnet`, `DRY_RUN=false`, `BINANCE_API_KEY=...`, `BINANCE_API_SECRET=...`
(key testnet), giữ nguyên các dòng cải tiến và `MAX_CAPITAL=1000`. Lưu: `Ctrl+O` → Enter → `Ctrl+X`.
Bảo mật file key:
```bash
chmod 600 .env
```

---

## Phần E — Chạy 24/7 bằng dịch vụ systemd (tự khởi động lại)

1. Chép file dịch vụ có sẵn trong `deploy/` vào hệ thống:
```bash
sudo cp deploy/trader3-bot.service /etc/systemd/system/
```
2. Kích hoạt (tự chạy khi máy bật + chạy ngay):
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trader3-bot
```
3. Kiểm tra & xem log trực tiếp:
```bash
systemctl status trader3-bot          # đang chạy chưa
journalctl -u trader3-bot -f          # xem log cuộn theo thời gian thực (Ctrl+C để thoát)
```

Từ giờ bot chạy **24/7**, tự khởi động lại nếu crash, tự bật lại khi máy reboot.

**Lệnh quản lý:**
```bash
sudo systemctl stop trader3-bot       # dừng
sudo systemctl start trader3-bot      # chạy lại
sudo systemctl restart trader3-bot    # nạp lại sau khi sửa .env
```

---

## Phần F — Xem dashboard để theo dõi (tuỳ chọn, an toàn)
KHÔNG mở cổng 5000 ra internet (vì chứa liên quan tới key). Thay vào đó dùng **SSH tunnel**:

Trên máy ảo, chạy dashboard ở chế độ nền:
```bash
source .venv/bin/activate
nohup python webapp.py > dashboard.log 2>&1 &
```
Trên **máy Mac**, mở tunnel:
```bash
ssh -i ~/Downloads/ssh-key-*.key -L 5000:localhost:5000 ubuntu@<PUBLIC_IP>
```
Rồi mở trình duyệt máy Mac vào **http://localhost:5000** — bạn xem được tab Thống kê Live,
log, cấu hình của bot đang chạy trên máy ảo.

> Lưu ý: trên máy ảo, hãy điều khiển bot bằng lệnh `systemctl` (Phần E), ĐỪNG bấm nút
> Bật/Dừng trong dashboard — vì sẽ tạo ra một bot thứ hai chạy song song. Dashboard ở đây
> chỉ để **xem** số liệu.

---

## An toàn
- File `.env` chứa API key — luôn `chmod 600`, không chia sẻ, không commit lên git.
- Giai đoạn testnet là tiền ảo nên rủi ro thấp. Khi lên tiền thật: bật IP whitelist cho API
  key (chỉ cho phép IP của máy ảo), không bật quyền rút tiền, và cân nhắc tường lửa chặt hơn.
- Muốn tắt hẳn: `sudo systemctl disable --now trader3-bot`.
