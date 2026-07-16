"""
Dashboard web cho bot Trader 3% — chạy: python webapp.py  → http://127.0.0.1:5000
Tabs: Bot (điều khiển + thống kê live) · Quét tham số · Cấu hình.
"""
import os
import json
import glob
import threading
import traceback
from datetime import datetime

from flask import Flask, jsonify, request, render_template

import config as config_mod
from strategy import Params
from backtest import run_backtest
from metrics import summarize, monthly_table
from validate import walk_forward

app = Flask(__name__)
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
SCANS_DIR = os.path.join(os.path.dirname(__file__), "scans")
os.makedirs(SCANS_DIR, exist_ok=True)

ENV_KEYS = [
    "TRADE_MODE", "DRY_RUN", "USE_GAINERS", "MAX_CAPITAL",
    "RISK_PER_TRADE", "MAX_SL_PCT", "MAX_OPEN_TRADES", "DAILY_STOP",
    "USE_TREND_FILTER", "TREND_EMA", "USE_TRAILING", "TRAIL_PCT",
    "USE_STALL_EXIT", "STALL_BARS", "USE_GAIN_FILTER", "GAIN_AVOID_LO", "GAIN_AVOID_HI",
    "HARD_STOP_ON_EXCHANGE", "MAX_TOTAL_DRAWDOWN", "LOOP_SECONDS",
    "BINANCE_API_KEY", "BINANCE_API_SECRET", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID",
]
SECRET_KEYS = {"BINANCE_API_KEY", "BINANCE_API_SECRET", "TELEGRAM_TOKEN"}
DEFAULT_UNIVERSE = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
                    "AVAX/USDT", "LINK/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT",
                    "LTC/USDT", "ATOM/USDT"]


# ----------------------- Bot nền -----------------------
def config_summary(cfg):
    return {
        "mode": cfg.mode, "dry_run": cfg.dry_run, "max_capital": cfg.max_capital,
        "use_gainers": cfg.use_gainers, "max_open": cfg.max_open_trades,
        "risk": cfg.risk_per_trade, "sl": cfg.max_sl_pct, "tp": cfg.tp_pct,
        "daily_stop": cfg.daily_stop, "loop": cfg.loop_seconds,
        "improvements": {
            "trend": cfg.use_trend_filter, "trend_ema": cfg.trend_ema,
            "trailing": cfg.use_trailing, "trail_pct": cfg.trail_pct,
            "stall": cfg.use_stall_exit, "stall_bars": cfg.stall_bars,
            "gain": cfg.use_gain_filter, "gain_lo": cfg.gain_avoid_lo, "gain_hi": cfg.gain_avoid_hi,
        },
    }


class BotManager:
    def __init__(self):
        self.thread = None
        self._stop = threading.Event()
        self.error = None
        self.cfg = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running:
            return False
        import importlib
        importlib.reload(config_mod)
        cfg = config_mod.Config()
        self.cfg = cfg
        self._stop.clear()
        self.error = None

        def _target():
            try:
                from trader import run
                run(cfg, should_stop=self._stop.is_set)
            except Exception as e:
                self.error = f"{e}\n{traceback.format_exc()}"

        self.thread = threading.Thread(target=_target, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self._stop.set()
        return True


BOT = BotManager()


# ----------------------- Cấu hình -----------------------
def read_env():
    values = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    cfg = config_mod.Config()
    defaults = {
        "TRADE_MODE": cfg.mode, "DRY_RUN": str(cfg.dry_run).lower(),
        "USE_GAINERS": str(cfg.use_gainers), "MAX_CAPITAL": str(cfg.max_capital),
        "RISK_PER_TRADE": str(cfg.risk_per_trade), "MAX_SL_PCT": str(cfg.max_sl_pct),
        "MAX_OPEN_TRADES": str(cfg.max_open_trades), "DAILY_STOP": str(cfg.daily_stop),
        "USE_TREND_FILTER": str(cfg.use_trend_filter).lower(), "TREND_EMA": str(cfg.trend_ema),
        "USE_TRAILING": str(cfg.use_trailing).lower(), "TRAIL_PCT": str(cfg.trail_pct),
        "USE_STALL_EXIT": str(cfg.use_stall_exit).lower(), "STALL_BARS": str(cfg.stall_bars),
        "USE_GAIN_FILTER": str(cfg.use_gain_filter).lower(),
        "GAIN_AVOID_LO": str(cfg.gain_avoid_lo), "GAIN_AVOID_HI": str(cfg.gain_avoid_hi),
        "HARD_STOP_ON_EXCHANGE": str(cfg.hard_stop_on_exchange).lower(),
        "MAX_TOTAL_DRAWDOWN": str(cfg.max_total_drawdown), "LOOP_SECONDS": str(cfg.loop_seconds),
    }
    out = {}
    for k in ENV_KEYS:
        val = values.get(k, defaults.get(k, ""))
        out[k] = "********" if (k in SECRET_KEYS and val) else val
    return out, values


def write_env(updates: dict):
    _, existing = read_env()
    for k, v in updates.items():
        if k in SECRET_KEYS and v in ("", "********"):
            continue
        existing[k] = v
    lines = ["# Cấu hình cập nhật từ dashboard\n"]
    for k in ENV_KEYS:
        if k in existing:
            lines.append(f"{k}={existing[k]}\n")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    state = {"open": {}, "peak_equity": 0.0}
    sp = os.path.join(os.path.dirname(__file__), "state.json")
    if os.path.exists(sp):
        try:
            state = json.load(open(sp, encoding="utf-8"))
        except Exception:
            pass
    cfg = BOT.cfg if (BOT.running and BOT.cfg) else config_mod.Config()
    return jsonify({
        "running": BOT.running, "error": BOT.error, "mode": cfg.mode, "dry_run": cfg.dry_run,
        "open_positions": state.get("open", {}), "peak_equity": state.get("peak_equity", 0.0),
        "config": config_summary(cfg), "config_is_live": bool(BOT.running and BOT.cfg),
    })


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        write_env(request.json or {})
        return jsonify({"ok": True})
    display, _ = read_env()
    return jsonify(display)


@app.route("/api/telegram/test", methods=["POST"])
def api_telegram_test():
    import importlib
    importlib.reload(config_mod)
    cfg = config_mod.Config()
    if not cfg.telegram_token or not cfg.telegram_chat_id:
        return jsonify({"ok": False, "error": "Chưa điền Token hoặc Chat ID (nhớ Lưu cấu hình trước)."})
    try:
        import requests
        r = requests.post(f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage",
                          data={"chat_id": cfg.telegram_chat_id,
                                "text": "✅ Test kết nối từ Trader3 Bot — Telegram đã hoạt động!"}, timeout=10)
        j = r.json()
        if j.get("ok"):
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": j.get("description", "lỗi"), "code": j.get("error_code")})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Không gọi được Telegram: {e}"})


@app.route("/api/bot/<action>", methods=["POST"])
def api_bot(action):
    if action == "start":
        ok = BOT.start()
        return jsonify({"ok": ok, "running": BOT.running, "error": BOT.error})
    if action == "stop":
        BOT.stop()
        return jsonify({"ok": True, "running": BOT.running})
    return jsonify({"ok": False}), 400


@app.route("/api/live/stats")
def api_live_stats():
    try:
        from livestats import live_stats
        cfg = config_mod.Config()
        base = cfg.max_capital if cfg.max_capital and cfg.max_capital > 0 else cfg.initial_capital
        return jsonify(live_stats(capital=base))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/logs")
def api_logs():
    path = os.path.join(os.path.dirname(__file__), "trader.log")
    if not os.path.exists(path):
        return jsonify({"lines": []})
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()[-200:]
    return jsonify({"lines": [l.rstrip() for l in lines]})


# ----------------------- Quét tham số -----------------------
def _floats(s, default):
    try:
        out = [float(x) for x in str(s).split(",") if x.strip() != ""]
        return out or default
    except ValueError:
        return default


def _ints(s, default):
    try:
        out = [int(float(x)) for x in str(s).split(",") if x.strip() != ""]
        return out or default
    except ValueError:
        return default


def _raw_opts(body):
    keys = ["use_trend", "trend_ema", "use_trailing", "trail_pct", "use_market", "market_ema",
            "use_stall", "stall_bars", "use_gainfilter", "gain_lo", "gain_hi"]
    return {k: body.get(k) for k in keys}


def _improvements(body):
    return {
        "use_trend_filter": bool(body.get("use_trend")),
        "trend_ema": int(body.get("trend_ema", 50) or 50),
        "use_trailing": bool(body.get("use_trailing")),
        "trail_pct": float(body.get("trail_pct", 3) or 3) / 100,
        "use_stall_exit": bool(body.get("use_stall")),
        "stall_bars": int(body.get("stall_bars", 12) or 12),
        "use_gain_filter": bool(body.get("use_gainfilter")),
        "gain_avoid_lo": float(body.get("gain_lo", 5) or 5) / 100,
        "gain_avoid_hi": float(body.get("gain_hi", 10) or 10) / 100,
    }


def save_scan(body, universe, rows, demo):
    ts = datetime.now()
    sid = "scan_" + ts.strftime("%Y%m%d_%H%M%S")
    rows_sorted = sorted(rows, key=lambda r: r.get("score", -1e9), reverse=True)
    label = (body.get("label") or "").strip() or (("DEMO " if demo else "") + f"{len(universe)} coin · {body.get('days','?')} ngày")
    payload = {"id": sid, "created": ts.strftime("%Y-%m-%d %H:%M:%S"), "demo": bool(demo),
               "label": label, "days": body.get("days"), "capital": body.get("capital"),
               "opts": _raw_opts(body), "universe": universe, "rows": rows_sorted}
    with open(os.path.join(SCANS_DIR, sid + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return sid


class ScanManager:
    def __init__(self):
        self.reset()

    def reset(self):
        self.thread = None; self.phase = "idle"; self.status = ""
        self.fetch_done = 0; self.fetch_total = 0; self.done = 0; self.total = 0
        self.rows = []; self.error = None; self.universe = []; self.demo = False
        self.saved_id = None; self.days = None; self.capital = None; self.opts = None; self.wfo = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, body):
        if self.running:
            return False
        self.reset()
        self.demo = bool(body.get("demo"))
        self.thread = threading.Thread(target=self._run, args=(body,), daemon=True)
        self.thread.start()
        return True

    def _run(self, body):
        try:
            from optimizer import param_scan
            days = int(body.get("days", 180))
            capital = float(body.get("capital", 1000))
            self.days, self.capital, self.opts = days, capital, _raw_opts(body)
            grid = {
                "tp_pct": [x / 100 for x in _floats(body.get("tp_list", "2,3,4,5"), [2, 3, 4, 5])],
                "max_sl_pct": [x / 100 for x in _floats(body.get("sl_list", "1.5,2,3"), [1.5, 2, 3])],
                "top_n": _ints(body.get("topn_list", "5,10"), [5, 10]),
                "risk_per_trade": [x / 100 for x in _floats(body.get("risk_list", "2"), [2])],
            }
            self.phase = "fetch"
            if self.demo:
                from demo_data import demo_dataset
                if body.get("auto_universe"):
                    syms = [f"C{i}/USDT" for i in range(min(int(body.get("auto_n", 50)), 40))]
                else:
                    syms = [s.strip() for s in (body.get("universe") or "").split(",") if s.strip()] or [f"C{i}/USDT" for i in range(8)]
                self.fetch_total = len(syms)
                data = demo_dataset(syms, days=min(days, 120))
                self.fetch_done = len(syms)
            else:
                from data import fetch_ohlcv, make_exchange, top_symbols_by_volume
                ex = make_exchange()
                if body.get("auto_universe"):
                    self.status = "Đang lấy top coin theo thanh khoản…"
                    syms = top_symbols_by_volume(int(body.get("auto_n", 50)), exchange=ex)
                else:
                    syms = [s.strip() for s in (body.get("universe") or "").split(",") if s.strip()] or DEFAULT_UNIVERSE
                self.fetch_total = len(syms)
                data = {}
                for s in syms:
                    self.status = f"Đang tải {s}…"
                    try:
                        data[s] = (fetch_ohlcv(s, "1h", days, exchange=ex),
                                   fetch_ohlcv(s, "1d", days + 10, exchange=ex))
                    except Exception:
                        pass
                    self.fetch_done += 1
                if not data:
                    self.phase = "error"; self.error = "Không tải được dữ liệu coin nào."; return

            self.universe = list(data.keys())
            self.phase = "scan"
            self.total = (len(grid["tp_pct"]) * len(grid["max_sl_pct"]) * len(grid["top_n"]) * len(grid["risk_per_trade"]))

            def cb(done, total, row):
                self.done = done; self.total = total; self.rows.append(row)
                self.status = f"Đang quét tổ hợp {done}/{total}…"

            base = _improvements(body)
            if body.get("wfo"):
                from optimizer import walk_forward_optimize
                self.status = "Đang kiểm định ngoài mẫu…"
                self.wfo = walk_forward_optimize(data, grid, capital=capital,
                                                 min_trades=int(body.get("min_trades", 10)),
                                                 base_params=base, split_frac=0.7, progress_cb=cb)
                self.phase = "done"; self.status = "Hoàn tất kiểm định ngoài mẫu."
            else:
                param_scan(data, grid, capital=capital, min_trades=int(body.get("min_trades", 10)),
                           splits=3, progress_cb=cb, base_params=base)
                self.phase = "done"
                self.status = f"Hoàn tất: {len(self.rows)} tổ hợp / {len(self.universe)} coin."
                self.saved_id = save_scan(body, self.universe, self.rows, self.demo)
        except Exception as e:
            self.phase = "error"; self.error = str(e)


SCAN = ScanManager()


@app.route("/api/scan/start", methods=["POST"])
def api_scan_start():
    ok = SCAN.start(request.json or {})
    return jsonify({"ok": ok, "already_running": not ok})


@app.route("/api/scan/progress")
def api_scan_progress():
    rows = sorted(SCAN.rows, key=lambda r: r.get("score", -1e9), reverse=True)
    return jsonify({
        "phase": SCAN.phase, "status": SCAN.status, "demo": SCAN.demo,
        "fetch_done": SCAN.fetch_done, "fetch_total": SCAN.fetch_total,
        "done": SCAN.done, "total": SCAN.total, "universe": SCAN.universe, "rows": rows,
        "error": SCAN.error, "saved_id": SCAN.saved_id,
        "days": SCAN.days, "capital": SCAN.capital, "opts": SCAN.opts, "wfo": SCAN.wfo,
    })


@app.route("/api/scans")
def api_scans_list():
    items = []
    for f in sorted(glob.glob(os.path.join(SCANS_DIR, "*.json")), reverse=True):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        best = d["rows"][0] if d.get("rows") else {}
        items.append({"id": d.get("id"), "created": d.get("created"), "label": d.get("label"),
                      "demo": d.get("demo"), "n_combos": len(d.get("rows", [])),
                      "n_universe": len(d.get("universe", [])), "best_monthly": best.get("monthly_%"),
                      "best_score": best.get("score"), "meets_any": any(r.get("meets_target") for r in d.get("rows", []))})
    return jsonify({"items": items})


@app.route("/api/scans/<sid>")
def api_scan_load(sid):
    path = os.path.join(SCANS_DIR, os.path.basename(sid) + ".json")
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "Không tìm thấy"}), 404
    return jsonify({"ok": True, **json.load(open(path, encoding="utf-8"))})


@app.route("/api/scans/<sid>/delete", methods=["POST"])
def api_scan_delete(sid):
    path = os.path.join(SCANS_DIR, os.path.basename(sid) + ".json")
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True})


def _analyze_trades(trades):
    import numpy as np
    if not trades:
        return None
    wins = [t for t in trades if t.pnl > 0]; losses = [t for t in trades if t.pnl <= 0]

    def avg(lst, attr):
        v = [getattr(t, attr) for t in lst if getattr(t, attr) is not None]
        return round(float(np.mean(v)), 2) if v else None

    def buckets(edges, is_pct):
        out = []
        for lo, hi in edges:
            if is_pct:
                grp = [t for t in trades if t.e_ret24 is not None and lo <= t.e_ret24 * 100 < hi]
            else:
                grp = [t for t in trades if lo <= t.bars_held < hi]
            if grp:
                w = sum(1 for t in grp if t.pnl > 0)
                out.append({"range": f"{lo}-{hi if hi < 900 else '+'}", "n": len(grp),
                            "win_rate": round(w / len(grp) * 100), "avg_R": round(float(np.mean([t.r_multiple for t in grp])), 2),
                            "pnl": round(sum(t.pnl for t in grp), 1)})
        return out

    return {
        "win": {"n": len(wins), "avg_ret24": avg(wins, "e_ret24"), "avg_hold": avg(wins, "bars_held")},
        "loss": {"n": len(losses), "avg_ret24": avg(losses, "e_ret24"), "avg_hold": avg(losses, "bars_held")},
        "by_ret": buckets([(0, 5), (5, 10), (10, 20), (20, 40), (40, 999)], True),
        "by_hold": buckets([(0, 3), (3, 6), (6, 12), (12, 24), (24, 9999)], False),
    }


@app.route("/api/scan/trades", methods=["POST"])
def api_scan_trades():
    body = request.json or {}
    demo = bool(body.get("demo"))
    universe = body.get("universe") or []
    if isinstance(universe, str):
        universe = [s.strip() for s in universe.split(",") if s.strip()]
    days = int(body.get("days", 180) or 180); capital = float(body.get("capital", 1000) or 1000)
    top_n = int(body.get("top_n", 10))
    p = Params(tp_pct=float(body.get("tp", 3)) / 100, max_sl_pct=float(body.get("sl", 2)) / 100,
               risk_per_trade=float(body.get("risk", 2)) / 100, **_improvements(body))
    try:
        if demo:
            from demo_data import demo_dataset
            data = demo_dataset(universe or [f"C{i}/USDT" for i in range(8)], days=min(days, 120))
        else:
            from data import fetch_ohlcv, make_exchange
            ex = make_exchange(); data = {}
            for s in universe:
                try:
                    data[s] = (fetch_ohlcv(s, "1h", days, exchange=ex), fetch_ohlcv(s, "1d", days + 10, exchange=ex))
                except Exception:
                    pass
            if not data:
                return jsonify({"ok": False, "error": "Không tải được dữ liệu."}), 200
        from backtest import gainer_eligibility
        res = run_backtest(data, p, initial_capital=capital, eligible=gainer_eligibility(data, top_n=top_n))
        trades = [{"symbol": t.symbol, "entry_time": str(t.entry_time)[:16], "exit_time": str(t.exit_time)[:16],
                   "entry": round(t.entry, 6), "exit": round(t.exit, 6), "reason": t.reason,
                   "pnl": round(t.pnl, 2), "R": round(t.r_multiple, 2),
                   "ret24": None if t.e_ret24 is None else round(t.e_ret24 * 100, 1),
                   "hold_h": t.bars_held, "hour": t.e_hour} for t in res.trades]
        wins = [t for t in res.trades if t.pnl > 0]; losses = [t for t in res.trades if t.pnl <= 0]
        gw = round(sum(t.pnl for t in wins), 2); gl = round(sum(t.pnl for t in losses), 2)
        summary = {"n": len(res.trades), "n_win": len(wins), "n_loss": len(losses),
                   "gross_win": gw, "gross_loss": gl, "net": round(gw + gl, 2),
                   "final": round(float(res.equity_curve.iloc[-1]) if len(res.equity_curve) else capital, 2), "capital": capital}
        from collections import defaultdict
        mbuf = defaultdict(lambda: {"n": 0, "win": 0, "gw": 0.0, "gl": 0.0})
        for t in res.trades:
            mk = str(t.exit_time)[:7]; d = mbuf[mk]; d["n"] += 1
            if t.pnl > 0:
                d["win"] += 1; d["gw"] += t.pnl
            else:
                d["gl"] += t.pnl
        monthly = [{"month": m, "trades": v["n"], "win": v["win"], "loss": v["n"] - v["win"],
                    "win_rate": round(v["win"] / v["n"] * 100) if v["n"] else 0,
                    "gross_win": round(v["gw"], 2), "gross_loss": round(v["gl"], 2),
                    "pnl": round(v["gw"] + v["gl"], 2)} for m, v in sorted(mbuf.items())]
        return jsonify({"ok": True, "trades": trades, "summary": summary,
                        "analysis": _analyze_trades(res.trades), "monthly": monthly})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


if __name__ == "__main__":
    print("Dashboard: http://127.0.0.1:5000  (Ctrl+C để dừng)")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
