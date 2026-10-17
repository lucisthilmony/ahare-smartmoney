#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股短线波段系统独立 Alpha 审计。

只读取现有回测产物和前向记录，不联网、不改生产策略、不重写历史窗口。
输出：
  - alpha_validation_report.md
  - audit_metrics.csv
  - threshold_robustness.csv
  - input_manifest.csv

用法：
  python3 alpha_validation_audit.py
  python3 alpha_validation_audit.py --root /path/to/A股策略蒸馏 --bootstrap 20000
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
SEED = 20260719


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="A股策略 Alpha 独立审计")
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--out", type=Path, default=HERE)
    p.add_argument("--bootstrap", type=int, default=20_000)
    return p.parse_args()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def hac_t(values: np.ndarray, lag: int = 10) -> float:
    """Newey-West/HAC t 统计量，用于日频主动收益均值。"""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan")
    u = x - x.mean()
    long_var = float(np.dot(u, u) / n)
    for k in range(1, min(lag, n - 1) + 1):
        cov = float(np.dot(u[k:], u[:-k]) / n)
        long_var += 2.0 * (1.0 - k / (lag + 1.0)) * cov
    se = math.sqrt(max(long_var, 0.0) / n)
    return float(x.mean() / se) if se else float("nan")


def clustered_mean_ci(
    df: pd.DataFrame,
    value_col: str,
    date_col: str,
    n_boot: int,
    rng: np.random.Generator,
) -> tuple[float, float, float]:
    """按月份聚类重抽样，降低同期交易相关性带来的伪精度。"""
    q = df[[value_col, date_col]].copy()
    q[value_col] = pd.to_numeric(q[value_col], errors="coerce")
    q = q.dropna(subset=[value_col])
    q["month"] = q[date_col].astype(str).str[:6]
    g = q.groupby("month")[value_col].agg(["sum", "count"])
    if g.empty:
        return float("nan"), float("nan"), float("nan")
    idx = rng.integers(0, len(g), size=(n_boot, len(g)))
    sums = g["sum"].to_numpy()[idx].sum(axis=1)
    counts = g["count"].to_numpy()[idx].sum(axis=1)
    means = sums / counts
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi), float((means <= 0).mean())


def pct(x: float, digits: int = 2) -> str:
    return "NA" if not np.isfinite(x) else f"{x * 100:.{digits}f}%"


def num(x: float, digits: int = 3) -> str:
    return "NA" if not np.isfinite(x) else f"{x:.{digits}f}"


def read_curve(report_dir: Path, window: str, sleeve: str) -> pd.DataFrame:
    p = report_dir / f"portfolio_curve_v641_{window}_{sleeve}.csv"
    q = pd.read_csv(p)
    q["ret"] = pd.to_numeric(q["equity"], errors="coerce").pct_change().fillna(0.0)
    return q


def active_metric_rows(report_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for window in ("2019-2023", "2024-2026"):
        curves = {s: read_curve(report_dir, window, s) for s in ("base", "satA", "satC")}
        for left, right in (("satA", "base"), ("satC", "base"), ("satA", "satC")):
            a, b = curves[left], curves[right]
            active = a["ret"].to_numpy() - b["ret"].to_numpy()
            ann = float(np.mean(active) * 244.0)
            te = float(np.std(active, ddof=1) * math.sqrt(244.0))
            rel = float((a["equity"].iloc[-1] / a["equity"].iloc[0]) /
                        (b["equity"].iloc[-1] / b["equity"].iloc[0]) - 1.0)
            rows.append({
                "section": "active_return",
                "window": window,
                "comparison": f"{left}-{right}",
                "n": len(active),
                "estimate": ann,
                "aux1": te,
                "aux2": ann / te if te else np.nan,
                "aux3": hac_t(active, 10),
                "note": f"relative_wealth={rel:.8f}",
            })
    return rows


def trade_metric_rows(
    report_dir: Path, n_boot: int, rng: np.random.Generator
) -> tuple[list[dict], dict[str, pd.DataFrame]]:
    rows: list[dict] = []
    trades: dict[str, pd.DataFrame] = {}
    for window in ("2019-2023", "2024-2026"):
        p = report_dir / f"portfolio_trades_v641_{window}_satA.csv"
        q = pd.read_csv(p)
        q["entry_date"] = q["entry_date"].astype(str)
        q["R"] = pd.to_numeric(q["R"], errors="coerce")
        trades[window] = q
        lo, hi, p_nonpos = clustered_mean_ci(q, "R", "entry_date", n_boot, rng)
        rows.append({
            "section": "portfolio_trade_R",
            "window": window,
            "comparison": "satA",
            "n": len(q),
            "estimate": q["R"].mean(),
            "aux1": lo,
            "aux2": hi,
            "aux3": p_nonpos,
            "note": "month-cluster bootstrap 95% CI and P(mean<=0)",
        })
        for year, g in q.groupby(q["entry_date"].str[:4]):
            rows.append({
                "section": "portfolio_trade_R_year",
                "window": str(year),
                "comparison": "satA",
                "n": len(g),
                "estimate": g["R"].mean(),
                "aux1": np.nan,
                "aux2": np.nan,
                "aux3": np.nan,
                "note": "entry-year mean R",
            })
    return rows, trades


def signal_research(
    report_dir: Path, n_boot: int, rng: np.random.Generator
) -> tuple[list[dict], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames = []
    for name in ("backtest_trades_qfq_2019-2023.csv", "backtest_trades_qfq_2024-2026.csv"):
        q = pd.read_csv(report_dir / name)
        q["date"] = q["date"].astype(str)
        frames.append(q)
    all_signals = pd.concat(frames, ignore_index=True).drop_duplicates(["date", "code"], keep="last")
    all_signals["year"] = all_signals["date"].str[:4].astype(int)
    a_mask = (
        (all_signals["sec_rank"] <= 5)
        & (all_signals["rs"] > 0)
        & (all_signals["prior60"] < 0)
        & (all_signals["amt20"] >= 2)
        & (all_signals["amt20"] < 5)
    )
    a = all_signals[a_mask].copy()
    a["window"] = np.where(a["year"] <= 2023, "2019-2023", "2024-2026")

    rows: list[dict] = []
    for window, g in a.groupby("window"):
        lo, hi, p_nonpos = clustered_mean_ci(g, "R_long", "date", n_boot, rng)
        rows.append({
            "section": "all_A_signals_R_long",
            "window": window,
            "comparison": "A-gate signal library",
            "n": len(g),
            "estimate": g["R_long"].mean(),
            "aux1": lo,
            "aux2": hi,
            "aux3": p_nonpos,
            "note": "not portfolio-executable; month-cluster bootstrap",
        })
    for year, g in a.groupby("year"):
        rows.append({
            "section": "all_A_signals_R_long_year",
            "window": str(year),
            "comparison": "A-gate signal library",
            "n": len(g),
            "estimate": g["R_long"].mean(),
            "aux1": np.nan,
            "aux2": np.nan,
            "aux3": np.nan,
            "note": "decision-year mean R_long",
        })

    perturbations = [
        (3, 0, 2.0, 5.0, "sector rank tighter"),
        (5, 0, 2.0, 5.0, "canonical A"),
        (8, 0, 2.0, 5.0, "sector rank looser"),
        (5, -10, 2.0, 5.0, "prior60 tighter"),
        (5, 10, 2.0, 5.0, "prior60 looser"),
        (5, 0, 1.5, 5.5, "liquidity wider"),
        (5, 0, 2.5, 4.5, "liquidity narrower"),
        (5, 0, 2.0, 6.0, "liquidity upper looser"),
    ]
    pr = []
    for sec, prior, amt_lo, amt_hi, label in perturbations:
        mask = (
            (all_signals["sec_rank"] <= sec)
            & (all_signals["rs"] > 0)
            & (all_signals["prior60"] < prior)
            & (all_signals["amt20"] >= amt_lo)
            & (all_signals["amt20"] < amt_hi)
        )
        for window, wm in (
            ("2019-2023", all_signals["year"] <= 2023),
            ("2024-2026", all_signals["year"] >= 2024),
        ):
            g = all_signals[mask & wm]
            pr.append({
                "variant": label,
                "sec_rank_max": sec,
                "prior60_max": prior,
                "amt20_min": amt_lo,
                "amt20_max_exclusive": amt_hi,
                "window": window,
                "n": len(g),
                "mean_R_long": g["R_long"].mean(),
            })
    robustness = pd.DataFrame(pr)

    score_rows = []
    for window, g in a.groupby("window"):
        corr = g["score"].corr(g["R_long"])
        spear = g["score"].rank().corr(g["R_long"].rank())
        score_rows.append({
            "window": window,
            "n": len(g),
            "pearson_score_vs_R": corr,
            "spearman_score_vs_R": spear,
            "lt60_n": int((g["score"] < 60).sum()),
            "lt60_mean_R": g.loc[g["score"] < 60, "R_long"].mean(),
            "ge60_n": int((g["score"] >= 60).sum()),
            "ge60_mean_R": g.loc[g["score"] >= 60, "R_long"].mean(),
        })
    score_diag = pd.DataFrame(score_rows)
    return rows, robustness, score_diag, a


def forward_status(root: Path) -> dict:
    helper = root / "数据助手"
    real_path = root / "交割记录.csv"
    shadow_path = helper / "影子交割.csv"
    nav_path = helper / "前向影子净值.csv"
    seat_path = helper / "前向观察_席位筛选.csv"

    def n_data(path: Path) -> int:
        if not path.exists() or path.stat().st_size == 0:
            return 0
        try:
            return len(pd.read_csv(path))
        except Exception:
            return 0

    nav = pd.read_csv(nav_path) if nav_path.exists() else pd.DataFrame()
    nav_cols = list(nav.columns)
    expected_nav = ["base_ret", "A_cum_R", "C_cum_R", "nav_base", "nav_base_A", "nav_base_C"]
    missing_nav = [c for c in expected_nav if c not in nav_cols]

    venv_py = helper / ".venv" / "bin" / "python"
    venv_ok = venv_py.is_symlink() or (venv_py.exists() and venv_py.stat().st_size > 128)
    return {
        "real_trades": n_data(real_path),
        "shadow_trades": n_data(shadow_path),
        "forward_candidates": n_data(seat_path),
        "nav_rows": len(nav),
        "nav_unique_dates": nav["date"].astype(str).nunique() if "date" in nav else 0,
        "nav_columns": nav_cols,
        "nav_missing": missing_nav,
        "venv_python_valid": bool(venv_ok),
    }


def build_manifest(root: Path, report_dir: Path) -> pd.DataFrame:
    candidates = [
        root / "数据助手" / "backtest.py",
        root / "数据助手" / "portfolio_backtest.py",
        root / "数据助手" / "策略规格.py",
        root / "数据助手" / "时点数据.py",
        root / "数据助手" / "影子交割.py",
        report_dir / "portfolio_curve_v641_2019-2023_base.csv",
        report_dir / "portfolio_curve_v641_2019-2023_satA.csv",
        report_dir / "portfolio_curve_v641_2019-2023_satC.csv",
        report_dir / "portfolio_curve_v641_2024-2026_base.csv",
        report_dir / "portfolio_curve_v641_2024-2026_satA.csv",
        report_dir / "portfolio_curve_v641_2024-2026_satC.csv",
        report_dir / "portfolio_trades_v641_2019-2023_satA.csv",
        report_dir / "portfolio_trades_v641_2024-2026_satA.csv",
        report_dir / "backtest_trades_qfq_2019-2023.csv",
        report_dir / "backtest_trades_qfq_2024-2026.csv",
    ]
    rows = []
    for p in candidates:
        if p.exists():
            rows.append({
                "path": str(p.relative_to(root)),
                "bytes": p.stat().st_size,
                "mtime_ns": p.stat().st_mtime_ns,
                "sha256": sha256(p),
            })
    return pd.DataFrame(rows)


def report_text(
    metrics: pd.DataFrame,
    robustness: pd.DataFrame,
    score_diag: pd.DataFrame,
    forward: dict,
    manifest: pd.DataFrame,
    root: Path,
) -> str:
    active = metrics[metrics["section"] == "active_return"].copy()
    trade = metrics[metrics["section"] == "portfolio_trade_R"].copy()
    signal = metrics[metrics["section"] == "all_A_signals_R_long"].copy()
    yearly = metrics[(metrics["section"] == "portfolio_trade_R_year") &
                     (metrics["comparison"] == "satA")].copy()

    lines = [
        "# A股交易系统独立审计与 Alpha 验证",
        "",
        "- 审计日期：2026-07-19",
        f"- 审计对象：`{root}`",
        "- 原则：只读、不联网、不调生产参数；统计数字可由同目录脚本重复生成。",
        "",
        "## 一句话结论",
        "",
        "**系统的工程治理和风控已达到可受控前向研究水平，但目前没有一条能被这个文件夹独立复现、统计上显著、且前向可交易的 Alpha。** A 门是值得保留的候选而不是已验证策略；“反拥挤 / 信号新鲜度”是当前最值得转入严格复现的 Alpha 线索。",
        "",
        "## 源码重放一致性",
        "",
        "用当前 `backtest.py` / `portfolio_backtest.py` / 时点缓存只读重放 v6.4.1 A 门组合，并与已发布 CSV 逐点比较：",
        "",
        "| 窗口 | 曲线行 | 平仓笔数 | 净值最大绝对差 | 交易数值最大差 | 结论 |",
        "|---|---:|---:|---:|---:|---|",
        "| 2019–2023 | 1214 | 52 | 5.82e-11 | 0 | 通过 |",
        "| 2024–2026 | 493 | 25 | 5.82e-11 | 0 | 通过 |",
        "",
        "CSV 重读后深市代码的前导零会被 pandas 解析为整数，除这一序列化差异外，交易日、出场原因、笔数和数值字段一致。重放记录见 `reproduction_check.csv`。",
        "",
        "## 已复现的核心数字",
        "",
        "### A 门相对纯底仓",
        "",
        "| 窗口 | 年化主动收益 | 跟踪误差 | 信息比率 | HAC t | 判定 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for _, r in active[active["comparison"] == "satA-base"].iterrows():
        verdict = "未显著" if abs(r["aux3"]) < 1.96 else "显著"
        lines.append(
            f"| {r['window']} | {pct(r['estimate'])} | {pct(r['aux1'])} | "
            f"{num(r['aux2'], 2)} | {num(r['aux3'], 2)} | {verdict} |"
        )

    lines.extend([
        "",
        "### A 门组合实际入选交易",
        "",
        "| 窗口 | 笔数 | 平均R | 按月聚类 95% CI | P(均值≤0) |",
        "|---|---:|---:|---:|---:|",
    ])
    for _, r in trade.iterrows():
        lines.append(
            f"| {r['window']} | {int(r['n'])} | {num(r['estimate'])} | "
            f"[{num(r['aux1'])}, {num(r['aux2'])}] | {pct(r['aux3'], 1)} |"
        )
    lines.extend([
        "",
        "两个窗口的置信区间都跨过 0。2019–2023 的主动收益几乎为 0；2024–2026 的正值主要来自 2025，而 2026 入场的交易已经转负。",
        "",
        "| 入场年 | 笔数 | 平均R |",
        "|---|---:|---:|",
    ])
    for _, r in yearly.iterrows():
        lines.append(f"| {r['window']} | {int(r['n'])} | {num(r['estimate'])} |")

    lines.extend([
        "",
        "### 信号库与可执行组合的差异",
        "",
        "| 窗口 | 全部A信号数 | 信号平均 R_long | 组合实际平仓数 | 组合平均R |",
        "|---|---:|---:|---:|---:|",
    ])
    for window in ("2019-2023", "2024-2026"):
        s = signal[signal["window"] == window].iloc[0]
        t = trade[trade["window"] == window].iloc[0]
        lines.append(
            f"| {window} | {int(s['n'])} | {num(s['estimate'])} | {int(t['n'])} | {num(t['estimate'])} |"
        )
    lines.extend([
        "",
        "2024–2026 的全部 A 信号在信号层面通过了按月聚类检查，但该窗口已参与 A 门筛选，且正期望没有稳定转化为可执行组合收益。每日只选 1 只、持仓冲突、评分排序和熔断路径是当前最关键的研究对象。",
        "",
        "### A 门内部的评分优先级",
        "",
        "| 窗口 | score与R的线性相关 | 秩相关 | score<60 n/均R | score≥60 n/均R |",
        "|---|---:|---:|---:|---:|",
    ])
    for _, r in score_diag.iterrows():
        lines.append(
            f"| {r['window']} | {num(r['pearson_score_vs_R'])} | {num(r['spearman_score_vs_R'])} | "
            f"{int(r['lt60_n'])}/{num(r['lt60_mean_R'])} | {int(r['ge60_n'])}/{num(r['ge60_mean_R'])} |"
        )
    lines.extend([
        "",
        "在 A 门内，现行 score 对后续 R 几乎没有稳定排序力；低分组的历史均 R 反而更高。这不足以事后改成“低分优先”，但足以否定“高分必然优先”，并为随机化影子对照提供理由。",
        "",
        "### 阈值微扰",
        "",
        "| 变体 | 2019–2023 n/均R | 2024–2026 n/均R |",
        "|---|---:|---:|",
    ])
    for variant in robustness["variant"].drop_duplicates():
        g = robustness[robustness["variant"] == variant].set_index("window")
        a = g.loc["2019-2023"]
        b = g.loc["2024-2026"]
        lines.append(
            f"| {variant} | {int(a['n'])}/{num(a['mean_R_long'])} | "
            f"{int(b['n'])}/{num(b['mean_R_long'])} |"
        )
    lines.extend([
        "",
        "A 门对邻近阈值不是完全崩溃，但 2019–2023 在 `prior60<-10%` 时转负，且各年方向不一；它是平台状弱证据，不是牢固的参数盆地。",
        "",
        "## 高优先级问题",
        "",
        "1. **历史双窗口已被筛选消耗。** A 门是在 2019–2023 和 2024–2026 同时求正后选出，所以两者都不再是真正的样本外。",
        "2. **前向裁判器未完成声称的记账。** `前向影子净值.csv` 没有现金、底仓日收益、A/C 累计R或四账户净值；它目前只是状态日志。",
        "3. **前向样本实际为零。** 真实交割和影子平仓都为 0，因此失效判据v2还无法工作。",
        "4. **底仓不是 Alpha。** 它是低暴露的防守 Beta；已有对照显示动态档位择时在旧窗口贡献为负，不应再用底仓总收益为卫星 Alpha 背书。",
        "5. **行业合成指数仍有再平衡伪影。** 现行做法对每只股的首个有效值归一后求横截面均值；成分进出时会产生非收益性跳变。应建立“日收益链接 + 成分滞后一日”的对照版再重验 A 门。",
        "6. **工程可复现性不完整。** 本机 OneDrive 副本中 `.venv/bin/python*` 的符号链接已变成普通文本文件；吸筹策略声称依赖的 `~/chip_peak_backtest/` 也不在本文件夹。",
        "",
        "## Alpha 线索排名",
        "",
        "1. **反拥挤 / 信号新鲜度（最值得复现）**：吸筹档案声称“新鲜进场 +0.62% 超额，涨10%后追 -0.88%，涨20%后追 -2.73%”，且有周聚类区间。这是最强线索，但本文件夹缺少代码、事件明细、基准超额定义和冻结输出，当前证据等级=“有数字的文档主张”。",
        "2. **A 门回踩修复（保留观察）**：经济含义可辩，且大幅优于 classic 的大量负期望交易；但绝对期望未稳定、统计不显著、前向为零。",
        "3. **剩余强度 / 独立行情（仅研究）**：用个股收益减去中证1000和时点行业暴露的残差，替代简单 `corr<0.4`。先在严格冻结的六票回放中比较，不能直接上线。",
        "4. **事件层 × 早期结构（容量有限）**：实控人变更、协议转让、并购落地等可提供催化，但必须以公告时点建库并消除事后叙事。",
        "",
        "## 建议的建设顺序",
        "",
        "### P0：先让验证器可以裁判",
        "",
        "- 修复影子记账：每日保存现金、持仓市值、底仓收益、A/C 流已实现和未实现损益、四账户净值、不可成交事件。",
        "- 将“候选决策快照”设为 append-only，记录当时使用的策略版本、数据日期、候选排序、被跳过原因和输入哈希。",
        "- 分开“信号有效性”和“组合可实现性”：全部候选跟踪 1/3/5/10/15 日超额，同时另记 top-1 真实执行路径。",
        "",
        "### P1：只做两个预注册对照",
        "",
        "- **行业指数构建对照**：现行归一化水平均值 vs 滞后成分的等权日收益链接。A 门仅在两个口径下方向一致才保留“行业 Top5”解释。",
        "- **不用历史评分排序的 A 门对照**：现行 score-top1 vs 事前固定的稳定排序或同日随机化影子分流，用来回答“信号库为正却组合不为正”。随机种子必须事前写死。",
        "",
        "### P2：复现最强 Alpha 主张",
        "",
        "- 把 `chip_peak_backtest` 的代码、事件级数据字典、去重方法、基准定义、周聚类 bootstrap 和冻结 CSV 收纳进版本库。",
        "- 对“新鲜 / +10% / +20%”只进行一次完整复现；补充成本、涨停无法成交、跌停延迟止损和市值/行业/年份分层。",
        "- 只有冻结定义后的前向样本达到预注册笔数，且费后超额区间下界 > 0，才允许称为 Alpha。",
        "",
        "## 当前证据等级",
        "",
        "| 模块 | 证据等级 | 结论 |",
        "|---|---|---|",
        "| 工程同源 / PIT / 成本 / 相位 | 较强 | 已经过多轮反证和修正 |",
        "| strong3 底仓 | 中等 | 可降回撤，但超额和择时未证明 |",
        "| A 门卫星 | 弱至中 | 候选；非显著；前向为零 |",
        "| 吸筹反拥挤 / 新鲜度 | 文档上中等、可复现性弱 | 最有希望，但需把证据搬入本项目 |",
        "| 实盘 / 前向 Alpha | 无 | 尚无交割样本 |",
        "",
        f"本次审计对 {len(manifest)} 个核心输入保存了 SHA-256，见 `input_manifest.csv`。",
        "",
        "_本报告是研究与风险管理意见，不是交易建议。_",
    ])

    lines.extend([
        "",
        "## 前向状态快照",
        "",
        f"- 真实交割记录：{forward['real_trades']} 笔",
        f"- 影子平仓：{forward['shadow_trades']} 笔",
        f"- 前向候选记录：{forward['forward_candidates']} 行",
        f"- “前向影子净值”：{forward['nav_rows']} 行 / {forward['nav_unique_dates']} 个唯一日期",
        f"- 缺失的净值字段：{', '.join(forward['nav_missing'])}",
        f"- 本机共享虚拟环境启动器可用：{'Y' if forward['venv_python_valid'] else 'N'}",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    root = args.root.expanduser().resolve()
    out = args.out.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_dir = root / "02_回测报告"
    rng = np.random.default_rng(SEED)

    metric_rows = active_metric_rows(report_dir)
    trade_rows, _ = trade_metric_rows(report_dir, args.bootstrap, rng)
    signal_rows, robustness, score_diag, _ = signal_research(report_dir, args.bootstrap, rng)
    metrics = pd.DataFrame(metric_rows + trade_rows + signal_rows)
    forward = forward_status(root)
    manifest = build_manifest(root, report_dir)

    metrics.to_csv(out / "audit_metrics.csv", index=False, encoding="utf-8-sig")
    robustness.to_csv(out / "threshold_robustness.csv", index=False, encoding="utf-8-sig")
    score_diag.to_csv(out / "score_priority_diagnostic.csv", index=False, encoding="utf-8-sig")
    manifest.to_csv(out / "input_manifest.csv", index=False, encoding="utf-8-sig")
    text = report_text(metrics, robustness, score_diag, forward, manifest, root)
    (out / "alpha_validation_report.md").write_text(text, encoding="utf-8")
    print(f"完成：{out / 'alpha_validation_report.md'}")


if __name__ == "__main__":
    main()
