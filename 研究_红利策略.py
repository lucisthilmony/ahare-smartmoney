# -*- coding: utf-8 -*-
"""红利策略研究执行器 v2（评审四缺口修复版，2026-07-20）。

修复：①T日收盘选股→T+1收盘成交起持有；②固定份额会计——停牌沿用最后价(ffill)、
数据终止(退市等)按最后可得价结算转现金并计数，禁止mean()幸存者重加权；
③完整成本=佣金0.03%+卖出印花税0.05%+滑点(计入佣金项)按换手计提+红利税模型；
④H00922/H20269/512890全部在本执行器内抓取，含MDD，可复现。
新增：512890实际产品检验、510300:红利低波50:50双腿回放（半年+10pp带）、三时代分段。
预注册=../02_回测报告/红利策略研究-预注册-2026-07-20.md。
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
HIST = ["20170630","20171229","20180629","20181228"] + SEMI[:-1]
ANNUAL = [d for d in SEMI if d[4:6] == "06"] + ["20260630"]
C_BUY, C_SELL = 0.0003, 0.0008          # 买0.03%(佣金+滑点)；卖0.03%+印花0.05%
RF = 0.018

def build_pivots():
    parts_c, parts_a = [], []
    for s, e in (("20190101","20231231"), ("20240101","20240617"), ("20240618","20260630")):
        d = B.fetch_all(s, e)["panel"]
        parts_c.append(d.pivot(index="trade_date", columns="ts_code", values="close"))
        parts_a.append(d.pivot(index="trade_date", columns="ts_code", values="amount_yuan"))
    C = pd.concat(parts_c).sort_index(); A = pd.concat(parts_a).sort_index()
    return C[~C.index.duplicated()], A[~A.index.duplicated()]

_DV = {}
def dv_snap(date):
    if date not in _DV:
        df = P._ts_query("daily_basic", trade_date=date, fields="ts_code,dv_ttm")
        df["dv_ttm"] = pd.to_numeric(df["dv_ttm"], errors="coerce")
        _DV[date] = df.set_index("ts_code")["dv_ttm"]; time.sleep(0.5)
    return _DV[date]

def select(nominal, C, A, quality):
    d0 = max(d for d in C.index if d <= nominal)        # T日（选股信息截止）
    dv = dv_snap(d0)
    amt20 = A.loc[:d0].tail(20).mean()
    liquid = set(amt20[amt20 >= 3e7].index)
    pool = dv[(dv > 0) & dv.index.isin(liquid)].dropna()
    pool = pool[[not PIT.st_at(ts, d0) for ts in pool.index]]
    if quality:
        pool = pool[pool <= 12.0]
        snaps = [s for s in HIST if s < nominal and s[4:6] == nominal[4:6]][-2:]
        if len(snaps) == 2:
            o1, o2 = dv_snap(snaps[0]), dv_snap(snaps[1])
            pool = pool[[(ts in o1.index and o1[ts] > 0) and (ts in o2.index and o2[ts] > 0)
                         for ts in pool.index]]
    top = pool.nlargest(50)
    return list(top.index), float(top.median()), d0

def leg_path(C, members, d_sel, d_end):
    """T+1收盘等权买入固定份额；停牌ffill；序列终止按最后价结算转现金。返回日度净值(入场=1)与统计。"""
    dates = list(C.index)
    i_sel = dates.index(d_sel)
    if i_sel + 1 >= len(dates): return None, 0, 0
    d_in = dates[i_sel + 1]                              # T+1成交日
    cols = [m for m in members if m in C.columns]
    sub = C.loc[d_in:d_end, cols]
    entry = sub.iloc[0]
    buyable = entry.notna()                              # T+1停牌无法买入→该份额留现金
    n_skip = int((~buyable).sum())
    sub = sub.loc[:, buyable].ffill()                    # 停牌沿用最后价
    w0 = 1.0 / len(cols)                                 # 固定初始权重（含未买入份额）
    shares = w0 / sub.iloc[0]                            # 每股固定份额
    vals = sub.mul(shares, axis=1)                       # 各持仓市值路径（ffill后无NaN）
    # 序列终止检测：ffill后仍NaN只可能在头部；尾部终止=原始数据在d_end前结束
    raw = C.loc[d_in:d_end, sub.columns]
    dead = raw.apply(lambda s: s.last_valid_index())
    n_dead = int((dead < raw.index[-1]).sum())           # 提前终止(退市/移出)按最后价冻结（ffill已实现）
    nav = vals.sum(axis=1) + n_skip * w0                 # 未买入份额=现金(不计息,腿内≤半年)
    return nav / nav.iloc[0], n_skip, n_dead

def run(C, A, legs, quality, label):
    navs, carries, overlaps, daily = [1.0], [], [], []
    prev, skip_t, dead_t = None, 0, 0
    for i in range(len(legs) - 1):
        mem, carry, d_sel = select(legs[i], C, A, quality)
        d_end_sel = max(d for d in C.index if d <= legs[i+1])
        dates = list(C.index); j = dates.index(d_end_sel)
        d_end = dates[min(j + 1, len(dates) - 1)]        # 下一腿T+1成交日=本腿终点(无缝)
        nv, ns, nd = leg_path(C, mem, d_sel, d_end)
        if nv is None: break
        gross = nv.iloc[-1]
        ov = len(set(mem) & set(prev)) / 50 if prev else 0.0
        turn = 1 - ov
        cost = turn * (C_BUY + C_SELL) + (C_BUY + C_SELL) * 0.0  # 换手部分双边
        navs.append(navs[-1] * gross * (1 - cost))
        carries.append(carry); overlaps.append(ov) if prev else None
        prev = mem; skip_t += ns; dead_t += nd
        daily.append(nv / nv.iloc[0] * (daily[-1].iloc[-1] if daily else 1.0) * (1 - cost))
    nav_d = pd.concat(daily)
    mdd = (nav_d / nav_d.cummax() - 1).min()
    carry = float(np.median(carries)); ov = float(np.mean(overlaps)) if overlaps else 0
    lpy = 2 if legs is SEMI else 1
    churn = lpy * (1 - ov)
    tax = 0.10 * (carry / 100) * min(churn, 1.0)
    yrs = len(nav_d) / 244
    gross_r = navs[-1] - 1
    net = (1 + gross_r) * ((1 - tax) ** yrs) - 1
    print(f"{label:<22} 毛(含费) {gross_r*100:+7.1f}% | 税后 {net*100:+7.1f}% (年化{((1+net)**(1/yrs)-1)*100:+.1f}%) | "
          f"MDD {mdd*100:6.1f}% | carry {carry:.1f}% | 换手{churn*100:3.0f}%/年 | 入场停牌跳过{skip_t} 提前终止{dead_t}")
    return nav_d

def fetch_series(api, code, val_col, date_col):
    rows = []
    for y0, y1 in (("20190101","20211231"),("20220101","20241231"),("20250101","20991231")):
        kw = {"ts_code": code, "start_date": y0, "end_date": y1}
        rows.append(P._ts_query(api, **kw)); time.sleep(0.8)
    df = pd.concat(rows)
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    s = df.dropna(subset=[val_col]).sort_values(date_col).set_index(date_col)[val_col]
    return s[~s.index.duplicated()]

def metrics(nav, name, bench=None):
    nav = nav.dropna()
    yrs = len(nav) / 244
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
    mdd = (nav / nav.cummax() - 1).min()
    ret = nav.pct_change().dropna()
    vol = ret.std() * np.sqrt(244)
    sharpe = (cagr - RF) / vol if vol > 0 else np.nan
    line = f"{name:<26} CAGR {cagr*100:+5.1f}% | MDD {mdd*100:6.1f}% | 波动 {vol*100:4.1f}% | Sharpe {sharpe:5.2f}"
    if bench is not None:
        b = bench.reindex(nav.index).ffill()
        br = b.pct_change().dropna()
        common = ret.index.intersection(br.index)
        dn = br[common] < 0
        cap = ret[common][dn].mean() / br[common][dn].mean() if dn.sum() else np.nan
        rel = (nav / nav.iloc[0]) / (b / b.iloc[0])
        under = (rel < rel.cummax()).astype(int)
        # 最长跑输(相对净值未创新高)天数
        runs, cur = 0, 0
        for x in under:
            cur = cur + 1 if x else 0
            runs = max(runs, cur)
        line += f" | 下行捕获 {cap:4.2f} | 最长跑输 {runs/244*12:.0f}个月"
    print(line)
    return cagr, mdd

def era_split(nav, name):
    for tag, s, e in (("2019-2021", "20190701", "20211231"),
                      ("2022-2023", "20220101", "20231231"),
                      ("2024-2026", "20240101", "20260630")):
        seg = nav.loc[s:e].dropna()
        if len(seg) > 20:
            r = seg.iloc[-1]/seg.iloc[0] - 1
            dd = (seg/seg.cummax()-1).min()
            print(f"  {name} {tag}: {r*100:+6.1f}% | 段内MDD {dd*100:.1f}%")

if __name__ == "__main__":
    C, A = build_pivots()
    print(f"连续面板 {C.index[0]}~{C.index[-1]}\n== 一、自建变体（v2修正口径）==")
    run(C, A, SEMI, False, "V0 基线半年调")
    run(C, A, SEMI, True,  "V1 质量半年调")
    n2 = run(C, A, ANNUAL, True, "V2 质量年度调")

    print("\n== 二、指数与实际产品（同执行器抓取，20190628基准=1）==")
    h00922 = fetch_series("index_daily", "H00922.CSI", "close", "trade_date")
    h20269 = fetch_series("index_daily", "H20269.CSI", "close", "trade_date")
    h00300 = fetch_series("index_daily", "H00300.CSI", "close", "trade_date")
    nav512 = fetch_series("fund_nav", "512890.SH", "adj_nav", "nav_date")
    win = lambda s: (s[(s.index >= "20190628") & (s.index <= "20260630")]
                     .pipe(lambda x: x / x.iloc[0]))
    b300 = win(h00300)
    metrics(win(h00922), "中证红利全收益H00922", b300)
    lv = win(h20269)
    metrics(lv, "红利低波全收益H20269", b300)
    f512 = win(nav512)
    metrics(f512, "512890实际净值(费已含)", b300)
    metrics(b300, "沪深300全收益H00300")
    # 512890跟踪核对
    common = f512.index.intersection(lv.index)
    tr_gap = ((f512[common].iloc[-1]/f512[common].iloc[0]) /
              (lv[common].iloc[-1]/lv[common].iloc[0])) ** (244/len(common)) - 1
    print(f"512890 vs 红利低波全收益 年化跟踪差 ≈ {tr_gap*100:+.2f}%/年（含费率，负值=产品落后指数）")

    print("\n== 三、双腿回放：510300(H00300) : 红利低波(512890实际净值) = 50:50，半年再平衡±10pp带，2bp/边 ==")
    a, b = b300.ffill(), f512.reindex(b300.index).ffill()
    wa = wb = 0.5; nav = [1.0]; idx = [b300.index[0]]
    reb = set(SEMI)
    va, vb = 0.5, 0.5
    for i in range(1, len(b300.index)):
        d = b300.index[i]
        va *= a.iloc[i] / a.iloc[i-1]
        vb *= (b.iloc[i] / b.iloc[i-1]) if not (np.isnan(b.iloc[i]) or np.isnan(b.iloc[i-1])) else 1.0
        tot = va + vb
        if d in reb and abs(va/tot - 0.5) > 0.10:
            cost = abs(va/tot - 0.5) * tot * 2 * 0.0002
            tot -= cost; va = vb = tot / 2
        nav.append(tot); idx.append(d)
    two = pd.Series(nav, index=idx)
    metrics(two, "双腿50:50(半年±10pp)", b300)
    metrics(b300, "100%沪深300全收益")
    metrics(f512, "100%红利低波(512890)")

    print("\n== 四、分时代 ==")
    era_split(two, "双腿50:50")
    era_split(b300, "100%沪深300")
    era_split(f512, "100%红利低波")
    era_split(n2, "V2自建(参考)")
