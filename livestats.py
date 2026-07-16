"""
Thống kê giao dịch LIVE từ nhật ký live_trades.csv — tính các chỉ số GIỐNG backtest
để bạn có số liệu thật đối chiếu (win rate, R:R, profit factor, drawdown, phân tích thắng/thua).
"""
import csv
import os

import numpy as np

LIVE_TRADES = os.path.join(os.path.dirname(__file__), "live_trades.csv")


def _load(path=LIVE_TRADES):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                r["pnl"] = float(r["pnl"]); r["R"] = float(r["R"])
                r["hold_bars"] = int(float(r.get("hold_bars") or 0))
                r["ret24"] = float(r["ret24"]) if r.get("ret24") not in (None, "", "None") else None
            except (ValueError, KeyError):
                continue
            rows.append(r)
    return rows


def _buckets(trades, key, edges, is_pct=False):
    out = []
    for lo, hi in edges:
        if is_pct:
            grp = [t for t in trades if t.get("ret24") is not None and lo <= t["ret24"] * 100 < hi]
        else:
            grp = [t for t in trades if lo <= t["hold_bars"] < hi]
        if grp:
            w = sum(1 for t in grp if t["pnl"] > 0)
            out.append({"range": f"{lo}-{hi if hi < 900 else '+'}", "n": len(grp),
                        "win_rate": round(w / len(grp) * 100),
                        "avg_R": round(float(np.mean([t["R"] for t in grp])), 2),
                        "pnl": round(sum(t["pnl"] for t in grp), 2)})
    return out


def live_stats(capital=1000.0):
    trades = _load()
    if not trades:
        return {"ok": True, "empty": True, "n": 0}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    n = len(trades)
    gw = sum(t["pnl"] for t in wins)
    gl = sum(t["pnl"] for t in losses)
    avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0.0
    avg_loss = np.mean([t["pnl"] for t in losses]) if losses else 0.0

    # Đường vốn tích luỹ + drawdown
    eq, peak, maxdd = capital, capital, 0.0
    curve = []
    for t in trades:
        eq += t["pnl"]; peak = max(peak, eq)
        maxdd = min(maxdd, eq / peak - 1)
        curve.append({"t": t.get("closed_at", ""), "v": round(eq, 2)})

    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1

    def avg(lst, k):
        v = [t[k] for t in lst if t.get(k) is not None]
        return round(float(np.mean(v)), 2) if v else None

    return {
        "ok": True, "empty": False, "n": n,
        "n_win": len(wins), "n_loss": len(losses),
        "win_rate": round(len(wins) / n * 100, 1) if n else 0,
        "gross_win": round(gw, 2), "gross_loss": round(gl, 2), "net": round(gw + gl, 2),
        "total_return": round((eq - capital) / capital * 100, 2),
        "realized_rr": round(avg_win / -avg_loss, 2) if avg_loss < 0 else None,
        "profit_factor": round(gw / -gl, 2) if gl < 0 else None,
        "expectancy_r": round(float(np.mean([t["R"] for t in trades])), 3) if n else 0,
        "max_drawdown": round(maxdd * 100, 2),
        "capital": capital, "final": round(eq, 2),
        "reasons": reasons, "curve": curve,
        "analysis": {
            "win": {"n": len(wins), "avg_ret24": avg(wins, "ret24"), "avg_hold": avg(wins, "hold_bars")},
            "loss": {"n": len(losses), "avg_ret24": avg(losses, "ret24"), "avg_hold": avg(losses, "hold_bars")},
            "by_ret": _buckets(trades, "ret24", [(0, 5), (5, 10), (10, 20), (20, 40), (40, 999)], is_pct=True),
            "by_hold": _buckets(trades, "hold_bars", [(0, 3), (3, 6), (6, 12), (12, 24), (24, 9999)]),
        },
        "trades": [{
            "symbol": t["symbol"], "entry_time": t.get("entry_time", ""), "exit_time": t.get("exit_time", ""),
            "entry": t.get("entry"), "exit": t.get("exit"), "reason": t["reason"],
            "pnl": round(t["pnl"], 2), "R": t["R"],
            "ret24": round(t["ret24"] * 100, 1) if t.get("ret24") is not None else None,
            "hold_bars": t["hold_bars"], "mode": t.get("mode"), "dry_run": t.get("dry_run"),
        } for t in trades],
    }
