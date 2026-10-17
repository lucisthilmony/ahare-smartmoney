# -*- coding: utf-8 -*-
"""回撤补仓梯 vs 估值梯 · 2005-2026全周期对照（用户2026-07-20提议"指数越回撤越补仓"）。

观察性研究，配置影子线素材，不触v1.3生产。冻结口径（跑前写定）：
- 数据：沪深300指数2005-2026（index_daily全史）+PE(TTM)2005-2026（index_dailybasic，缓存.pe300_full.csv）；
  指数层简化引擎（无广度/量能闸门——那些需全市场面板；T+1、5pp带、单笔≤10pp批间≥3日、单边2bp、
  权益分红+2.5%/年、现金1.8%/年），与昨晚连续回放同族口径；
- VAL（v1.3同构）：核心12% + PE扩窗分位（≥750交易日）地板 ≤30%分位→30%、≤15%→45%；解除=分位>阈值+15pp连续5日；
- DD（用户提议）：核心12% + 距250日滚动高点回撤 ≤-10%→30%、≤-20%→45%（权重与VAL对齐保可比）；
  解除=回撤修复至阈值+5pp连续5日（-10%档在dd>-5%解除、-20%档在dd>-15%解除）；
- UNION：地板=max(VAL, DD)；STATIC：事后匹配各梯实现均仓的固定仓位对照。
- 全期起点=2006-04（250日预热后）；VAL自PE史满750日起生效（约2008-05），此前仅核心仓——如实报告。
"""
import sys, os, time
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
import pipeline as P

CORE, COST = 0.12, 0.0002
PE_CSV = ".pe300_full.csv"

def load_data():
    if os.path.exists(PE_CSV):
        df = pd.read_csv(PE_CSV, dtype={"trade_date": str})
    else:
        rows = []
        for y in range(2005, 2027, 2):
            rows.append(P._ts_query("index_dailybasic", ts_code="000300.SH",
                                    start_date=f"{y}0101", end_date=f"{y+1}1231")); time.sleep(1.1)
        pe = pd.concat(rows)[["trade_date", "pe_ttm"]]
        rows = []
        for y in range(2005, 2027, 2):
            rows.append(P._ts_query("index_daily", ts_code="000300.SH",
                                    start_date=f"{y}0101", end_date=f"{y+1}1231")); time.sleep(1.1)
        px = pd.concat(rows)[["trade_date", "close"]]
        df = px.merge(pe, on="trade_date", how="left").sort_values("trade_date")
        df.to_csv(PE_CSV, index=False)
    df["pe_ttm"] = pd.to_numeric(df["pe_ttm"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values("trade_date").reset_index(drop=True)
    df["ret"] = df["close"].pct_change()
    df["roll_max"] = df["close"].rolling(250, min_periods=250).max()
    df["idx_dd"] = df["close"] / df["roll_max"] - 1
    return df

def run(df, use_val, use_dd, static=None, label=""):
    pe = df["pe_ttm"]
    etf, cash = CORE, 1.0 - CORE
    if static is not None: etf, cash = static, 1.0 - static
    val_fl = [False, False]; val_rel = [0, 0]     # (≤30%→30%), (≤15%→45%)
    dd_fl = [False, False]; dd_rel = [0, 0]       # (≤-10%→30%), (≤-20%→45%)
    VAL_R = [(0.30, 0.30, 0.45), (0.15, 0.45, 0.30)]
    DD_R = [(-0.10, 0.30, -0.05), (-0.20, 0.45, -0.15)]
    last_buy = -9
    trades, hist = 0, []
    pend = CORE if static is None else static
    start = 250                                    # 250日预热
    for i in range(start, len(df)):
        r = df.iloc[i]
        etf *= 1 + (r["ret"] if not np.isnan(r["ret"]) else 0) + 0.025/244
        cash *= 1 + 0.018/244
        nav = etf + cash; pos = etf / nav
        # T+1执行昨日目标
        if static is not None:
            tgt = static
        else:
            tgt = pend
        if pos <= tgt - 0.05 and i - last_buy >= 3:
            step = min(0.10, tgt - pos); d = step * nav
            etf += d - d*COST; cash -= d; trades += 1; last_buy = i
        elif pos >= tgt + 0.05:
            d = (tgt - pos) * nav
            etf += d - abs(d)*COST; cash -= d; trades += 1
        nav = etf + cash
        # 收盘信号→明日目标
        if static is None:
            floor = 0.0
            if use_val:
                hist_pe = pe.iloc[:i+1].dropna()
                pct = (hist_pe < r["pe_ttm"]).mean() if (len(hist_pe) >= 750 and not np.isnan(r["pe_ttm"])) else np.nan
                if not np.isnan(pct):
                    for k, (q, w, rq) in enumerate(VAL_R):
                        if not val_fl[k] and pct <= q: val_fl[k] = True; val_rel[k] = 0
                        elif val_fl[k]:
                            val_rel[k] = val_rel[k] + 1 if pct > rq else 0
                            if val_rel[k] >= 5: val_fl[k] = False
                floor = max([w for k, (q, w, rq) in enumerate(VAL_R) if val_fl[k]] + [floor])
            if use_dd and not np.isnan(r["idx_dd"]):
                for k, (q, w, rq) in enumerate(DD_R):
                    if not dd_fl[k] and r["idx_dd"] <= q: dd_fl[k] = True; dd_rel[k] = 0
                    elif dd_fl[k]:
                        dd_rel[k] = dd_rel[k] + 1 if r["idx_dd"] > rq else 0
                        if dd_rel[k] >= 5: dd_fl[k] = False
                floor = max([w for k, (q, w, rq) in enumerate(DD_R) if dd_fl[k]] + [floor])
            pend = max(CORE, floor)
        hist.append((r["trade_date"], nav, pos))
    h = pd.DataFrame(hist, columns=["d", "nav", "pos"]).set_index("d")
    mdd = (h.nav/h.nav.cummax() - 1).min()
    yrs = len(h)/244
    cagr = (h.nav.iloc[-1])**(1/yrs) - 1
    print(f"{label:<14} 全期 {(h.nav.iloc[-1]-1)*100:+7.1f}% (年化{cagr*100:+.1f}%) | MDD {mdd*100:6.1f}% | "
          f"均仓 {h.pos.mean()*100:3.0f}% | 调仓{trades:4d}次")
    return h

def episode(h, name, s, e):
    seg = h.loc[s:e]
    if len(seg) < 2: return f"  {name}: 无数据"
    dd = (seg.nav/seg.nav.cummax() - 1).min()
    return f"  {name}: 段收益 {(seg.nav.iloc[-1]/seg.nav.iloc[0]-1)*100:+.1f}% | 段内最深回撤 {dd*100:.1f}% | 段末仓位 {seg.pos.iloc[-1]*100:.0f}%"

if __name__ == "__main__":
    df = load_data()
    print(f"数据: {df['trade_date'].iloc[0]}~{df['trade_date'].iloc[-1]} 共{len(df)}日 "
          f"(账户起点约{df['trade_date'].iloc[250]})\n")
    print("== 全期对照 (2006-04起) ==")
    runs = {}
    runs["VAL(估值梯)"] = run(df, True, False, label="VAL(估值梯)")
    runs["DD(回撤梯)"] = run(df, False, True, label="DD(回撤梯)")
    runs["UNION(并集)"] = run(df, True, True, label="UNION(并集)")
    for lab, h in list(runs.items()):
        avg = round(h.pos.mean(), 2)
        run(df, False, False, static=avg, label=f"STATIC{int(avg*100)}%")
    print("\n== 关键熊市段行为 (策略净值口径) ==")
    for lab, h in runs.items():
        print(f"{lab}:")
        print(episode(h, "2008金融危机(0710-0811)", "20071016", "20081104"))
        print(episode(h, "2015杠杆崩(1506-1602)", "20150608", "20160129"))
        print(episode(h, "2018贸易战(1801-1901)", "20180124", "20190103"))
        print(episode(h, "2021-24长熊(2102-2402)", "20210218", "20240202"))
