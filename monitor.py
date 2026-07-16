"""
Giám sát: ghi log ra màn hình + file, gửi cảnh báo Telegram (tuỳ chọn),
và kiểm tra kill-switch (dừng bot an toàn bằng cách tạo file STOP).
"""
import os
import logging
from datetime import datetime, timezone

try:
    import requests
except Exception:
    requests = None


def setup_logger(logfile="trader.log"):
    logger = logging.getLogger("trader3")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh = logging.StreamHandler(); sh.setFormatter(fmt); logger.addHandler(sh)
    fh = logging.FileHandler(logfile, encoding="utf-8"); fh.setFormatter(fmt); logger.addHandler(fh)
    return logger


class Notifier:
    def __init__(self, cfg, logger):
        self.cfg = cfg
        self.log = logger

    def telegram(self, text: str):
        c = self.cfg
        if not (c.telegram_token and c.telegram_chat_id):
            return
        if requests is None:
            self.log.warning("Chưa cài 'requests' — bỏ qua Telegram.")
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{c.telegram_token}/sendMessage",
                data={"chat_id": c.telegram_chat_id, "text": text},
                timeout=10,
            )
        except Exception as e:
            self.log.warning(f"Gửi Telegram lỗi: {e}")

    def event(self, text: str, alert=True):
        self.log.info(text)
        if alert:
            self.telegram(text)


def kill_requested(kill_file="STOP") -> bool:
    """True nếu tồn tại file kill-switch -> yêu cầu dừng bot an toàn."""
    return os.path.exists(kill_file)


def now_utc():
    return datetime.now(timezone.utc)
