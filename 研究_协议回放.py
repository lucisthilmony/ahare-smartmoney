# -*- coding: utf-8 -*-
"""个人再入场协议 v1.1 一体化回放（2019-2023 / 2024-06~2026-06，可执行性检查）。

规格=01_策略文档/个人再入场协议-预注册-2026-07-19.md（v1.1）。回放近似口径（如实声明）：
- 状态分为生产口径的近似重实现：s1=沪深300>MA20、s2=>MA60、s3=两市额≥20日均、s4=阳线家数>阴线家数；
  否决近似=当日阴线占比≥80%（生产另有涨停大面等细则，回放不含）；
- 资产=沪深300价格指数+2.5%/年分红连续计入（近似510300全收益）；现金=1.8%/年；
- 执行=T日收盘确认目标、T+1收盘成交（新仓位自T+1收盘起计收益）；
- 加仓单笔≤10pp、批间≥3个交易日；卖出不受限（降险优先）；熔断动作同样T+1生效；
- PE分位=扩窗（起点2019-01，≥500交易日方生效）；
- 两变体：BASE=v1.1原文（再平衡带0.5pp）；AMEND=v1.2候选（5pp再平衡带+非强制交易方向反转10日锁）；
- 时代B独立重启；2024H1缓存缺口不覆盖，两时代独立报告。
"""
import sys, os, time
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
import backtest as B
import pipeline as P

CORE, CAP = 0.12, 0.50
A_TGT = {0: CORE, 2: 0.20, 3: 0.35, 4: 0.50}
B_RUNGS = [(0.50, 0.15, 0.65), (0.30, 0.30, 0.45), (0.15, 0.45, 0.30)]  # (买入分位, 地板, 解除分位)
PE_CSV = ".pe300_daily.csv"

def load_pe():
    if os.path.exists(PE_CSV):
        return pd.read_csv(PE_CSV, dtype={"trade_date": str}).set_index("trade_date")["pe_ttm"]
    rows = []
    for y0, y1 in (("20190101","20201231"),("20210101","20221231"),("20230101","20241231"),("20250101","20991231")):
        rows.append(P._ts_query("index_dailybasic", ts_code="000300.SH", start_date=y0, end_date=y1)); time.sleep(1.2)
    df = pd.concat(rows)
    df["pe_ttm"] = pd.to_numeric(df["pe_ttm"], errors="coerce")
    ser = df.dropna(subset=["pe_ttm"]).sort_values("trade_date").set_index("trade_date")["pe_ttm"]
    ser.to_frame().to_csv(PE_CSV)
    return ser

_ERA = {}
def era_frame(tag):
    if tag in _ERA: return _ERA[tag]
    s, e = ("20240618", "20260630") if tag == "B" else ("20190101", "20231231")
    d = B.fetch_all(s, e)
    panel = d["panel"]
    hs = None
    for k, v in d.items():
        if isinstance(v, dict) and "hs300" in v:
            hs = v["hs300"].sort_values("trade_date").set_index("trade_date")["close"]
    g = panel.groupby("trade_date")
    up = g.apply(lambda x: (x["close"] > x["open"]).sum())
    dn = g.apply(lambda x: (x["close"] < x["open"]).sum())
    dn_ratio = g.apply(lambda x: (x["close"] < x["open"]).mean())
    amt = g["amount_yuan"].sum()
    f = pd.DataFrame({"up": up, "dn": dn, "amt": amt, "dn_ratio": dn_ratio})
    f = f[(f.index >= s) & (f.index <= e)]
    f["hs"] = hs.reindex(f.index)
    f["ma20"] = hs.rolling(20).mean().reindex(f.index)
    f["ma60"] = hs.rolling(60).mean().reindex(f.index)
    f["amt20"] = f["amt"].rolling(20).mean()
    f["amt_q20"] = f["amt"].rolling(250, min_periods=60).quantile(0.20)
    f["hs_ret"] = f["hs"].pct_change()
    f["score"] = ((f.hs > f.ma20).astype(int) + (f.hs > f.ma60).astype(int)
                  + (f.amt >= f.amt20).astype(int) + (f.up > f.dn).astype(int))
    f["veto"] = f["dn_ratio"] >= 0.80
    _ERA[tag] = f.dropna(subset=["hs", "ma60"])
    return _ERA[tag]

def run(tag, pe, amend):
    f = era_frame(tag)
    dates = f.index.tolist()
    band = 0.05 if amend else 0.005
    pos, nav, peak = CORE, 1.0, 1.0
    a_cnt = {2: 0, 3: 0, 4: 0}
    floors, rel_cnt = [False]*3, [0]*3
    last_buy_i, last_sell_i = -99, -99
    halt_until, freeze_b = -1, False
    trades, events = 0, []
    hist = []
    pend_target, pend_forced = CORE, None   # 昨日收盘确定，今日收盘执行
    for i, dt_ in enumerate(dates):
        r = f.loc[dt_]
        # 1) 记账：昨日收盘持仓过今日
        if i > 0:
            nav *= 1 + pos*(r["hs_ret"] + 0.025/244) + (1-pos)*(0.018/244)
        peak = max(peak, nav); dd = nav/peak - 1
        # 2) 执行昨日目标（T+1收盘成交；成交后仓位自明日计收益）
        b_floor_now = max([w for k, (q, w, rq) in enumerate(B_RUNGS) if floors[k]] + [0])
        if pend_forced is not None:                       # 熔断强制（不受带宽/锁约束）
            new_pos = pend_forced
            if abs(new_pos - pos) > 1e-9:
                pos = new_pos; trades += 1; last_sell_i = i
            pend_forced = None
        else:
            forbidden = bool(r["veto"]) or (r["hs_ret"] <= -0.02) or (r["amt"] < r["amt_q20"])
            if halt_until >= i:
                pass                                       # 停做期不加仓
            elif pos < pend_target - band:
                if not forbidden and i - last_buy_i >= 3 and not (amend and i - last_sell_i < 10):
                    pos = min(pos + 0.10, pend_target); trades += 1; last_buy_i = i
            elif pos > pend_target + band:
                if not (amend and i - last_buy_i < 10):
                    new_pos = max(pend_target, CORE, b_floor_now)
                    if pos > new_pos + 1e-9:
                        pos = new_pos; trades += 1; last_sell_i = i
        # 3) 收盘信号 → 明日目标
        sc, veto = int(r["score"]), bool(r["veto"])
        for k in (2, 3, 4):
            a_cnt[k] = 0 if (veto or sc < k) else a_cnt[k] + 1
        a_tier = 4 if a_cnt[4] >= 3 else 3 if a_cnt[3] >= 3 else 2 if a_cnt[2] >= 3 else 0
        a_target = CORE if veto else A_TGT[a_tier]
        pe_now = pe.get(dt_, np.nan)
        hist_pe = pe[pe.index <= dt_]
        pct = (hist_pe < pe_now).mean() if (len(hist_pe) >= 500 and not np.isnan(pe_now)) else np.nan
        if not np.isnan(pct):
            for k, (q, w, rq) in enumerate(B_RUNGS):
                if not floors[k] and not freeze_b and pct <= q:
                    floors[k] = True; rel_cnt[k] = 0
                    events.append((dt_, f"B{k+1}地板{int(w*100)}%触发(分位{pct*100:.0f}%)"))
                elif floors[k]:
                    rel_cnt[k] = rel_cnt[k] + 1 if pct > rq else 0
                    if rel_cnt[k] >= 5:
                        floors[k] = False; events.append((dt_, f"B{k+1}地板解除"))
        b_floor = max([w for k, (q, w, rq) in enumerate(B_RUNGS) if floors[k]] + [0])
        # 4) 熔断（收盘判定 → 明日强制执行）
        if dd <= -0.20:
            pend_forced = CORE; halt_until = i + 20; freeze_b = True
            floors = [False]*3; events.append((dt_, "熔断-20%→明日清至核心"))
        elif dd <= -0.15 and halt_until < i:
            pend_forced = max(CORE, b_floor); halt_until = i + 20; freeze_b = True
            events.append((dt_, "熔断-15%→明日机动全退"))
        elif dd <= -0.08:
            pend_target = min(max(CORE, b_floor), pos)     # 冻结加仓+机动撤至A0
        else:
            pend_target = min(CAP, max(CORE, a_target, b_floor))
        hist.append((dt_, nav, pos))
    h = pd.DataFrame(hist, columns=["date", "nav", "pos"]).set_index("date")
    bench = (1 + f["hs_ret"].fillna(0) + 0.025/244).cumprod()
    st50 = (1 + 0.5*(f["hs_ret"].fillna(0) + 0.025/244) + 0.5*0.018/244).cumprod()
    mdd = (h.nav/h.nav.cummax() - 1).min()
    lab = "AMEND(v1.2候选)" if amend else "BASE(v1.1原文)"
    print(f"时代{tag} {lab}: {(h.nav.iloc[-1]-1)*100:+.1f}% | MDD {mdd*100:.1f}% | 均仓 {h.pos.mean()*100:.0f}% | 调仓{trades}次"
          f" | 熔断{sum(1 for _,m in events if '熔断' in m)}次")
    if not amend:
        print(f"  对照: 满仓指数 {(bench.iloc[-1]-1)*100:+.1f}% | 固定50% {(st50.iloc[-1]-1)*100:+.1f}%")
        key = [e for e in events if "B" in e[1] or "熔断" in e[1]]
        print("  关键事件:", "; ".join(f"{d}:{m}" for d, m in key[:14]) or "无")
    return h

if __name__ == "__main__":
    pe = load_pe()
    for tag in ("A", "B"):
        run(tag, pe, amend=False)
        run(tag, pe, amend=True)
