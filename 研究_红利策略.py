# -*- coding: utf-8 -*-
"""红利策略研究执行器（预注册=../02_回测报告/红利策略研究-预注册-2026-07-20.md，先冻结后运行）。

连续面板2019-01~2026-06（含2024H1）；变体仅V0/V1/V2三个；口径见预注册§二。
"""
import sys, time
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
import backtest as B
import pipeline as P
import 时点数据 as PIT

SEMI = ["20190628","20191231","20200630","20201231","20210630","20211231",
        "20220630","20221230","20230630","20231229","20240628","20241231",
        "20250630","20251231","20260630"]
HIST = ["20170630","20171229","20180629","20181228"] + SEMI[:-1]   # 连续性核查用快照
ANNUAL = [d for d in SEMI if d[4:6] == "06"] + ["20260630"]

def build_pivots():
    parts_c, parts_a = [], []
    for s, e in (("20190101","20231231"), ("20240101","20240617"), ("20240618","20260630")):
        d = B.fetch_all(s, e)["panel"]
        parts_c.append(d.pivot(index="trade_date", columns="ts_code", values="close"))
        parts_a.append(d.pivot(index="trade_date", columns="ts_code", values="amount_yuan"))
    C = pd.concat(parts_c).sort_index()
    A = pd.concat(parts_a).sort_index()
    C = C[~C.index.duplicated()]; A = A[~A.index.duplicated()]
    return C, A

_DV = {}
def dv_snap(date):
    if date not in _DV:
        df = P._ts_query("daily_basic", trade_date=date, fields="ts_code,dv_ttm")
        df["dv_ttm"] = pd.to_numeric(df["dv_ttm"], errors="coerce")
        _DV[date] = df.set_index("ts_code")["dv_ttm"]
        time.sleep(0.6)
    return _DV[date]

def select(date, C, A, quality):
    dates = [d for d in C.index if d <= date]
    d0 = dates[-1]
    dv = dv_snap(d0 if d0 in C.index else date)
    amt20 = A.loc[:d0].tail(20).mean()
    liquid = set(amt20[amt20 >= 3e7].index)
    pool = dv[(dv > 0) & dv.index.isin(liquid)].dropna()
    pool = pool[[not PIT.st_at(ts, d0) for ts in pool.index]]
    if quality:
        pool = pool[pool <= 12.0]                     # 股息率上限12%
        # 分红连续性：近两个更早年度快照 dv>0
        y = int(date[:4])
        snaps = [s for s in HIST if s < date and s[4:6] == date[4:6]][-2:]
        if len(snaps) == 2:
            ok1, ok2 = dv_snap(snaps[0]), dv_snap(snaps[1])
            pool = pool[[ (ts in ok1.index and ok1[ts] > 0) and (ts in ok2.index and ok2[ts] > 0)
                          for ts in pool.index ]]
    top = pool.nlargest(50)
    return list(top.index), float(top.median()), d0

def leg_nav(C, members, d0, d1):
    cols = [m for m in members if m in C.columns]
    sub = C.loc[d0:d1, cols]
    base = sub.iloc[0]; ok = base.notna()
    return sub.loc[:, ok].div(base[ok]).mean(axis=1)

def run(C, A, legs, quality, label):
    navs, carries, overlaps = [1.0], [], []
    prev = None
    daily = []
    for i in range(len(legs) - 1):
        mem, carry, d0 = select(legs[i], C, A, quality)
        d1 = max(d for d in C.index if d <= legs[i+1])
        nv = leg_nav(C, mem, d0, d1)
        navs.append(navs[-1] * nv.iloc[-1])
        carries.append(carry)
        if prev: overlaps.append(len(set(mem) & set(prev)) / 50)
        prev = mem
        daily.append(nv / nv.iloc[0] * (daily[-1].iloc[-1] if daily else 1.0))
    nav_d = pd.concat(daily)
    mdd = (nav_d / nav_d.cummax() - 1).min()
    carry = float(np.median(carries))
    ov = float(np.mean(overlaps)) if overlaps else 0
    legs_per_yr = 2 if legs is SEMI else 1
    churn = legs_per_yr * (1 - ov)                    # 年换手比例（近似）
    tax = 0.10 * (carry/100) * min(churn, 1.0)        # 年税负拖累（近似，声明）
    yrs = 7.5
    gross = navs[-1] - 1
    net = (1 + gross) * ((1 - tax) ** yrs) - 1
    print(f"{label:<24} 全期 {gross*100:+7.1f}% | MDD {mdd*100:6.1f}% | 中位carry {carry:4.1f}% | "
          f"期均重合 {ov*100:3.0f}% | 年换手≈{churn*100:3.0f}% | 税后≈{net*100:+7.1f}%")
    return nav_d

if __name__ == "__main__":
    C, A = build_pivots()
    print(f"连续面板 {C.index[0]}~{C.index[-1]} {len(C)}日 × {C.shape[1]}股\n")
    print("== 变体（2019-06~2026-06，含2024H1）==")
    n0 = run(C, A, SEMI, False, "V0 基线Top50半年调")
    n1 = run(C, A, SEMI, True,  "V1 +质量过滤半年调")
    n2 = run(C, A, ANNUAL, True, "V2 质量过滤年度调")
    # 对照
    hs = None
    d = B.fetch_all("20190101","20231231")
    for k, v in d.items():
        if isinstance(v, dict) and "hs300" in v: hs = v["hs300"].sort_values("trade_date").set_index("trade_date")["close"]
    hs = hs[(hs.index >= "20190628") & (hs.index <= "20260630")]
    print(f"\n沪深300价格 {(hs.iloc[-1]/hs.iloc[0]-1)*100:+.1f}%（含分红约再+19pp）")
    rows = []
    for y0, y1 in (("20190101","20201231"),("20210101","20221231"),("20230101","20241231"),("20250101","20260719")):
        rows.append(P._ts_query("index_daily", ts_code="000922.CSI", start_date=y0, end_date=y1)); time.sleep(1.0)
    zi = pd.concat(rows).sort_values("trade_date").set_index("trade_date")["close"]
    zi = zi[(zi.index >= "20190628") & (zi.index <= "20260630")]
    zp = zi.iloc[-1]/zi.iloc[0] - 1
    zt = (1 + zp) * (1.055 - 0.005) ** 7.5 / 1 - 1   # +5.5%股息-0.5%费近似
    print(f"中证红利指数 价格{zp*100:+.1f}% | 全收益近似(+5.5%股息-费率) {zt*100:+.1f}%")
    # 关键段
    print("\n== 关键段（V1质量版） ==")
    for name, s, e in (("2024H1(上次缺口)", "20240102", "20240617"),
                       ("2024H2-925行情", "20240618", "20241231"),
                       ("2025", "20250101", "20251231"),
                       ("2026H1", "20260101", "20260630")):
        seg = n1.loc[s:e]
        if len(seg) > 1:
            dd = (seg/seg.cummax()-1).min()
            print(f"  {name}: {(seg.iloc[-1]/seg.iloc[0]-1)*100:+.1f}% | 段内回撤 {dd*100:.1f}%")
