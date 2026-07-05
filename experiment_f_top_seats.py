# -*- coding: utf-8 -*-
"""
实验F：顶级席位跟随 · 策略化检验（2026-07-03 预注册）

来源：席位性格研究（观察层）——席位exc1排名跨时代相关0.49、窗口内split-half 0.50/0.29。
检验"跟随历史最优席位的买入"在可执行+全成本下是否有正期望。

预注册规则（跑前写定，不扫参）：
  席位评级（walk-forward，仅用T日之前的数据）：
    T日回看250个交易日内该席位的买方上榜事件（净买入>0），事件数≥30 才有资格；
    以事件的exc1（相对同日同板等权的次日超额）均值排名，取前10%为"顶级席位"。
  信号：T日顶级席位以净买入>0上榜股票X（同股同日多席位去重）。
  可执行过滤：T+1开盘未涨停（开盘涨幅<板块阈-0.3%）；T+1真实价(close_raw)在4-80元。
  入场/出场：T+1开盘买入，T+2开盘卖出（T+1制度下最早合法退出）。
  成本：滑点每边 主板0.1%/20cm 0.2% + 佣金万2.5×2 + 印花税0.05%。
  判据：**两窗口平均净收益同时>0**；任一窗口≤0 → 否决归档。

用法：./.venv/bin/python experiment_f_top_seats.py
输出：02_回测报告/experiment_f_top_seats.md
"""
import os, sys, pickle, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import backtest as B

WINDOWS = [("20240618", "20260630", "2024-2026样本内"), ("20190101", "20231231", "2019-2023样本外")]
LOOKBACK = 250
MIN_EV = 30
TOP_PCT = 0.10
SLIP = {"main": 0.001, "chinext": 0.002, "star": 0.002}
COMM, STAMP = 0.00025, 0.0005

def run_window(start, end):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, f".toplist_cache_{start}_{end}.pkl"), "rb") as f:
        lhb = pickle.load(f)
    ti = lhb["top_inst"]
    ti = ti[(ti["side"].astype(str) == "0") & (ti["net_buy"] > 0)].copy()
    data = B.fetch_all(start, end)
    basic = data["basic"]
    board_map = dict(zip(basic["ts_code"], basic["board"]))
    panel = data["panel"].sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    price_col = "close_raw" if "close_raw" in panel.columns else "close"
    g = panel.groupby("ts_code", sort=False)
    panel["fwd1"] = g["close"].shift(-1) / panel["close"] - 1
    panel["open1"] = g["open"].shift(-1)          # T+1 开盘
    panel["open2"] = g["open"].shift(-2)          # T+2 开盘
    panel["oret1"] = panel["open1"] / panel["close"] - 1
    panel["raw1"] = g[price_col].shift(-1)
    panel["board"] = panel["ts_code"].map(board_map)
    panel = panel[panel["board"].notna()]
    bl = panel.groupby(["trade_date", "board"])["fwd1"].mean().rename("bl1").reset_index()
    panel = panel.merge(bl, on=["trade_date", "board"], how="left")
    panel["exc1"] = panel["fwd1"] - panel["bl1"]
    cols = ["ts_code", "trade_date", "board", "exc1", "oret1", "open1", "open2", "raw1"]
    ev = ti.merge(panel[cols], on=["ts_code", "trade_date"], how="inner")
    ev = ev.sort_values("trade_date").reset_index(drop=True)

    # walk-forward 席位评级：逐席位事件序列，滚动250日窗口均值（仅用T之前的事件，exc1在T+1可知）
    all_dates = sorted(panel["trade_date"].unique())
    dpos = {d: i for i, d in enumerate(all_dates)}
    ev["dpos"] = ev["trade_date"].map(dpos)
    seat_hist = {}   # exalter -> (dpos_arr, exc1_arr) 按序
    for s, gse in ev.groupby("exalter"):
        gse = gse.dropna(subset=["exc1"])
        seat_hist[s] = (gse["dpos"].values, gse["exc1"].values)

    # 每日：对当日出现的席位算 trailing 均值 → 当日合格席位分布 → 前10%分位线
    win_dates = [d for d in data["win_dates"] if d in dpos]
    ev_win = ev[ev["trade_date"].isin(set(win_dates))]
    trades = []
    for d, gd in ev_win.groupby("trade_date"):
        p = dpos[d]
        lo = p - LOOKBACK
        scores = {}
        for s in gd["exalter"].unique():
            hp, hx = seat_hist.get(s, (None, None))
            if hp is None:
                continue
            m = (hp >= lo) & (hp < p)     # 严格T之前（exc1需T+1收盘才可知，p-1事件的exc1在p日盘前已知：exc1(p-1)用到p日收盘→不可知！再收紧：hp < p-1）
            m = (hp >= lo) & (hp < p - 1)
            if m.sum() >= MIN_EV:
                scores[s] = hx[m].mean()
        if len(scores) < 10:
            continue
        cut = np.quantile(list(scores.values()), 1 - TOP_PCT)
        top_seats = {s for s, v in scores.items() if v >= cut}
        sig = gd[gd["exalter"].isin(top_seats)]
        for (ts_, _), r in sig.groupby(["ts_code", "trade_date"]):
            r0 = r.iloc[0]
            thr = P.limit_up_thr(r0["board"], d)
            if not (r0["oret1"] == r0["oret1"]) or r0["oret1"] >= thr - 0.003:
                continue
            if not (r0["raw1"] == r0["raw1"]) or not (C.PRICE_MIN <= r0["raw1"] <= C.PRICE_MAX):
                continue
            if not (r0["open2"] == r0["open2"]) or not r0["open1"]:
                continue
            gross = r0["open2"] / r0["open1"] - 1
            cost = 2 * SLIP[r0["board"]] + 2 * COMM + STAMP
            trades.append(dict(ts=ts_, date=d, board=r0["board"], gross=gross, net=gross - cost))
    return pd.DataFrame(trades)

if __name__ == "__main__":
    L = ["# 实验F：顶级席位跟随 · 策略化检验（2026-07-03）\n",
         "> 预注册见 experiment_f_top_seats.py 头注释：250日滚动席位评级（≥30事件，前10%），",
         "> 严格walk-forward（评级仅用T-1日之前已可知的exc1）；T+1开盘入场（未涨停+4-80元），T+2开盘卖出，全成本。",
         "> 判据：两窗口平均净收益同时>0。\n"]
    verdicts = []
    for start, end, wname in WINDOWS:
        tr = run_window(start, end)
        n = len(tr)
        L.append(f"\n## 窗口 {wname}\n")
        if not n:
            L.append("无可执行样本。\n"); verdicts.append(False); continue
        mean, med, win = tr["net"].mean(), tr["net"].median(), (tr["net"] > 0).mean()
        L.append(f"- 信号 **{n}** 笔 ｜ 平均净收益 **{mean*100:+.3f}%** ｜ 中位 {med*100:+.3f}% ｜ 胜率 {win*100:.0f}%")
        tr["yr"] = tr["date"].str[:4]
        L.append("\n| 年 | 笔数 | 平均净收益 | 胜率 |\n|---|---|---|---|")
        for y, gy in tr.groupby("yr"):
            L.append(f"| {y} | {len(gy)} | {gy['net'].mean()*100:+.3f}% | {(gy['net']>0).mean()*100:.0f}% |")
        verdicts.append(mean > 0)
        tag = "in" if "样本内" in wname else "oos"
        tr.to_csv(os.path.join(C.BASE_DIR, "02_回测报告", f"experiment_f_trades_{tag}.csv"),
                  index=False, encoding="utf-8-sig")
    ok = all(verdicts)
    L.append(f"\n## 判定\n\n**{'✅ 通过：获得候选资格（下一步：仓位化+与卫星层的关系设计，另行预注册+前向）' if ok else '❌ 否决：未两窗口同正，归档'}**\n")
    L.append("\n## 诚实限制\n- 开盘价成交近似（未建模集合竞价排队）；隔夜持仓一晚的跳空风险由样本分布如实反映。")
    L.append("- 评级期250日在窗口初期不足，前一年信号自然稀疏（walk-forward的代价，非bug）。")
    L.append("- 席位改名会重置历史。信号源自同库观察研究，真正独立检验是前向。")
    out = os.path.join(C.BASE_DIR, "02_回测报告", "experiment_f_top_seats.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    B.log(f"已生成 {out}")
