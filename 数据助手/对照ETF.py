# -*- coding: utf-8 -*-
"""
ETF实际净值对照（v6.4 P3 · 2026-07-10）——回答审查："用指数点位记账 vs 实际ETF净值差多少？"
方法：strong3档位×择强的解析记账（同对照组.py口径），资产收益分别用①指数点位②ETF后复权价
（fund_daily×fund_adj）。ETF上市前的日子回落指数并计数（588000科创50ETF 2020-09上市）。
用法：./.venv/bin/python 对照ETF.py → 02_回测报告/ETF净值对照-2026-07-10.md
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import backtest as B
import 策略规格 as SPEC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
对照组 = __import__("对照组")

ETF = {"hs300": "510300.SH", "gem": "159915.SZ", "star": "588000.SH"}

def etf_series(code, start, end):
    px = P._ts_query("fund_daily", ts_code=code, start_date=start, end_date=end,
                     fields="trade_date,close").sort_values("trade_date")
    time.sleep(0.2)
    adj = P._ts_query("fund_adj", ts_code=code, start_date=start, end_date=end).sort_values("trade_date")
    time.sleep(0.2)
    df = px.merge(adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
    df["adj_close"] = df["close"] * df["adj_factor"].ffill()
    return df.set_index("trade_date")["adj_close"]

if __name__ == "__main__":
    L = ["# ETF实际净值对照（2026-07-10 · 描述性）\n",
         "> strong3解析记账，同一权重/择强序列，资产收益分别用指数点位与ETF后复权净值。",
         "> ETF上市前回落指数（计数）。差异来源=跟踪误差+折溢价+管理费。\n"]
    for start, end, w in [("20240618", "20260630", "2024-2026"), ("20190101", "20231231", "2019-2023")]:
        S = 对照组.window_series(start, end)
        wd = S["wd"]
        pull0 = (pd.Timestamp(start) - pd.Timedelta(days=40)).strftime("%Y%m%d")
        etf_px = {nm: etf_series(code, pull0, end) for nm, code in ETF.items()}
        # 重建inst序列（与window_series同逻辑不可得——用其inst_ret? 需要inst本身；window_series未返回inst，改用其内部逻辑复算）
        # 简化：直接重算inst（与对照组相同代码路径）
        data = B.fetch_all(start, end)
        idx = {nm: data["idx"][nm].sort_values("trade_date").set_index("trade_date")["close"]
               for nm in ("hs300", "gem", "star")}
        off = SPEC.checkpoint_offset(wd, P._ts_query)
        inst, cur = [None] * len(wd), "hs300"
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
        fallback = 0
        def ret_at(nm, i, use_etf):
            if i == 0: return 0.0, False
            d0, d1 = wd[i - 1], wd[i]
            if use_etf:
                s = etf_px[nm]
                if d0 in s.index and d1 in s.index and pd.notna(s[d0]) and pd.notna(s[d1]):
                    return float(s[d1] / s[d0] - 1), False
            s = idx[nm]
            if d0 in s.index and d1 in s.index:
                return float(s[d1] / s[d0] - 1), use_etf
            return 0.0, False
        rows = []
        for label, use_etf in (("指数点位", False), ("ETF后复权净值", True)):
            eq, peak, mdd, prev_w, fb = 1.0, 1.0, 0.0, 0.0, 0
            for i in range(len(wd)):
                nm = inst[i - 1] if (i > 0 and inst[i - 1] != inst[i]) else inst[i]
                r, fell = ret_at(nm, i, use_etf)
                fb += 1 if fell else 0
                wgt = S["tier_w"][i]
                cost = abs(wgt - prev_w) * SPEC.ETF_COST + (2 * wgt * SPEC.ETF_COST * S["switch"][i])
                eq *= (1 + wgt * r - cost)
                peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
                prev_w = wgt
            rows.append((label, eq - 1, mdd, fb))
        L.append(f"\n## 窗口 {w}\n\n| 记账口径 | 总收益 | 最大回撤 | ETF缺失回落天数 |\n|---|---|---|---|")
        for label, tot, mdd, fb in rows:
            L.append(f"| {label} | {tot*100:+.2f}% | {mdd*100:.2f}% | {fb} |")
        diff = rows[1][1] - rows[0][1]
        L.append(f"\n口径差（ETF−指数）：**{diff*100:+.2f}pp**")
    L.append("\n## 判读\n- 差异幅度即为回测用指数近似的系统性误差范围；若在±1-2pp内，指数近似可接受并记为已知偏差；更大则底仓回测应切换ETF净值。")
    out = os.path.join(C.BASE_DIR, "02_回测报告", "ETF净值对照-2026-07-10.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    B.log(f"已生成 {out}")
