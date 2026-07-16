"""Tính chỉ số hiệu quả + đối chiếu mục tiêu."""
import numpy as np
import pandas as pd

TARGETS = {"monthly_return": (0.05, 0.15), "win_rate": (0.45, 0.55), "realized_rr": (1.5, None)}


def summarize(res) -> dict:
    ec, trades = res.equity_curve, res.trades
    final = float(ec.iloc[-1]) if len(ec) else res.initial_capital
    total_return = final / res.initial_capital - 1
    days = (ec.index[-1] - ec.index[0]).days if len(ec) > 1 else 0
    months = max(days / 30.44, 1e-9)
    monthly = (1 + total_return) ** (1 / months) - 1 if total_return > -1 else -1.0
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    n = len(trades)
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0.0
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    roll_max = ec.cummax()
    max_dd = float((ec / roll_max - 1).min()) if len(ec) else 0.0
    reasons = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    return {
        "initial_capital": res.initial_capital, "final_equity": final,
        "total_return": total_return, "days": days, "monthly_return": monthly,
        "num_trades": n, "win_rate": len(wins) / n if n else 0.0,
        "n_win": len(wins), "n_loss": len(losses),
        "gross_win": round(gross_win, 2), "gross_loss": round(-gross_loss, 2),
        "avg_win": avg_win, "avg_loss": avg_loss,
        "realized_rr": (avg_win / -avg_loss) if avg_loss < 0 else float("inf"),
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_r": np.mean([t.r_multiple for t in trades]) if n else 0.0,
        "max_drawdown": max_dd, "exit_reasons": reasons,
    }


def monthly_table(res) -> pd.DataFrame:
    rows = [(t.exit_time, t.pnl) for t in res.trades if t.exit_time is not None]
    if not rows:
        return pd.DataFrame(columns=["month", "pnl", "trades"])
    df = pd.DataFrame(rows, columns=["exit_time", "pnl"])
    df["month"] = pd.to_datetime(df["exit_time"]).dt.tz_localize(None).dt.to_period("M").astype(str)
    return df.groupby("month").agg(pnl=("pnl", "sum"), trades=("pnl", "size")).reset_index()


def print_report(res) -> dict:
    m = summarize(res)
    pct = lambda x: f"{x*100:,.2f}%"
    line = "─" * 60
    print(line); print("  KẾT QUẢ BACKTEST — Swing Stoch RSI"); print(line)
    print(f"  Vốn: ${m['initial_capital']:,.2f} → ${m['final_equity']:,.2f}")
    print(f"  Tổng LN: {pct(m['total_return'])} | LN/tháng: {pct(m['monthly_return'])}")
    print(f"  Lệnh: {m['num_trades']} | Win: {pct(m['win_rate'])} | R:R: {m['realized_rr']:.2f}")
    print(f"  Drawdown tối đa: {pct(m['max_drawdown'])} | Lý do thoát: {m['exit_reasons']}")
    print(line)
    return m
