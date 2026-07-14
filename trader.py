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
import csv
import json
import os
import time

import pandas as pd

LIVE_TRADES = "live_trades.csv"


def log_trade(rec: dict):
    """Ghi một lệnh ĐÃ ĐÓNG vào nhật ký live (để thống kê giống backtest)."""
    exists = os.path.exists(LIVE_TRADES)
    with open(LIVE_TRADES, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rec.keys()))
        if not exists:
            w.writeheader()
        w.writerow(rec)

from strategy import add_indicators, params_from_config
from risk import position_size, DailyStop, total_drawdown_exceeded
from data import make_exchange, fetch_recent, top_gainers
from scanner import scan, _closed_only
from executor import Executor
from monitor import setup_logger, Notifier, kill_requested, now_utc

STATE_FILE = "state.json"


def decide_exit(pos, price, reversal, held_bars, p):
    """Quyết định thoát lệnh — KHỚP đúng logic backtest (trailing / stall / reversal / time)."""
    peak = pos.get("peak", pos["entry"])
    if p.use_trailing:
        trail_stop = peak * (1 - p.trail_pct)
        eff_sl = max(pos["sl"], trail_stop)
        if price <= eff_sl:
            return ("Trail", eff_sl) if trail_stop > pos["sl"] else ("SL", eff_sl)
    else:
        if price <= pos["sl"]:
            return "SL", pos["sl"]
        if price >= pos["tp"]:
            return "TP", pos["tp"]
    if reversal:
        return "Reversal", price
    if p.use_stall_exit and held_bars >= p.stall_bars and price <= pos["entry"]:
        return "Stall", price
    if held_bars >= p.max_hold_bars:
        return "TimeStop", price
    return None, None


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


def run(cfg, should_stop=None):
    """
    should_stop: hàm không đối số trả về True để yêu cầu dừng bot (dùng cho dashboard).
    """
    log = setup_logger()
    note = Notifier(cfg, log)
    problems = cfg.validate_live()
    for pr in problems:
        log.warning(pr)

    p = params_from_config(cfg)
    ex = make_exchange(cfg)
    execu = Executor(ex, cfg, note)
    state = _load_state()
    dstop = DailyStop(threshold=cfg.daily_stop)

    mode_txt = f"mode={cfg.mode} dry_run={cfg.dry_run}"
    note.event(f"▶ Khởi động bot ({mode_txt}). Tạo file '{cfg.kill_file}' để dừng an toàn.")

    while True:
        try:
            if kill_requested(cfg.kill_file) or (should_stop and should_stop()):
                note.event("■ Nhận lệnh dừng. Dừng bot (không đóng vị thế tự động).")
                break

            # Chọn danh mục
            symbols = top_gainers(cfg.use_gainers, exchange=ex) if cfg.use_gainers > 0 else cfg.symbols

            # Vốn hiện tại, có ÁP HẠN MỨC max_capital (dù ví có nhiều hơn)
            cash_actual = execu.free_usdt()
            open_value = 0.0
            for sym, pos in state["open"].items():
                try:
                    open_value += pos["qty"] * execu.price(sym)
                except Exception:
                    open_value += pos["qty"] * pos["entry"]
            equity_actual = cash_actual + open_value
            budget = cfg.max_capital if getattr(cfg, "max_capital", 0) and cfg.max_capital > 0 else equity_actual
            equity = min(equity_actual, budget)                       # dùng cho sizing & drawdown
            cash = min(cash_actual, max(0.0, budget - open_value))    # tiền cho lệnh mới, trong hạn mức
            state["peak_equity"] = max(state.get("peak_equity", 0.0), equity)

            if total_drawdown_exceeded(state["peak_equity"], equity, cfg.max_total_drawdown):
                note.event(f"⛔ Sụt giảm tổng vượt {cfg.max_total_drawdown*100:.0f}%. Tự dừng bot.")
                _save_state(state)
                break

            # 3) Quản lý thoát lệnh (trailing/stall/reversal/time — khớp backtest)
            for sym in list(state["open"].keys()):
                pos = state["open"][sym]
                px = execu.price(sym)
                pos["peak"] = max(pos.get("peak", pos["entry"]), px)   # theo dõi đỉnh cho trailing
                held_bars = int((now_utc() - pd.to_datetime(pos["entry_time"])).total_seconds() // 3600)
                # Chỉ tính đảo chiều (tốn phí gọi API) khi giá chưa chạm ngưỡng thoát
                reason, _ = decide_exit(pos, px, False, held_bars, p)
                if reason is None:
                    reason, _ = decide_exit(pos, px, _reversal_exit(sym, p, ex), held_bars, p)
                if reason:
                    execu.cancel(sym, pos.get("stop_order_id"))
                    sell = execu.market_sell(sym, pos["qty"], reason)
                    exit_px = sell.price
                    pnl = (exit_px - pos["entry"]) * pos["qty"]
                    risk = pos.get("risk_amount") or 0
                    log_trade({
                        "closed_at": str(now_utc())[:19], "symbol": sym,
                        "entry_time": str(pos["entry_time"])[:19], "entry": round(pos["entry"], 8),
                        "exit_time": str(now_utc())[:19], "exit": round(exit_px, 8),
                        "qty": pos["qty"], "reason": reason,
                        "pnl": round(pnl, 4), "R": round(pnl / risk, 3) if risk else 0,
                        "ret24": pos.get("ret24"), "hold_bars": held_bars,
                        "mode": cfg.mode, "dry_run": cfg.dry_run,
                    })
                    note.event(f"✔ Đóng {sym} ({reason}) @ ${exit_px:.6f} | PnL ${pnl:+.2f}")
                    del state["open"][sym]
                    _save_state(state)
                else:
                    _save_state(state)   # lưu peak cập nhật

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
                        "peak": buy.price,
                        "risk_amount": sz["risk_amount"], "ret24": s.get("ret24"),
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

        # Ngủ theo từng giây để phản hồi nhanh lệnh dừng (kill-switch / dashboard)
        for _ in range(max(1, int(cfg.loop_seconds))):
            if kill_requested(cfg.kill_file) or (should_stop and should_stop()):
                break
            time.sleep(1)


if __name__ == "__main__":
    from config import CONFIG
    run(CONFIG)
