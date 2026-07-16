"""
Vòng lặp giao dịch LIVE (mặc định Testnet + dry_run).
Dữ liệu tín hiệu từ Binance THẬT; đặt lệnh qua testnet/live. Ghi nhật ký + báo Telegram.
"""
import csv
import json
import os
import time

import pandas as pd

from strategy import add_indicators, params_from_config
from risk import position_size, DailyStop, total_drawdown_exceeded
from data import make_exchange, fetch_recent, top_gainers
from scanner import scan, _closed_only
from executor import Executor
from monitor import setup_logger, Notifier, kill_requested, now_utc

STATE_FILE = "state.json"
LIVE_TRADES = "live_trades.csv"


def log_trade(rec: dict):
    exists = os.path.exists(LIVE_TRADES)
    with open(LIVE_TRADES, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rec.keys()))
        if not exists:
            w.writeheader()
        w.writerow(rec)


def decide_exit(pos, price, reversal, held_bars, p):
    """Khớp đúng logic backtest (trailing / stall / reversal / time)."""
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
    h1 = _closed_only(fetch_recent(symbol, "1h", limit=120, exchange=ex))
    d1 = _closed_only(fetch_recent(symbol, "1d", limit=60, exchange=ex))
    if len(h1) < 30:
        return False
    r = add_indicators(h1, d1, p).iloc[-1]
    return bool(r["k"] > p.ob_level and r["d"] > p.ob_level and r["cross_down"])


def run(cfg, should_stop=None):
    log = setup_logger()
    note = Notifier(cfg, log)
    for pr in cfg.validate_live():
        log.warning(pr)

    p = params_from_config(cfg)
    data_ex = make_exchange()            # DỮ LIỆU thị trường thật → tín hiệu
    ex = make_exchange(cfg)              # sàn ĐẶT LỆNH (testnet/live)
    execu = Executor(ex, cfg, note, data_ex=data_ex)
    state = _load_state()
    dstop = DailyStop(threshold=cfg.daily_stop)

    che_do = "MÔ PHỎNG (không gửi lệnh)" if cfg.dry_run else f"{cfg.mode.upper()} (đặt lệnh)"
    note.event(
        f"▶️ BOT KHỞI ĐỘNG — {che_do}\n"
        f"• Vốn tối đa: ${cfg.max_capital:.0f} · Rủi ro {cfg.risk_per_trade*100:.0f}%/lệnh · Tối đa {cfg.max_open_trades} lệnh\n"
        f"• Chiến lược: Top-{cfg.use_gainers} gainer · Trailing {cfg.trail_pct*100:.0f}% · "
        f"Trend{'✓' if cfg.use_trend_filter else '✗'} Stall{'✓' if cfg.use_stall_exit else '✗'} Né-vùng{'✓' if cfg.use_gain_filter else '✗'}\n"
        f"• Sẽ thông báo mỗi khi vào/thoát lệnh.")

    while True:
        try:
            if kill_requested(cfg.kill_file) or (should_stop and should_stop()):
                note.event("■ Nhận lệnh dừng. Dừng bot (không đóng vị thế tự động).")
                break

            symbols = top_gainers(cfg.use_gainers, exchange=data_ex) if cfg.use_gainers > 0 else cfg.symbols

            cash_actual = execu.free_usdt()
            open_value = 0.0
            for sym, pos in state["open"].items():
                try:
                    open_value += pos["qty"] * execu.price(sym)
                except Exception:
                    open_value += pos["qty"] * pos["entry"]
            equity_actual = cash_actual + open_value
            budget = cfg.max_capital if getattr(cfg, "max_capital", 0) and cfg.max_capital > 0 else equity_actual
            equity = min(equity_actual, budget)
            cash = min(cash_actual, max(0.0, budget - open_value))
            peak = state.get("peak_equity", 0.0)
            if cfg.max_capital and cfg.max_capital > 0:
                peak = min(peak, budget)
            state["peak_equity"] = max(peak, equity)

            if total_drawdown_exceeded(state["peak_equity"], equity, cfg.max_total_drawdown):
                note.event(f"⛔ Sụt giảm tổng vượt {cfg.max_total_drawdown*100:.0f}%. Tự dừng bot.")
                _save_state(state); break

            # Thoát lệnh
            for sym in list(state["open"].keys()):
                pos = state["open"][sym]
                px = execu.price(sym)
                pos["peak"] = max(pos.get("peak", pos["entry"]), px)
                held_bars = int((now_utc() - pd.to_datetime(pos["entry_time"])).total_seconds() // 3600)
                reason, _ = decide_exit(pos, px, False, held_bars, p)
                if reason is None:
                    reason, _ = decide_exit(pos, px, _reversal_exit(sym, p, data_ex), held_bars, p)
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
                    pnl_pct = (exit_px / pos["entry"] - 1) * 100
                    r_mult = pnl / risk if risk else 0
                    emoji = "✅" if pnl > 0 else "🔴"; kq = "LỜI" if pnl > 0 else "LỖ"
                    try:
                        from livestats import live_stats
                        st = live_stats(capital=cfg.max_capital or cfg.initial_capital)
                        tong = (f"\n📊 Tổng: {st['n']} lệnh · Thắng {st['n_win']}/Thua {st['n_loss']}"
                                f" ({st['win_rate']}%) · Ròng ${st['net']:+.2f} ({st['total_return']:+.2f}%)")
                    except Exception:
                        tong = ""
                    note.event(f"{emoji} ĐÓNG {sym} — {kq} (${pnl:+.2f})\n• Lý do: {reason}\n"
                               f"• Giá ra: ${exit_px:.6f} ({pnl_pct:+.2f}%) · {r_mult:+.2f}R\n• Giữ: {held_bars}h" + tong)
                    del state["open"][sym]
                _save_state(state)

            blocked = dstop.update(now_utc().date(), equity)

            # Vào lệnh
            if not blocked and len(state["open"]) < cfg.max_open_trades:
                for s in scan(symbols, p, data_ex):
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
                        "qty": buy.qty, "entry": buy.price, "sl": sl, "tp": tp, "peak": buy.price,
                        "risk_amount": sz["risk_amount"], "ret24": s.get("ret24"),
                        "entry_time": str(now_utc()), "stop_order_id": stop.id if stop else None,
                    }
                    cash -= sz["notional"]
                    ret_txt = f" · đã tăng {s['ret24']*100:.1f}%/24h" if s.get("ret24") is not None else ""
                    note.event(
                        f"🟢 VÀO LỆNH {s['symbol']}{ret_txt}\n"
                        f"• Giá vào: ${buy.price:.6f}\n"
                        f"• SL: ${sl:.6f} (-{(1-sl/buy.price)*100:.1f}%)\n"
                        f"• Khối lượng: {buy.qty} (~${sz['notional']:.0f})\n"
                        f"• Rủi ro tối đa: ${sz['risk_amount']:.2f}\n"
                        f"• Thoát: trailing {cfg.trail_pct*100:.0f}% / cắt lỗ / đảo chiều")
                    _save_state(state)

            log.info(f"Chu kỳ xong. Vốn≈${equity:,.2f} | Vị thế mở: {list(state['open'])}")
            _save_state(state)
        except Exception as e:
            log.error(f"Lỗi chu kỳ: {e}")

        for _ in range(max(1, int(cfg.loop_seconds))):
            if kill_requested(cfg.kill_file) or (should_stop and should_stop()):
                break
            time.sleep(1)


if __name__ == "__main__":
    from config import CONFIG
    run(CONFIG)
