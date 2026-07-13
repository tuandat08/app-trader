"""
Vòng lặp giao dịch LIVE (mặc định: Testnet + dry_run).

Mỗi chu kỳ:
  1) Kiểm tra kill-switch (file STOP) -> dừng an toàn.
  2) Cập nhật vốn, kiểm tra ngưỡng sụt giảm tổng -> tự dừng.
  3) Quản lý THOÁT lệnh cho vị thế đang mở (TP / SL / đảo chiều / hết hạn).
  4) Kiểm tra ngưng lỗ trong ngày.
  5) Quét tín hiệu và VÀO lệnh nếu còn chỗ.
Trạng thái vị thế lưu ra state.json để khôi phục khi khởi động lại.
"""
import json
import os
import time

import pandas as pd

from strategy import Params, add_indicators
from risk import position_size, DailyStop, total_drawdown_exceeded
from data import make_exchange, fetch_recent, top_gainers
from scanner import scan, _closed_only
from executor import Executor
from monitor import setup_logger, Notifier, kill_requested, now_utc

STATE_FILE = "state.json"


def _params_from_cfg(cfg) -> Params:
    return Params(tp_pct=cfg.tp_pct, max_sl_pct=cfg.max_sl_pct,
                  risk_per_trade=cfg.risk_per_trade, max_open_trades=cfg.max_open_trades,
                  daily_stop=cfg.daily_stop)


def _load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"open": {}, "peak_equity": 0.0}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)


def _reversal_exit(symbol, p, ex) -> bool:
    """True nếu H1 cho tín hiệu đảo chiều sớm (K,D>ob và K cắt xuống D)."""
    h1 = _closed_only(fetch_recent(symbol, "1h", limit=120, exchange=ex))
    d1 = _closed_only(fetch_recent(symbol, "1d", limit=60, exchange=ex))
    if len(h1) < 30:
        return False
    ind = add_indicators(h1, d1, p)
    r = ind.iloc[-1]
    return bool(r["k"] > p.ob_level and r["d"] > p.ob_level and r["cross_down"])


def run(cfg):
    log = setup_logger()
    note = Notifier(cfg, log)
    problems = cfg.validate_live()
    for pr in problems:
        log.warning(pr)

    p = _params_from_cfg(cfg)
    ex = make_exchange(cfg)
    execu = Executor(ex, cfg, note)
    state = _load_state()
    dstop = DailyStop(threshold=cfg.daily_stop)

    mode_txt = f"mode={cfg.mode} dry_run={cfg.dry_run}"
    note.event(f"▶ Khởi động bot ({mode_txt}). Tạo file '{cfg.kill_file}' để dừng an toàn.")

    while True:
        try:
            if kill_requested(cfg.kill_file):
                note.event("■ Phát hiện kill-switch. Dừng bot (không đóng vị thế tự động).")
                break

            # Chọn danh mục
            symbols = top_gainers(cfg.use_gainers, exchange=ex) if cfg.use_gainers > 0 else cfg.symbols

            # Vốn hiện tại (ước lượng): tiền mặt + giá trị vị thế mở
            cash = execu.free_usdt()
            equity = cash
            for sym, pos in state["open"].items():
                try:
                    equity += pos["qty"] * execu.price(sym)
                except Exception:
                    equity += pos["qty"] * pos["entry"]
            state["peak_equity"] = max(state.get("peak_equity", 0.0), equity)

            if total_drawdown_exceeded(state["peak_equity"], equity, cfg.max_total_drawdown):
                note.event(f"⛔ Sụt giảm tổng vượt {cfg.max_total_drawdown*100:.0f}%. Tự dừng bot.")
                _save_state(state)
                break

            # 3) Quản lý thoát lệnh
            for sym in list(state["open"].keys()):
                pos = state["open"][sym]
                px = execu.price(sym)
                held_h = (now_utc() - pd.to_datetime(pos["entry_time"])).total_seconds() / 3600.0
                reason = None
                if px <= pos["sl"]:
                    reason = "SL"
                elif px >= pos["tp"]:
                    reason = "TP"
                elif _reversal_exit(sym, p, ex):
                    reason = "Reversal"
                elif held_h >= p.max_hold_bars:
                    reason = "TimeStop"
                if reason:
                    execu.cancel(sym, pos.get("stop_order_id"))
                    execu.market_sell(sym, pos["qty"], reason)
                    del state["open"][sym]
                    _save_state(state)

            # 4) Ngưng lỗ ngày
            blocked = dstop.update(now_utc().date(), equity)

            # 5) Vào lệnh
            if not blocked and len(state["open"]) < cfg.max_open_trades:
                signals = scan(symbols, p, ex)
                for s in signals:
                    if len(state["open"]) >= cfg.max_open_trades:
                        break
                    if not s.get("signal") or s["symbol"] in state["open"]:
                        continue
                    entry, sl, tp = s["entry"], s["sl"], s["tp"]
                    sz = position_size(equity, entry, sl, cfg.risk_per_trade, cash)
                    if sz["qty"] <= 0 or sz["notional"] < 10:
                        continue
                    buy = execu.market_buy(s["symbol"], sz["qty"])
                    stop = execu.place_hard_stop(s["symbol"], buy.qty, sl)
                    state["open"][s["symbol"]] = {
                        "qty": buy.qty, "entry": buy.price, "sl": sl, "tp": tp,
                        "entry_time": str(now_utc()),
                        "stop_order_id": stop.id if stop else None,
                    }
                    cash -= sz["notional"]
                    note.event(f"➕ Vào lệnh {s['symbol']}: entry=${buy.price:.6f} "
                               f"TP=${tp:.6f} SL=${sl:.6f} qty={buy.qty}")
                    _save_state(state)

            log.info(f"Chu kỳ xong. Vốn≈${equity:,.2f} | Vị thế mở: {list(state['open'])}")
            _save_state(state)

        except Exception as e:
            log.error(f"Lỗi chu kỳ: {e}")

        time.sleep(cfg.loop_seconds)


if __name__ == "__main__":
    from config import CONFIG
    run(CONFIG)
