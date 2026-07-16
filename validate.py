"""Kiểm định GĐ1: equity curve, thống kê tháng, walk-forward."""
import pandas as pd
from strategy import Params
from backtest import run_backtest
from metrics import summarize, monthly_table


def export_equity_curve(res, path="equity_curve.csv"):
    ec = res.equity_curve.copy(); ec.index.name = "time"
    ec.to_frame("equity").to_csv(path)
    return path


def export_monthly(res, path="monthly_returns.csv"):
    mt = monthly_table(res); mt.to_csv(path, index=False)
    return path, mt


def walk_forward(data, splits=3, p: Params = None, initial_capital=1000.0):
    p = p or Params()
    starts = min(h1.index[0] for h1, _ in data.values())
    ends = max(h1.index[-1] for h1, _ in data.values())
    bounds = pd.date_range(starts, ends, periods=splits + 1)
    out = []
    for i in range(splits):
        lo, hi = bounds[i], bounds[i + 1]
        sub = {}
        for s, (h1, d1) in data.items():
            h1s = h1[(h1.index >= lo) & (h1.index < hi)]
            d1s = d1[(d1.index >= lo - pd.Timedelta(days=10)) & (d1.index < hi)]
            if len(h1s) > 50:
                sub[s] = (h1s, d1s)
        if not sub:
            continue
        m = summarize(run_backtest(sub, p, initial_capital))
        out.append({
            "segment": f"{lo.date()} → {hi.date()}", "trades": m["num_trades"],
            "total_return_%": round(m["total_return"] * 100, 2),
            "monthly_%": round(m["monthly_return"] * 100, 2),
            "win_rate_%": round(m["win_rate"] * 100, 1),
            "realized_rr": round(m["realized_rr"], 2) if m["realized_rr"] != float("inf") else None,
            "max_dd_%": round(m["max_drawdown"] * 100, 2),
        })
    return pd.DataFrame(out)
