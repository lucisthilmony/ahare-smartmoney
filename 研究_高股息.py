# -*- coding: utf-8 -*-
"""高股息组合描述性研究 · 2026-07-19。

口径（写死）：每半年末（6/12月最后交易日）按 daily_basic.dv_ttm（TTM股息率）选Top50等权；
过滤=时点非ST、20日均成交额≥3000万元、dv_ttm>0；持有至下一形成日；qfq收盘计收益（近似含分红再投）。
对照：零分红组（dv_ttm空或0，等权）、全市场等权、沪深300（价格指数，注：漏其分红约2.5pp/年）、
中证红利指数000922.CSI（价格口径，漏其自身5-6pp/年分红，仅作方向交叉验证）。
时代A形成日 2019-06~2023-06（末腿至2023-12），时代B 2024-06~2025-12（末腿至2026-06）；
2023-12/2024H1腿因缓存缺口不覆盖（与结果无关的预先排除）。描述性研究：不设通过判线，只出成绩单。
"""
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
import backtest as B
import pipeline as P
import 时点数据 as PIT

LEGS_A = ["20190628", "20191231", "20200630", "20201231", "20210630",
          "20211231", "20220630", "20221230", "20230630", "20231229"]
LEGS_B = ["20240628", "20241231", "20250630", "20251231", "20260630"]

def get_pivots(tag):
    s, e = ("20240618", "20260630") if tag == "B" else ("20190101", "20231231")
    d = B.fetch_all(s, e)
    C = d["panel"].pivot(index="trade_date", columns="ts_code", values="close")
    A = d["panel"].pivot(index="trade_date", columns="ts_code", values="amount_yuan")
    hs = None
    for k, v in d.items():
        if isinstance(v, dict) and "hs300" in v:
            hs = v["hs300"].sort_values("trade_date").set_index("trade_date")["close"]
    return C, A, hs

def csi_div(s, e):
    df = P._ts_query("index_daily", ts_code="000922.CSI", start_date=s, end_date=e)
    return df.sort_values("trade_date").set_index("trade_date")["close"]

def leg_nav(C, members, d0, d1):
    """成员等权日度净值（d0收盘=1）。"""
    sub = C.loc[d0:d1, [m for m in members if m in C.columns]]
    base = sub.iloc[0]
    ok = base.notna()
    rel = sub.loc[:, ok].div(base[ok])
    return rel.mean(axis=1)

def run_era(tag, legs):
    C, A, hs = get_pivots(tag)
    dates = list(C.index)
    csi = csi_div(legs[0], legs[-1])
    navs = {k: [1.0] for k in ("高股息Top50", "零分红组", "全市场EW", "沪深300", "中证红利")}
    daily = {k: [] for k in ("高股息Top50", "全市场EW")}
    rows = []
    for i in range(len(legs) - 1):
        d0 = max(d for d in dates if d <= legs[i])
        d1 = max(d for d in dates if d <= legs[i + 1])
        db = P._ts_query("daily_basic", trade_date=d0, fields="ts_code,dv_ttm")
        db["dv_ttm"] = pd.to_numeric(db["dv_ttm"], errors="coerce")
        amt20 = A.loc[:d0].tail(20).mean()
        liquid = set(amt20[amt20 >= 3e7].index)
        ok_st = {ts for ts in db.ts_code if ts in liquid and not PIT.st_at(ts, d0)}
        pos = db[(db.ts_code.isin(ok_st)) & (db.dv_ttm > 0)].nlargest(50, "dv_ttm")
        zero = db[(db.ts_code.isin(ok_st)) & (db.dv_ttm.isna() | (db.dv_ttm <= 0))]["ts_code"]
        top_nav = leg_nav(C, pos.ts_code, d0, d1)
        zero_nav = leg_nav(C, zero, d0, d1)
        mkt_nav = leg_nav(C, list(ok_st), d0, d1)
        r = dict(leg=f"{d0}~{d1}", 门槛股息率=pos.dv_ttm.min(),
                 高股息Top50=top_nav.iloc[-1] - 1, 零分红组=zero_nav.iloc[-1] - 1,
                 全市场EW=mkt_nav.iloc[-1] - 1, 沪深300=hs[d1] / hs[d0] - 1,
                 中证红利=csi[d1] / csi[d0] - 1 if d0 in csi.index and d1 in csi.index else np.nan)
        rows.append(r)
        for k, nv in (("高股息Top50", top_nav), ("全市场EW", mkt_nav)):
            daily[k].append(nv / nv.iloc[0] * (daily[k][-1].iloc[-1] if daily[k] else 1.0))
        for k in navs:
            navs[k].append(navs[k][-1] * (1 + r[k]) if not np.isnan(r[k]) else navs[k][-1])
    df = pd.DataFrame(rows).set_index("leg")
    print(f"\n=== 时代{tag} 分腿收益（%）===")
    print((df.drop(columns=["门槛股息率"]) * 100).round(1).to_string())
    print("Top50入选门槛股息率(各腿min):", (df.门槛股息率.round(1)).tolist())
    print(f"\n时代{tag} 累计: " + " | ".join(f"{k} {(navs[k][-1]-1)*100:+.1f}%" for k in navs))
    for k, chain in daily.items():
        nv = pd.concat(chain)
        print(f"{k} 最大回撤 {((nv/nv.cummax()-1).min())*100:.1f}%", end="  ")
    print()
    return df

if __name__ == "__main__":
    a = run_era("A", LEGS_A)
    b = run_era("B", LEGS_B)
    pd.concat([a, b]).round(4).to_csv("高股息研究_分腿.csv", encoding="utf-8-sig")
