# -*- coding: utf-8 -*-
"""
Codex alpha experiment: keep the validated strong3 base sleeve, but narrow the
stock satellite sleeve to filters that were positive in both historical windows.

Outputs are written to this folder, not to the original 02_回测报告 folder.
"""
import os
import sys
import datetime as dt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.dirname(os.path.abspath(__file__))
HELPER = os.path.join(ROOT, "数据助手")
SITE_PACKAGES = os.path.join(HELPER, ".venv", "lib", "python3.9", "site-packages")
sys.path.insert(0, HELPER)
if os.path.isdir(SITE_PACKAGES):
    sys.path.append(SITE_PACKAGES)

import backtest as B  # noqa: E402
import portfolio_backtest as PB  # noqa: E402


_ORIGINAL_SCREEN_ONE = B.P.screen_one


def _screen_one_skip_bad_board(di_slice, board, *args, **kwargs):
    if board not in B.C.BOARDS:
        return None
    return _ORIGINAL_SCREEN_ONE(di_slice, board, *args, **kwargs)


B.P.screen_one = _screen_one_skip_bad_board


WINDOWS = [
    ("20240618", "20260630", "2024-2026"),
    ("20190101", "20231231", "2019-2023"),
]


def _num(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def codex_gate(c):
    """Two simple, pre-specified sleeves discovered from dual-window signal bins."""
    score = _num(c.get("score"))
    sec = _num(c.get("sec_rank"), 999)
    rs = _num(c.get("rs"))
    prior = _num(c.get("prior60"))
    amt = _num(c.get("amt20"))

    # Sleeve A: strong sector, short-term pullback/left-side repair, small tradable liquidity.
    pullback_repair = sec <= 5 and rs > 0 and prior < 0 and 2 <= amt < 5

    # Sleeve B: strong score, strong sector, established but not overheated trend.
    midtrend_relay = score >= 75 and sec <= 10 and 60 <= prior < 100 and amt >= 5

    return pullback_repair or midtrend_relay


def run_one(start, end, label):
    original_base = B.BASE
    original_gate = B.live_gate
    B.BASE = OUT

    def live_gate_with_codex(c):
        return original_gate(c) and codex_gate(c)

    B.live_gate = live_gate_with_codex
    try:
        tag = f"codex_alpha_{label}"
        curve, trades, kills, win_dates, meta = PB.run_portfolio(
            start, end, tag, base_mode="strong3", no_satellite=False
        )
        PB.report(curve, trades, kills, win_dates, f"{tag}_base-strong3", meta)
        return curve, trades, kills
    finally:
        B.live_gate = original_gate
        B.BASE = original_base


def summarize(results):
    lines = [
        "# Codex Alpha 组合实验摘要\n",
        f"- 生成时间：{dt.datetime.now():%Y-%m-%d %H:%M}",
        "- 设计：底仓沿用 strong3；卫星层只做两个双窗口为正的过滤器。",
        "- 过滤器A：强主线、RS>0、60日涨幅<0、20日日均成交额2-5亿。",
        "- 过滤器B：评分>=75、板块排名<=10、60日涨幅60-100%、20日日均成交额>=5亿。\n",
        "| 窗口 | 总收益 | 最大回撤 | Sharpe | 平均敞口 | 平仓笔数 | 胜率 | 平均R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    import numpy as np
    import pandas as pd

    for label, curve, trades in results:
        eq = curve["equity"].values
        ret = pd.Series(eq).pct_change().dropna()
        total = eq[-1] / PB.INIT_CAPITAL - 1
        peak = np.maximum.accumulate(eq)
        mdd = ((eq - peak) / peak).min()
        sharpe = ret.mean() / ret.std() * np.sqrt(244) if len(ret) > 2 and ret.std() else float("nan")
        n = len(trades)
        win = (trades["pnl"] > 0).mean() if n else float("nan")
        avg_r = trades["R"].mean() if n else float("nan")
        lines.append(
            f"| {label} | {total*100:.1f}% | {mdd*100:.1f}% | {sharpe:.2f} | "
            f"{curve['exposure'].mean()*100:.1f}% | {n} | {win*100:.1f}% | {avg_r:.3f} |"
        )

    lines.extend(
        [
            "\n## 判读",
            "- 这是组合级回测：包含 T+1、仓位上限、回撤降档、熔断、成本与滑点。",
            "- 它不是参数扫描后的最终答案，而是把蒸馏框架中的“强主线核心、买分歧、避开极端过热”变成可复验的候选策略。",
            "- 是否采纳应看两个窗口与现任 strong3 基线的比较，并进入前向并行记账。",
        ]
    )
    with open(os.path.join(OUT, "Codex Alpha 组合实验摘要.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    import pandas as pd

    all_results = []
    for start, end, label in WINDOWS:
        tag = f"codex_alpha_{label}_base-strong3"
        curve_path = os.path.join(OUT, f"portfolio_curve_{tag}.csv")
        trades_path = os.path.join(OUT, f"portfolio_trades_{tag}.csv")
        if os.path.exists(curve_path) and os.path.exists(trades_path):
            curve = pd.read_csv(curve_path)
            trades = pd.read_csv(trades_path)
        else:
            curve, trades, kills = run_one(start, end, label)
        all_results.append((label, curve, trades))
    summarize(all_results)
    print("Codex alpha experiment complete.")
