# -*- coding: utf-8 -*-
"""
实验E：E10"扛住"多头信号 · 策略化检验（2026-07-02 预注册）

来源：监管异动事件研究（观察层）发现 E10 扛住组持有5日两窗口均值为正（+2.6%/+4.1%）。
本实验加上**可执行过滤与全成本**，按双窗口判据检验它是否仍然成立。

预注册规则（跑前写定，不扫参）：
  事件：E10 = qfq收盘较10个交易日前≥+100%首穿越，同股20交易日去重；排除北交所/ST/次新（与事件研究一致）。
  扛住：T+1 收盘涨幅 > 0。
  可执行过滤：① T+1 收盘未封涨停（收盘涨幅 < 当日板块涨停阈−0.3%，封死买不进）；
             ② T+1 真实价(close_raw)在 4–80 元池内（手册§1）；③ T+1 后至少还有5根K线（不足则弃样）。
  入场：T+1 收盘。出场：固定持有5个交易日后收盘卖出，无止损（保持信号纯度）。
  成本：滑点每边 主板0.1%/20cm 0.2% + 佣金万2.5×2 + 印花税卖出0.05%（主板往返≈0.30%，20cm≈0.50%）。
  判据：**两窗口平均净收益同时>0** → 才有资格作为"候选小模块"进入下一步（仓位化+前向）；任一窗口≤0 → 否决归档。

用法：./.venv/bin/python experiment_e10_survivor.py
输出：02_回测报告/experiment_e10_survivor.md
"""
import os, sys, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import backtest as B

WINDOWS = [("20240618", "20260630", "2024-2026样本内"), ("20190101", "20231231", "2019-2023样本外")]
HOLD = 5
DEDUP = 20
SLIP = {"main": 0.001, "chinext": 0.002, "star": 0.002}
COMM, STAMP = 0.00025, 0.0005

def run_window(start, end):
    data = B.fetch_all(start, end)
    basic = data["basic"]
    st_set = set(basic.loc[basic["name"].apply(P.is_st), "ts_code"])
    board_map = dict(zip(basic["ts_code"], basic["board"]))
    name_map = dict(zip(basic["ts_code"], basic["name"]))
    list_map = dict(zip(basic["ts_code"], basic["list_date"].fillna("19900101")))
    win = set(data["win_dates"])
    panel = data["panel"].sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    price_col = "close_raw" if "close_raw" in panel.columns else "close"
    trades, skipped_locked = [], 0
    for code, sub in panel.groupby("ts_code", sort=False):
        board = board_map.get(code)
        if board is None or code in st_set:
            continue
        c = sub["close"].values; craw = sub[price_col].values; dates = sub["trade_date"].values
        n = len(c)
        if n < 35:
            continue
        ld = str(list_map.get(code, "19900101"))[:8]
        try:
            ld_dt = dt.datetime.strptime(ld, "%Y%m%d").date()
        except ValueError:
            ld_dt = dt.date(1990, 1, 1)
        r10 = np.full(n, np.nan)
        r10[10:] = c[10:] / c[:-10] - 1
        last_ev = -10**9
        for i in range(1, n):
            if not (r10[i] == r10[i]) or r10[i] < 1.0 or (r10[i-1] == r10[i-1] and r10[i-1] >= 1.0):
                continue
            if i - last_ev < DEDUP:
                continue
            d = dates[i]
            if d not in win:
                continue
            d_dt = dt.datetime.strptime(d, "%Y%m%d").date()
            if (d_dt - ld_dt).days < int(C.MIN_LIST_DAYS * 1.6):
                continue
            last_ev = i
            if i + 1 >= n:
                continue
            ret1 = c[i+1] / c[i] - 1
            if ret1 <= 0:
                continue                      # 没扛住 → 无信号
            thr = P.limit_up_thr(board, dates[i+1])
            if ret1 >= thr - 0.003:
                skipped_locked += 1
                continue                      # T+1 封死，买不进
            if not (C.PRICE_MIN <= craw[i+1] <= C.PRICE_MAX):
                continue
            if i + 1 + HOLD >= n:
                continue                      # 出场K线不足，弃样
            gross = c[i+1+HOLD] / c[i+1] - 1
            cost = 2 * SLIP[board] + 2 * COMM + STAMP
            trades.append(dict(ts=code, name=name_map.get(code, ""), board=board,
                               date=dates[i+1], gross=gross, net=gross - cost))
    return pd.DataFrame(trades), skipped_locked

if __name__ == "__main__":
    L = ["# 实验E：E10\"扛住\"多头信号 · 策略化检验（2026-07-02）\n",
         "> 预注册规则见 experiment_e10_survivor.py 头注释：扛住确认+T+1未封板可执行过滤+4-80元池+全成本，",
         "> T+1收盘入场、固定持有5日、无止损。判据：两窗口平均净收益同时>0。\n"]
    verdicts = []
    for start, end, wname in WINDOWS:
        tr, locked = run_window(start, end)
        n = len(tr)
        L.append(f"\n## 窗口 {wname}（{start}~{end}）\n")
        if not n:
            L.append("无可执行样本。\n"); verdicts.append(False); continue
        mean, med = tr["net"].mean(), tr["net"].median()
        L.append(f"- 可执行样本 **{n}** 笔（另有 {locked} 起因T+1封死跳过）")
        L.append(f"- 平均净收益 **{mean*100:+.2f}%** ｜ 中位数 {med*100:+.2f}% ｜ 胜率 {(tr['net']>0).mean()*100:.0f}% "
                 f"｜ 最差 {tr['net'].min()*100:+.1f}% ｜ 最好 {tr['net'].max()*100:+.1f}%")
        tr["yr"] = tr["date"].str[:4]
        L.append("\n| 年 | 笔数 | 平均净收益 | 胜率 |\n|---|---|---|---|")
        for y, g in tr.groupby("yr"):
            L.append(f"| {y} | {len(g)} | {g['net'].mean()*100:+.2f}% | {(g['net']>0).mean()*100:.0f}% |")
        L.append(f"\n| 板 | 笔数 | 平均净收益 |\n|---|---|---|")
        for b, g in tr.groupby("board"):
            L.append(f"| {b} | {len(g)} | {g['net'].mean()*100:+.2f}% |")
        verdicts.append(mean > 0)
        tag = "in" if "样本内" in wname else "oos"
        tr.to_csv(os.path.join(C.BASE_DIR, "02_回测报告", f"experiment_e10_trades_{tag}.csv"),
                  index=False, encoding="utf-8-sig")
    ok = all(verdicts)
    L.append(f"\n## 判定\n\n**{'✅ 通过：两窗口平均净收益均>0，获得候选资格（下一步：仓位化设计+前向记账，另行预注册）' if ok else '❌ 否决：未能两窗口同时为正，归档'}**\n")
    L.append("\n## 诚实限制\n- 收盘对收盘近似；未建模盘中路径与真实滑点；T+1接近涨停但未封死的样本按可成交处理，实际或部分排队失败。")
    L.append("- 事件频率低（每周约1起），单笔波动大——即便通过也只配小仓位模块，且需前向验证。")
    L.append("- 信号源自同一批数据的观察性研究（事件研究），本检验只是加了执行/成本约束，**并非独立数据的确认**；真正的独立检验是前向。")
    out = os.path.join(C.BASE_DIR, "02_回测报告", "experiment_e10_survivor.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    B.log(f"已生成 {out}")
