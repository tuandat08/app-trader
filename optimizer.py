"""
Công cụ QUÉT THAM SỐ (param scan) trên nhiều coin, chọn động top-gainer từng thời điểm.

Mục tiêu: thay vì chỉnh tay từng lần, quét một lưới tham số (TP / SL / top_n / risk)
và xem có VÙNG tham số nào cho kết quả dương & ổn định không — để tránh overfitting
kiểu 'chỉ đẹp đúng một bộ số'.

CẢNH BÁO overfitting: nếu chỉ MỘT tổ hợp đẹp còn lại đều tệ, khả năng cao là may rủi.
Ta ưu tiên tổ hợp vừa dương, vừa đủ số lệnh, vừa ổn định qua các giai đoạn.
"""
import itertools
import pandas as pd

from strategy import Params
from backtest import run_backtest, gainer_eligibility
from metrics import summarize
from validate import walk_forward


def _stability(data, p, eligible, capital, splits=3):
    """Tỷ lệ số đoạn walk-forward có LN dương (0..1) — đo độ ổn định."""
    wf = walk_forward(data, splits=splits, p=p, initial_capital=capital)
    if wf.empty:
        return 0.0, wf
    pos = (wf["monthly_%"] > 0).sum()
    return pos / len(wf), wf


def param_scan(data, grid: dict, capital=1000.0, top_n_default=10,
               min_trades=10, use_gainer_filter=True, splits=3, progress_cb=None,
               base_params=None) -> pd.DataFrame:
    """
    grid ví dụ:
        {"tp_pct":[0.02,0.03,0.04,0.05], "max_sl_pct":[0.015,0.02,0.03],
         "top_n":[5,10], "risk_per_trade":[0.02]}
    Trả DataFrame mỗi dòng = 1 tổ hợp, kèm chỉ số & 'score' để xếp hạng.
    progress_cb(done:int, total:int, row:dict): gọi sau mỗi tổ hợp (để hiện tiến độ live).
    """
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    total = len(combos)

    # cache eligibility theo top_n (đỡ tính lại)
    elig_cache = {}

    def get_elig(top_n, max_ret):
        if not use_gainer_filter:
            return None
        key = (top_n, round(max_ret, 4))
        if key not in elig_cache:
            elig_cache[key] = gainer_eligibility(data, top_n=top_n, max_ret=max_ret)
        return elig_cache[key]

    rows = []
    for combo in combos:
        kw = dict(zip(keys, combo))
        top_n = int(kw.pop("top_n", top_n_default))
        p = Params(**{**(base_params or {}), **{k: v for k, v in kw.items()}})
        max_ret = 0.40
        elig = get_elig(top_n, max_ret)
        res = run_backtest(data, p, initial_capital=capital, eligible=elig)
        m = summarize(res)
        stab, _ = _stability(data, p, elig, capital, splits=splits)

        # Điểm tổng hợp: thưởng LN/tháng & độ ổn định, phạt nếu quá ít lệnh
        enough = m["num_trades"] >= min_trades
        rr = m["realized_rr"] if m["realized_rr"] != float("inf") else 3.0
        score = (m["monthly_return"] * 100) * (1 if enough else 0.3) + stab * 2 \
            + min(max(rr - 1.5, -1), 1)
        meets = (0.05 <= m["monthly_return"] <= 0.15) and (0.45 <= m["win_rate"] <= 0.55) \
            and (m["realized_rr"] >= 1.5)

        rows.append({
            "tp_%": round(p.tp_pct * 100, 1), "sl_%": round(p.max_sl_pct * 100, 1),
            "top_n": top_n, "risk_%": round(p.risk_per_trade * 100, 1),
            "trades": m["num_trades"],
            "n_win": m["n_win"], "n_loss": m["n_loss"],
            "gross_win": m["gross_win"], "gross_loss": m["gross_loss"],
            "monthly_%": round(m["monthly_return"] * 100, 2),
            "total_%": round(m["total_return"] * 100, 2),
            "win_%": round(m["win_rate"] * 100, 1),
            "rr": None if m["realized_rr"] == float("inf") else round(m["realized_rr"], 2),
            "maxdd_%": round(m["max_drawdown"] * 100, 2),
            "stability": round(stab, 2),
            "meets_target": bool(meets),
            "score": round(score, 3),
        })
        if progress_cb:
            progress_cb(len(rows), total, rows[-1])

    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    return df


DEFAULT_GRID = {
    "tp_pct": [0.02, 0.03, 0.04, 0.05],
    "max_sl_pct": [0.015, 0.02, 0.03],
    "top_n": [5, 10],
    "risk_per_trade": [0.02],
}
