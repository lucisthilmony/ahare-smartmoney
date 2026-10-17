# -*- coding: utf-8 -*-
"""
实验A · 止损执行方式对比：收盘确认→次日开盘卖（现状） vs 盘中触价条件单（手册§7允许的变体）
同一批候选、同一入场、同一盈利端出场，只换止损成交方式。
预注册判定标准：**两个窗口（2019–2023 样本外 与 2024–2026 样本内）同向改善才采纳**。
用法：./.venv/bin/python experiment_stop_mode.py     （需先跑过 backtest.py 生成两个窗口的缓存）
产出：02_回测报告/experiment_stop_mode.md
"""
import os, sys, time, datetime as dt
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import backtest as B

WINDOWS = [("20190101", "20231231", "2019-2023 样本外"),
           ("20240618", "20260630", "2024-2026 样本内")]
VARIANTS = [("8日/MA5",  dict(hold_max=8,  trail="ma5")),
            ("15日/MA10", dict(hold_max=15, trail="ma10"))]

def run_window(start, end):
    data = B.fetch_all(start, end)
    P_ = B.prepare(data)
    frames = P_["frames"]
    rows = []
    for d, state, cands in B.daily_candidates(data, P_):
        for cd in cands:
            sub = frames[cd["ts"]]; p = cd["p"]; board = cd["board"]
            gap = C.BOARDS[board]["gap"]
            rec = dict(date=d, sec_rank=cd["sec_rank"])
            ok = True
            for vname, kw in VARIANTS:
                s1 = B.simulate(sub, p, board, gap, stop_mode="next_open", **kw)
                if s1 is None:
                    ok = False; break
                s2 = B.simulate(sub, p, board, gap, stop_mode="intraday", **kw)
                rec[f"R|{vname}|收盘确认"] = s1["R"]
                rec[f"R|{vname}|盘中触价"] = (s2 or {}).get("R")
            if ok:
                rows.append(rec)
    return pd.DataFrame(rows)

def stat(s):
    s = s.dropna()
    if not len(s): return "-", "-", "-"
    return f"{len(s)}", f"{(s>0).mean()*100:.1f}%", f"{s.mean():.3f}"

if __name__ == "__main__":
    t0 = time.time()
    L = ["# 实验A · 止损执行方式对比（收盘确认 vs 盘中触价条件单）\n",
         f"- 生成：{dt.datetime.now():%Y-%m-%d %H:%M}",
         "- 同一批候选、同一入场与盈利端出场，只换止损成交方式。触价成交价 = min(当日开盘, 止损价)；同日与2R冲突保守地先算止损。",
         "- **预注册判定标准：两个窗口同向改善才采纳。**\n"]
    for start, end, wname in WINDOWS:
        B.log(f"窗口 {wname} …")
        df = run_window(start, end)
        L.append(f"\n## {wname}\n")
        L.append("| 出场结构 · 止损方式 | 笔数 | 胜率 | 平均R | Top5主线平均R |")
        L.append("|---|---|---|---|---|")
        top5 = df["sec_rank"] <= 5
        for vname, _ in VARIANTS:
            for mode in ("收盘确认", "盘中触价"):
                col = f"R|{vname}|{mode}"
                n, w, r = stat(df[col])
                _, _, r5 = stat(df.loc[top5, col])
                L.append(f"| {vname} · {mode} | {n} | {w} | **{r}** | {r5} |")
    out = os.path.join(B.BASE, "experiment_stop_mode.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    B.log(f"完成：{out}（用时 {time.time()-t0:.0f}s）")
