"""Cấu hình tập trung. Đọc bí mật từ .env. Sao chép .env.example -> .env và điền."""
import os
from dataclasses import dataclass, field
from typing import List

# override=True: khi .env đổi và module nạp lại (bật lại bot), lấy giá trị MỚI.
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass


def _get(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _get_bool(name, default=False):
    v = _get(name)
    return default if v is None else str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _get_float(name, default):
    try:
        return float(_get(name, default))
    except (TypeError, ValueError):
        return default


def _get_int(name, default):
    try:
        return int(_get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    mode: str = _get("TRADE_MODE", "testnet")
    api_key: str = _get("BINANCE_API_KEY", "")
    api_secret: str = _get("BINANCE_API_SECRET", "")
    symbols: List[str] = field(default_factory=lambda: _get("SYMBOLS", "SOL/USDT,AVAX/USDT,LINK/USDT").split(","))
    use_gainers: int = _get_int("USE_GAINERS", 10)
    initial_capital: float = _get_float("INITIAL_CAPITAL", 1000.0)
    max_capital: float = _get_float("MAX_CAPITAL", 1000.0)
    risk_per_trade: float = _get_float("RISK_PER_TRADE", 0.02)
    tp_pct: float = _get_float("TP_PCT", 0.03)
    max_sl_pct: float = _get_float("MAX_SL_PCT", 0.02)
    max_open_trades: int = _get_int("MAX_OPEN_TRADES", 3)
    daily_stop: float = _get_float("DAILY_STOP", 0.05)
    # --- Cải tiến đã kiểm chứng (mặc định BẬT) ---
    use_trend_filter: bool = _get_bool("USE_TREND_FILTER", True)
    trend_ema: int = _get_int("TREND_EMA", 50)
    use_trailing: bool = _get_bool("USE_TRAILING", True)
    trail_pct: float = _get_float("TRAIL_PCT", 0.03)
    use_stall_exit: bool = _get_bool("USE_STALL_EXIT", True)
    stall_bars: int = _get_int("STALL_BARS", 12)
    use_gain_filter: bool = _get_bool("USE_GAIN_FILTER", True)
    gain_avoid_lo: float = _get_float("GAIN_AVOID_LO", 0.05)
    gain_avoid_hi: float = _get_float("GAIN_AVOID_HI", 0.10)
    # --- An toàn ---
    hard_stop_on_exchange: bool = _get_bool("HARD_STOP_ON_EXCHANGE", True)
    max_total_drawdown: float = _get_float("MAX_TOTAL_DRAWDOWN", 0.20)
    dry_run: bool = _get_bool("DRY_RUN", True)
    loop_seconds: int = _get_int("LOOP_SECONDS", 300)
    telegram_token: str = _get("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = _get("TELEGRAM_CHAT_ID", "")
    kill_file: str = _get("KILL_FILE", "STOP")

    def validate_live(self):
        problems = []
        if self.mode not in ("testnet", "live"):
            problems.append(f"TRADE_MODE không hợp lệ: {self.mode}")
        if not self.dry_run and not (self.api_key and self.api_secret):
            problems.append("Thiếu BINANCE_API_KEY / BINANCE_API_SECRET để đặt lệnh.")
        return problems


CONFIG = Config()
