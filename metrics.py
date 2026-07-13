"""Tính chỉ số hiệu quả và đối chiếu mục tiêu."""
import numpy as np
import pandas as pd

TARGETS = {
    "monthly_return": (0.05, 0.15),   # 5%–15% / tháng
    "win_rate": (0.45, 0.55),         # 45%–55%
    "realized_rr": (1.5, None),       # >= 1:1,5
}


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
        "avg_win": avg_win, "avg_loss": avg_loss,
        "realized_rr": (avg_win / -avg_loss) if avg_loss < 0 else float("inf"),
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy_r": np.mean([t.r_multiple for t in trades]) if n else 0.0,
        "max_drawdown": max_dd, "exit_reasons": reasons,
    }


def monthly_table(res) -> pd.DataFrame:
    """Bảng lợi nhuận thực hiện theo tháng (dựa trên thời điểm THOÁT lệnh)."""
    rows = [(t.exit_time, t.pnl) for t in res.trades if t.exit_time is not None]
    if not rows:
        return pd.DataFrame(columns=["month", "pnl", "trades"])
    df = pd.DataFrame(rows, columns=["exit_time", "pnl"])
    df["month"] = pd.to_datetime(df["exit_time"]).dt.tz_localize(None).dt.to_period("M").astype(str)
    g = df.groupby("month").agg(pnl=("pnl", "sum"), trades=("pnl", "size")).reset_index()
    return g


def print_report(res) -> dict:
    m = summarize(res)
    pct = lambda x: f"{x*100:,.2f}%"
    line = "─" * 60
    print(line); print("  KẾT QUẢ BACKTEST — Chiến lược Swing Stoch RSI"); print(line)
    print(f"  Vốn ban đầu        : ${m['initial_capital']:,.2f}")
    print(f"  Vốn cuối kỳ        : ${m['final_equity']:,.2f}")
    print(f"  Số ngày            : {m['days']}")
    print(f"  Tổng lợi nhuận     : {pct(m['total_return'])}")
    print(f"  LN trung bình/tháng: {pct(m['monthly_return'])}")
    print(f"  Số lệnh            : {m['num_trades']}")
    print(f"  Tỷ lệ thắng        : {pct(m['win_rate'])}")
    print(f"  R:R thực tế        : {m['realized_rr']:.2f}  (Lời TB / Lỗ TB)")
    print(f"  Profit factor      : {m['profit_factor']:.2f}")
    print(f"  Kỳ vọng mỗi lệnh   : {m['expectancy_r']:.3f} R")
    print(f"  Drawdown tối đa    : {pct(m['max_drawdown'])}")
    print(f"  Lý do thoát        : {m['exit_reasons']}")
    print(line); print("  ĐỐI CHIẾU MỤC TIÊU"); print(line)

    def chk(name, val, lo, hi, is_pct=True):
        ok = val >= lo and (hi is None or val <= hi)
        if is_pct:
            rng = f">= {lo*100:.0f}%" if hi is None else f"{lo*100:.0f}%–{hi*100:.0f}%"
            sval = f"{val*100:6.2f}%"
        else:
            rng = f">= {lo}" if hi is None else f"{lo}–{hi}"
            sval = f"{val:6.2f} "
        print(f"  {name:<20}: {sval}  (mục tiêu {rng})  {'✔ ĐẠT' if ok else '✘ CHƯA'}")
        return ok

    ok1 = chk("LN/tháng", m["monthly_return"], *TARGETS["monthly_return"])
    ok2 = chk("Tỷ lệ thắng", m["win_rate"], *TARGETS["win_rate"])
    ok3 = chk("R:R thực tế", m["realized_rr"], TARGETS["realized_rr"][0], None, is_pct=False)
    print(line)
    print("  KẾT LUẬN:", "ĐẠT TOÀN BỘ MỤC TIÊU" if (ok1 and ok2 and ok3)
          else "CHƯA ĐẠT ĐỦ — cần tinh chỉnh hoặc xem lại chiến lược")
    print(line)
    return m
