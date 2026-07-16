"""Quét tham số (param scan) + kiểm định ngoài mẫu (walk-forward optimize)."""
import itertools
import pandas as pd

from strategy import Params
from backtest import run_backtest, gainer_eligibility
from metrics import summarize
from validate import walk_forward


def _stability(data, p, capital, splits=3):
    wf = walk_forward(data, splits=splits, p=p, initial_capital=capital)
    if wf.empty:
        return 0.0
    return (wf["monthly_%"] > 0).sum() / len(wf)


def param_scan(data, grid: dict, capital=1000.0, top_n_default=10, min_trades=10,
               use_gainer_filter=True, splits=3, progress_cb=None, base_params=None) -> pd.DataFrame:
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    total = len(combos)
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
        elig = get_elig(top_n, 0.40)
        m = summarize(run_backtest(data, p, initial_capital=capital, eligible=elig))
        stab = _stability(data, p, capital, splits=splits)
        enough = m["num_trades"] >= min_trades
        rr = m["realized_rr"] if m["realized_rr"] != float("inf") else 3.0
        score = (m["monthly_return"] * 100) * (1 if enough else 0.3) + stab * 2 \
            + min(max(rr - 1.5, -1), 1)
        meets = (0.05 <= m["monthly_return"] <= 0.15) and (0.45 <= m["win_rate"] <= 0.55) \
            and (m["realized_rr"] >= 1.5)
        rows.append({
            "tp_%": round(p.tp_pct * 100, 1), "sl_%": round(p.max_sl_pct * 100, 1),
            "top_n": top_n, "risk_%": round(p.risk_per_trade * 100, 1),
            "trades": m["num_trades"], "n_win": m["n_win"], "n_loss": m["n_loss"],
            "gross_win": m["gross_win"], "gross_loss": m["gross_loss"],
            "monthly_%": round(m["monthly_return"] * 100, 2),
            "total_%": round(m["total_return"] * 100, 2),
            "win_%": round(m["win_rate"] * 100, 1),
            "rr": None if m["realized_rr"] == float("inf") else round(m["realized_rr"], 2),
            "maxdd_%": round(m["max_drawdown"] * 100, 2),
            "stability": round(stab, 2), "meets_target": bool(meets), "score": round(score, 3),
        })
        if progress_cb:
            progress_cb(len(rows), total, rows[-1])
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


def slice_data(data, lo, hi):
    out = {}
    for s, (h1, d1) in data.items():
        h1s = h1[(h1.index >= lo) & (h1.index < hi)]
        d1s = d1[(d1.index >= lo - pd.Timedelta(days=15)) & (d1.index < hi)]
        if len(h1s) > 50:
            out[s] = (h1s, d1s)
    return out


def evaluate_combo(data, tp_pct, sl_pct, top_n, risk, base_params, capital):
    p = Params(**{**(base_params or {}), "tp_pct": tp_pct, "max_sl_pct": sl_pct, "risk_per_trade": risk})
    elig = gainer_eligibility(data, top_n=int(top_n))
    return summarize(run_backtest(data, p, initial_capital=capital, eligible=elig))


def walk_forward_optimize(data, grid, capital=1000.0, min_trades=10, base_params=None,
                          split_frac=0.7, progress_cb=None):
    starts = min(h1.index[0] for h1, _ in data.values())
    ends = max(h1.index[-1] for h1, _ in data.values())
    split_ts = starts + (ends - starts) * split_frac
    train = slice_data(data, starts, split_ts)
    test = slice_data(data, split_ts, ends)
    if not train or not test:
        return {"ok": False, "error": "Không đủ dữ liệu để chia train/test."}
    df = param_scan(train, grid, capital=capital, min_trades=min_trades,
                    base_params=base_params, splits=2, progress_cb=progress_cb)
    results = []
    for row in df.head(3).to_dict("records"):
        m = evaluate_combo(test, row["tp_%"] / 100, row["sl_%"] / 100, row["top_n"],
                           row["risk_%"] / 100, base_params, capital)
        results.append({
            "combo": f"TP{row['tp_%']} SL{row['sl_%']} Top{row['top_n']}",
            "train_total_%": row["total_%"], "train_win_%": row["win_%"], "train_trades": row["trades"],
            "test_total_%": round(m["total_return"] * 100, 2), "test_win_%": round(m["win_rate"] * 100, 1),
            "test_trades": m["num_trades"], "test_maxdd_%": round(m["max_drawdown"] * 100, 2),
        })
    best = results[0]
    return {"ok": True, "split_date": str(split_ts)[:10], "n_train": len(train), "n_test": len(test),
            "results": results, "generalizes": best["test_total_%"] > 0 and best["test_trades"] >= 5}


DEFAULT_GRID = {"tp_pct": [0.02, 0.03, 0.04, 0.05], "max_sl_pct": [0.015, 0.02, 0.03],
                "top_n": [5, 10], "risk_per_trade": [0.02]}
