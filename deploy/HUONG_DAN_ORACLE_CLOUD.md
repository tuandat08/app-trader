# Chạy bot 24/7 miễn phí trên Oracle Cloud (Always Free)

Mục tiêu: bot chạy liên tục cả khi tắt máy tính. Oracle Cloud cho VM miễn phí vĩnh viễn
(Always Free) — đủ mạnh cho bot này.

## 1. Tạo tài khoản & VM
1. Đăng ký tại https://www.oracle.com/cloud/free/ (cần thẻ để xác minh, KHÔNG bị trừ tiền nếu chỉ dùng Always Free).
2. Menu → **Compute → Instances → Create Instance**.
3. Image: **Ubuntu 22.04**. Shape: **VM.Standard.A1.Flex** (ARM, 1 OCPU / 6 GB là quá đủ) —
   nằm trong Always Free. Nếu hết ARM, chọn **VM.Standard.E2.1.Micro** (x86).
4. Phần **SSH keys**: bấm "Save private key" và "Save public key" → giữ file `.key` cẩn thận.
5. Create. Chờ ~1 phút, ghi lại **Public IP**.

## 2. Mở cổng 5000 (để xem dashboard) — tuỳ chọn
Nếu muốn mở dashboard qua trình duyệt:
- **Networking → Virtual Cloud Networks → (VCN của bạn) → Security Lists → Default** →
  Add Ingress Rule: Source `0.0.0.0/0`, Protocol TCP, Destination port **5000**.
- Trên VM cũng mở tường lửa: `sudo iptables -I INPUT -p tcp --dport 5000 -j ACCEPT`
  (hoặc dùng SSH tunnel ở mục 6 cho an toàn hơn — khuyến nghị).

## 3. SSH vào máy chủ
```bash
chmod 600 duong-dan-toi-file.key
ssh -i duong-dan-toi-file.key ubuntu@<PUBLIC_IP>
```

## 4. Cài đặt bot
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip unzip
# Tải code lên: dùng scp từ máy bạn, hoặc git clone nếu bạn đã đẩy lên git
# Ví dụ scp (chạy ở MÁY BẠN, không phải trên server):
#   scp -i file.key -r "app-trader" ubuntu@<PUBLIC_IP>:/home/ubuntu/

cd /home/ubuntu/app-trader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env          # điền API key testnet, Telegram... rồi Ctrl+O, Enter, Ctrl+X
python selftest.py # kiểm thử nhanh
```

## 5. Chạy nền vĩnh viễn bằng systemd
```bash
# Sửa User / đường dẫn trong file service nếu cần
sudo cp deploy/trader3-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trader3-bot     # tự chạy khi máy khởi động lại
sudo systemctl start trader3-bot
sudo systemctl status trader3-bot     # xem trạng thái (q để thoát)
tail -f bot.log                       # xem log trực tiếp
```

Lệnh quản lý: `sudo systemctl restart trader3-bot` (khởi động lại),
`sudo systemctl stop trader3-bot` (dừng).

## 6. Xem dashboard an toàn qua SSH tunnel (khuyến nghị)
Không cần mở cổng 5000 ra internet. Chạy ở MÁY BẠN:
```bash
ssh -i file.key -L 5000:localhost:5000 ubuntu@<PUBLIC_IP>
```
Rồi mở trình duyệt: http://localhost:5000

## 7. Cập nhật code mới
```bash
# đẩy code mới lên (scp/git) rồi:
sudo systemctl restart trader3-bot
```

## Lưu ý an toàn
- Luôn để **DRY_RUN=true** và **TRADE_MODE=testnet** cho tới khi bạn thực sự tin tưởng.
- KHÔNG bao giờ commit/chia sẻ file `.env` (chứa key).
- Nếu mở cổng 5000 ra internet, hãy đặt sau reverse proxy có mật khẩu, hoặc chỉ dùng SSH tunnel.
