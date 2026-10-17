# -*- coding: utf-8 -*-
"""
龙虎榜席位性格研究 · 分析（协议见 02_回测报告/席位性格研究-协议预注册-2026-07-02.md）
观察性研究：Q1 席位次日超额的持续性（split-half + 跨窗口）；Q2 合力榜家数单调性；Q3 机构 vs 游资席位。
观察层=事件日T收盘起的超额（相对同日同板等权）；可执行层=T+1开盘未涨停时按T+1开盘入场的原始收益。
用法：./.venv/bin/python 席位性格研究.py
输出：02_回测报告/席位性格研究-结果-2026-07-03.md
"""
import os, sys, pickle, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import backtest as B

WINDOWS = [("20240618", "20260630", "2024-2026样本内"), ("20190101", "20231231", "2019-2023样本外")]
KS = (1, 3, 5)
MIN_EVENTS = 30      # 高频席位门槛（窗口内买方上榜次数）
MIN_HALF = 15        # split-half 每半最少事件数

def load_events(start, end):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, f".toplist_cache_{start}_{end}.pkl"), "rb") as f:
        lhb = pickle.load(f)
    ti = lhb["top_inst"]
    ti = ti[(ti["side"].astype(str) == "0") & (ti["net_buy"] > 0)].copy()   # 买方席位、净买入>0
    data = B.fetch_all(start, end)
    basic = data["basic"]
    board_map = dict(zip(basic["ts_code"], basic["board"]))
    panel = data["panel"].sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    g = panel.groupby("ts_code", sort=False)
    for k in KS:
        panel[f"fwd{k}"] = g["close"].shift(-k) / panel["close"] - 1
    panel["open_next"] = g["open"].shift(-1)
    panel["oret_next"] = panel["open_next"] / panel["close"] - 1
    for k in KS:
        panel[f"exe{k}"] = g["close"].shift(-k) / panel["open_next"] - 1
    panel["board"] = panel["ts_code"].map(board_map)
    panel = panel[panel["board"].notna()]
    # 同日同板等权基准
    bl = panel.groupby(["trade_date", "board"])[[f"fwd{k}" for k in KS]].mean().rename(
        columns={f"fwd{k}": f"bl{k}" for k in KS}).reset_index()
    panel = panel.merge(bl, on=["trade_date", "board"], how="left")
    for k in KS:
        panel[f"exc{k}"] = panel[f"fwd{k}"] - panel[f"bl{k}"]
    cols = ["ts_code", "trade_date", "board", "close", "oret_next"] + \
           [f"exc{k}" for k in KS] + [f"exe{k}" for k in KS]
    ev = ti.merge(panel[cols], on=["ts_code", "trade_date"], how="inner")
    ev = ev[ev["trade_date"].isin(set(data["win_dates"]))]
    # 可执行标记：T+1开盘未达涨停（阈按T日规则近似）
    thr = ev.apply(lambda r: P.limit_up_thr(r["board"], r["trade_date"]), axis=1)
    ev["executable"] = ev["oret_next"] < thr - 0.003
    return ev

def q1(ev, wname, L):
    cnt = ev.groupby("exalter").size()
    hot = cnt[cnt >= MIN_EVENTS].index
    L.append(f"\n### Q1 席位次日超额的持续性（{wname}）\n")
    L.append(f"- 买方事件 {len(ev)} 起 ｜ 席位 {ev['exalter'].nunique()} 个 ｜ ≥{MIN_EVENTS}次的高频席位 **{len(hot)}** 个")
    e = ev[ev["exalter"].isin(hot)].copy()
    med = e["trade_date"].sort_values().iloc[len(e)//2]
    h1, h2 = e[e["trade_date"] <= med], e[e["trade_date"] > med]
    m1 = h1.groupby("exalter")["exc1"].agg(["mean", "size"])
    m2 = h2.groupby("exalter")["exc1"].agg(["mean", "size"])
    both = m1[m1["size"] >= MIN_HALF].join(m2[m2["size"] >= MIN_HALF], lsuffix="_1", rsuffix="_2", how="inner")
    if len(both) >= 10:
        rho = both["mean_1"].rank().corr(both["mean_2"].rank())
        L.append(f"- **split-half稳定性**：前后半段均≥{MIN_HALF}次的席位 {len(both)} 个，"
                 f"平均exc1排名 Spearman ρ = **{rho:.3f}**（n={len(both)}）")
    else:
        rho = np.nan
        L.append(f"- split-half：合格席位不足10个，无法判定")
    top = e.groupby("exalter")["exc1"].agg(["mean", "size"]).sort_values("mean", ascending=False)
    L.append(f"- 高频席位 exc1 分布：中位 {top['mean'].median()*100:+.2f}%，"
             f"P90 {top['mean'].quantile(.9)*100:+.2f}%，P10 {top['mean'].quantile(.1)*100:+.2f}%")
    ex = e[e["executable"]]
    L.append(f"- 可执行层（T+1开盘未涨停，占 {e['executable'].mean()*100:.0f}%）：exe1 均值 {ex['exe1'].mean()*100:+.2f}%，"
             f"exe5 均值 {ex['exe5'].mean()*100:+.2f}%（原始收益，未扣成本）")
    return rho, top

def q2(ev, hot_seats, wname, L):
    L.append(f"\n### Q2 合力榜效应（{wname}）\n")
    e = ev.copy()
    e["is_hot"] = e["exalter"].isin(hot_seats)
    grp = e.groupby(["ts_code", "trade_date"]).agg(hot_n=("is_hot", "sum"), exc1=("exc1", "first"),
                                                   exc5=("exc5", "first"), exe5=("exe5", "first"),
                                                   executable=("executable", "first")).reset_index()
    grp["bucket"] = pd.cut(grp["hot_n"], bins=[-1, 0, 1, 2, 999], labels=["0个", "1个", "2个", "3个+"])
    L.append("| 高频席位家数 | n | exc1均值 | exc5均值 | 可执行exe5均值 |\n|---|---|---|---|---|")
    for b, g in grp.groupby("bucket", observed=True):
        ge = g[g["executable"] == True]
        L.append(f"| {b} | {len(g)} | {g['exc1'].mean()*100:+.2f}% | {g['exc5'].mean()*100:+.2f}% | "
                 f"{(ge['exe5'].mean()*100 if len(ge) else float('nan')):+.2f}% |")

def q3(ev, wname, L):
    L.append(f"\n### Q3 机构专用 vs 营业部席位（{wname}）\n")
    e = ev.copy()
    e["inst"] = e["exalter"].astype(str).str.contains("机构专用")
    L.append("| 买方类型 | n | exc1均值 | exc5均值 | 可执行exe5均值 |\n|---|---|---|---|---|")
    for nm, g in [("机构专用", e[e["inst"]]), ("营业部(游资/散户)", e[~e["inst"]])]:
        ge = g[g["executable"] == True]
        L.append(f"| {nm} | {len(g)} | {g['exc1'].mean()*100:+.2f}% | {g['exc5'].mean()*100:+.2f}% | "
                 f"{(ge['exe5'].mean()*100 if len(ge) else float('nan')):+.2f}% |")

if __name__ == "__main__":
    L = ["# 龙虎榜席位性格研究 · 结果（2026-07-03，观察性）\n",
         "> 协议：席位性格研究-协议预注册-2026-07-02.md。exc=相对同日同板等权的超额（观察层，自T收盘）；",
         "> exe=T+1开盘未涨停时自T+1开盘的原始收益（可执行层）。均未扣交易成本。\n"]
    tops = {}
    for start, end, wname in WINDOWS:
        ev = load_events(start, end)
        L.append(f"\n## 窗口 {wname}\n")
        rho, top = q1(ev, wname, L)
        cnt = ev.groupby("exalter").size()
        q2(ev, set(cnt[cnt >= MIN_EVENTS].index), wname, L)
        q3(ev, wname, L)
        tops[wname] = top
    a, b = tops[WINDOWS[0][2]], tops[WINDOWS[1][2]]
    common = a.join(b, lsuffix="_in", rsuffix="_oos", how="inner")
    L.append(f"\n## 跨窗口稳定性（两窗口均≥{MIN_EVENTS}次的席位：{len(common)} 个）\n")
    if len(common) >= 10:
        rho = common["mean_in"].rank().corr(common["mean_oos"].rank())
        L.append(f"跨时代 exc1 排名 Spearman ρ = **{rho:.3f}**（n={len(common)}）")
    else:
        L.append("合格席位不足10个，无法判定（席位改名/消亡导致跨窗口交集小，如实报告）。")
    L.append("\n## 诚实限制\n- 未扣成本；exe层按T+1开盘可成交近似（竞价排队失败未建模）。")
    L.append("- 席位以营业部名称为键，改名/迁址会打断历史。reason细类未区分。观察性研究，策略化需另行预注册。")
    out = os.path.join(C.BASE_DIR, "02_回测报告", "席位性格研究-结果-2026-07-03.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    B.log(f"已生成 {out}")
