# -*- coding: utf-8 -*-
"""
底仓对照组研究（v6.4 P2 · 2026-07-10）——回答外部审查："strong3收益来自择时、择强、高Beta还是偶然？"
描述性归因研究（非采纳决策）。六条对照线，两窗口，统一简化记账（日频精确调仓至目标、无再平衡带；
成本每边0.03%按权重变化计）。与引擎版strong3（有5%带）数字略有差异属预期，同列供校验。

对照线：
  L1 状态定仓×strong3择强（=现行底仓的解析复刻）
  L2 状态定仓×固定沪深300（只择时不择强）
  L3 固定30%×strong3择强（只择强不择时）
  L4 波动率目标×strong3择强（w=min(50%, 15%/σ20年化)，预注册公式）
  L5 固定w̄×沪深300（w̄=L1两窗平均权重，同均仓Beta对照）
  L6 沪深300买入持有（w=100%）
用法：./.venv/bin/python 对照组.py → 02_回测报告/底仓对照组-2026-07-10.md
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import backtest as B
import 策略规格 as SPEC

WINDOWS = [("20240618", "20260630", "2024-2026"), ("20190101", "20231231", "2019-2023")]
COST = SPEC.ETF_COST

def window_series(start, end):
    data = B.fetch_all(start, end)
    P_ = B.prepare(data)
    wd = data["win_dates"]
    caps = []
    for d in wd:
        st = B.daily_state(P_, d)
        caps.append(st["cap"] if st else 0)
    idx = {}
    for nm in ("hs300", "gem", "star"):
        di = data["idx"][nm].sort_values("trade_date")
        idx[nm] = di.set_index("trade_date")["close"]
    off = SPEC.checkpoint_offset(wd, P._ts_query)
    # strong3 选择序列（生效标的，从检查点次日起算新标的收益）
    inst = [None] * len(wd)
    cur = "hs300"
    for i, d in enumerate(wd):
        if i % 5 == off or i == 0:
            dp = wd[i - 1] if i >= 1 else None
            if dp:
                mom = {}
                for nm, s in idx.items():
                    ss = s[s.index <= dp]
                    if len(ss) >= 21:
                        mom[nm] = ss.iloc[-1] / ss.iloc[-21] - 1
                if mom:
                    cur = max(mom, key=mom.get)
        inst[i] = cur
    # 日收益矩阵
    rets = {nm: idx[nm].pct_change().reindex(wd).fillna(0.0).values for nm in idx}
    inst_ret = np.array([rets[inst[i]][i] if i > 0 and inst[i - 1] == inst[i] else
                         (rets[inst[i - 1]][i] if i > 0 else 0.0) for i in range(len(wd))])
    # 波动率（生效标的的20日年化，用前一日为止）
    sig = np.full(len(wd), 0.20)
    for i in range(len(wd)):
        s = idx[inst[i]]
        ss = s[s.index < wd[i]].pct_change().dropna().tail(20)
        if len(ss) >= 15:
            sig[i] = max(0.05, float(ss.std() * np.sqrt(244)))
    tier_w = np.array([SPEC.BASE_TARGET.get(caps[i - 1], 0) / 100 if i > 0 else 0.0 for i in range(len(wd))])
    switch = np.array([1.0 if i > 0 and inst[i - 1] != inst[i] else 0.0 for i in range(len(wd))])
    hs_ret = rets["hs300"]
    return dict(wd=wd, tier_w=tier_w, inst_ret=inst_ret, hs_ret=hs_ret, sig=sig, switch=switch)

def nav(weights, asset_ret, switch=None):
    eq, peak, mdd, prev_w, rets = 1.0, 1.0, 0.0, 0.0, []
    for i in range(len(weights)):
        w = weights[i]
        r = w * asset_ret[i]
        cost = abs(w - prev_w) * COST + (2 * w * COST * switch[i] if switch is not None else 0)
        eq *= (1 + r - cost)
        rets.append(r - cost)
        peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
        prev_w = w
    sr = pd.Series(rets)
    sharpe = sr.mean() / sr.std() * np.sqrt(244) if sr.std() else float("nan")
    return eq - 1, mdd, sharpe

if __name__ == "__main__":
    L = ["# 底仓对照组研究（2026-07-10 · 描述性归因，非采纳决策）\n",
         "> 目的：分解strong3收益来源（择时/择强/Beta）。统一解析记账（日频精确调仓、无5%带），",
         "> 与引擎版（portfolio_backtest，含带）数字略差属预期。成本每边0.03%。\n"]
    for start, end, w in WINDOWS:
        S = window_series(start, end)
        wbar = S["tier_w"].mean()
        rows = [
            ("L1 状态×择强（现行底仓·解析版）", nav(S["tier_w"], S["inst_ret"], S["switch"])),
            ("L2 状态×固定沪深300（只择时）", nav(S["tier_w"], S["hs_ret"])),
            ("L3 固定30%×择强（只择强）", nav(np.full(len(S["wd"]), 0.30), S["inst_ret"], S["switch"])),
            ("L4 波动率目标×择强", nav(np.minimum(0.50, 0.15 / S["sig"]), S["inst_ret"], S["switch"])),
            (f"L5 固定{wbar*100:.0f}%×沪深300（同均仓Beta）", nav(np.full(len(S["wd"]), wbar), S["hs_ret"])),
            ("L6 沪深300买入持有", nav(np.ones(len(S["wd"])), S["hs_ret"])),
        ]
        L.append(f"\n## 窗口 {w}（平均档位权重 {wbar*100:.0f}%）\n")
        L.append("| 对照线 | 总收益 | 最大回撤 | Sharpe |\n|---|---|---|---|")
        for nm, (tot, mdd, sh) in rows:
            L.append(f"| {nm} | {tot*100:+.1f}% | {mdd*100:.1f}% | {sh:.2f} |")
    L.append("\n## 判读提示\n- L1−L2 ≈ 择强的贡献；L1−L3 ≈ 择时的贡献；L1−L5 ≈ 相对同均仓Beta的总主动贡献。")
    L.append("- 引擎版基线（含5%再平衡带）：样本内 +34.0%/-8.4%，样本外 -10.8%/-19.8%（v6.4）。")
    out = os.path.join(C.BASE_DIR, "02_回测报告", "底仓对照组-2026-07-10.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    B.log(f"已生成 {out}")
