# -*- coding: utf-8 -*-
"""个人再入场协议 v1.2草案 连续回放（2019-01~2026-06 单账户不重启）。

规格=01_策略文档/个人再入场协议-预注册-2026-07-19.md（v1.2草案）。二轮评审后的口径：
- 数据：三段面板拼接（2019-2023 / 2024H1新增缓存 / 2024-06~2026-06）→ 日频聚合连续序列；
  指数MA用全历史宽序列（无截断预热损失）；成交额滚动分位在连续序列上计算——
  除2019年头三个月（min_periods=60，序列起点无更早数据，如实声明）外全程预热完备；
- 会计：ETF市值与现金分账，仓位随价格自然漂移；交易成本单边2bp；带宽判定用实际漂移仓位，
  偏离≥5pp（含等于）才交易；
- 执行：T日收盘确认→T+1收盘成交（pend机制）；熔断T+1强制、豁免带宽与锁；
- B梯：B1观察档（只记录），交易梯B2(30%)/B3(45%)；扩窗分位最少历史=变体参数；
- 单向锁（v1.2）：仅锁"梯A普通卖出后10个交易日内的A驱动再加仓"；一切卖出、B驱动买入、熔断豁免；
- 变体：V11(无锁,500日) / V12L(+锁,500日) / V12H(无锁,750日) / V12(锁+750日)；
  消融（V12参数）：CORE(12%固定) / CORE+A / CORE+B / FULL / STATIC(=FULL均仓固定)。
- 状态分/否决仍为生产口径近似（阴线占比≥80%近似否决），资产=沪深300+2.5%/年分红近似510300。
"""
import sys, os, time
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
import backtest as B
import pipeline as P

CORE, CAP, COST = 0.12, 0.50, 0.0002
A_TGT = {0: CORE, 2: 0.20, 3: 0.35, 4: 0.50}
B_TRADE = [(0.30, 0.30, 0.45), (0.15, 0.45, 0.30)]   # 交易档 (买入分位, 地板, 解除分位)
B_WATCH = (0.50, 0.65)                                # B1观察档（只记录）
PE_CSV = ".pe300_daily.csv"
SEGS = ("20240101", "20240618")                       # 分段统计边界

def load_pe():
    return pd.read_csv(PE_CSV, dtype={"trade_date": str}).set_index("trade_date")["pe_ttm"]

def build_frame():
    parts = []
    hs_full = None
    for s, e in (("20190101", "20231231"), ("20240101", "20240617"), ("20240618", "20260630")):
        d = B.fetch_all(s, e)
        panel = d["panel"]
        for k, v in d.items():
            if isinstance(v, dict) and "hs300" in v:
                h = v["hs300"].sort_values("trade_date").set_index("trade_date")["close"]
                hs_full = h if hs_full is None or len(h) > len(hs_full) else hs_full
        g = panel.groupby("trade_date")
        parts.append(pd.DataFrame({
            "up": g.apply(lambda x: (x["close"] > x["open"]).sum()),
            "dn": g.apply(lambda x: (x["close"] < x["open"]).sum()),
            "dn_ratio": g.apply(lambda x: (x["close"] < x["open"]).mean()),
            "amt": g["amount_yuan"].sum()}))
    f = pd.concat(parts)
    f = f[~f.index.duplicated()].sort_index()
    f = f[(f.index >= "20190101") & (f.index <= "20260630")]
    f["hs"] = hs_full.reindex(f.index)
    f["ma20"] = hs_full.rolling(20).mean().reindex(f.index)
    f["ma60"] = hs_full.rolling(60).mean().reindex(f.index)
    f["amt20"] = f["amt"].rolling(20).mean()
    f["amt_q20"] = f["amt"].rolling(250, min_periods=60).quantile(0.20)
    f["hs_ret"] = f["hs"].pct_change()
    f["score"] = ((f.hs > f.ma20).astype(int) + (f.hs > f.ma60).astype(int)
                  + (f.amt >= f.amt20).astype(int) + (f.up > f.dn).astype(int))
    f["veto"] = f["dn_ratio"] >= 0.80
    assert not f["hs"].isna().any(), "指数序列有缺口"
    return f

def run(f, pe, lock=False, minhist=750, use_a=True, use_b=True, static=None, label=""):
    dates = f.index.tolist()
    etf, cash = CORE, 1.0 - CORE
    a_cnt = {2: 0, 3: 0, 4: 0}
    floors, rel_cnt = [False]*len(B_TRADE), [0]*len(B_TRADE)
    watch_on, watch_rel = False, 0
    last_buy_i, last_a_sell_i = -99, -99
    halt_until, freeze_b = -1, False
    trades, events, hist = 0, [], []
    pend_target, pend_forced, pend_b_driven = CORE, None, False
    peak = 1.0
    for i, dt_ in enumerate(dates):
        r = f.loc[dt_]
        if i > 0:
            etf *= 1 + r["hs_ret"] + 0.025/244
            cash *= 1 + 0.018/244
        nav = etf + cash
        pos = etf / nav
        peak = max(peak, nav); dd = nav/peak - 1
        if freeze_b and halt_until == i - 1:
            freeze_b = False                            # 停做期满复核通过（回放假设）
        b_floor_now = max([w for k, (q, w, rq) in enumerate(B_TRADE) if floors[k]] + [0])
        # —— T+1执行（昨日收盘确定的目标/强制动作）——
        if static is not None:
            tgt = static
            if abs(tgt - pos) >= 0.05:
                delta = (tgt - pos) * nav
                etf += delta - abs(delta)*COST; cash -= delta; trades += 1
        elif pend_forced is not None:
            delta = (pend_forced - pos) * nav
            if abs(delta) > 1e-9:
                etf += delta - abs(delta)*COST; cash -= delta; trades += 1
                if delta < 0: last_a_sell_i = i
            pend_forced = None
        else:
            forbidden = bool(r["veto"]) or (r["hs_ret"] <= -0.02) or \
                        (not np.isnan(r["amt_q20"]) and r["amt"] < r["amt_q20"])
            if halt_until >= i:
                pass
            elif pos <= pend_target - 0.05:             # 加仓（含等于5pp）
                locked = lock and (not pend_b_driven) and (i - last_a_sell_i < 10)
                if not forbidden and i - last_buy_i >= 3 and not locked:
                    step = min(0.10, pend_target - pos)
                    delta = step * nav
                    etf += delta - delta*COST; cash -= delta; trades += 1; last_buy_i = i
            elif pos >= pend_target + 0.05:             # 减仓（不受锁）
                new_pos = max(pend_target, CORE, b_floor_now)
                if pos - new_pos >= 0.05:
                    delta = (new_pos - pos) * nav
                    etf += delta - abs(delta)*COST; cash -= delta; trades += 1; last_a_sell_i = i
        nav = etf + cash; pos = etf / nav
        # —— 收盘信号 → 明日目标 ——
        sc, veto = int(r["score"]), bool(r["veto"])
        for k in (2, 3, 4):
            a_cnt[k] = 0 if (veto or sc < k) else a_cnt[k] + 1
        a_tier = 4 if a_cnt[4] >= 3 else 3 if a_cnt[3] >= 3 else 2 if a_cnt[2] >= 3 else 0
        a_target = (CORE if veto else A_TGT[a_tier]) if use_a else CORE
        pe_now = pe.get(dt_, np.nan)
        hist_pe = pe[pe.index <= dt_]
        pct = (hist_pe < pe_now).mean() if (len(hist_pe) >= minhist and not np.isnan(pe_now)) else np.nan
        if use_b and not np.isnan(pct):
            if not watch_on and pct <= B_WATCH[0]:
                watch_on = True; watch_rel = 0; events.append((dt_, f"B1观察档触发(分位{pct*100:.0f}%)"))
            elif watch_on:
                watch_rel = watch_rel + 1 if pct > B_WATCH[1] else 0
                if watch_rel >= 5: watch_on = False; events.append((dt_, "B1观察档解除"))
            for k, (q, w, rq) in enumerate(B_TRADE):
                if not floors[k] and not freeze_b and dd > -0.08 and pct <= q:
                    floors[k] = True; rel_cnt[k] = 0
                    events.append((dt_, f"B{k+2}地板{int(w*100)}%触发(分位{pct*100:.0f}%)"))
                elif floors[k]:
                    rel_cnt[k] = rel_cnt[k] + 1 if pct > rq else 0
                    if rel_cnt[k] >= 5:
                        floors[k] = False; events.append((dt_, f"B{k+2}地板解除"))
        b_floor = max([w for k, (q, w, rq) in enumerate(B_TRADE) if floors[k]] + [0]) if use_b else 0
        # —— 熔断（收盘判定 → 明日强制）——
        if dd <= -0.20:
            pend_forced = CORE; halt_until = i + 20; freeze_b = True
            floors = [False]*len(B_TRADE); events.append((dt_, f"熔断-20%(dd={dd*100:.1f}%)"))
        elif dd <= -0.15 and halt_until < i:
            pend_forced = max(CORE, b_floor); halt_until = i + 20; freeze_b = True
            events.append((dt_, f"熔断-15%(dd={dd*100:.1f}%)"))
        elif dd <= -0.08:
            pend_target = min(max(CORE, b_floor), pos); pend_b_driven = False
        else:
            pend_target = min(CAP, max(CORE, a_target, b_floor))
            pend_b_driven = b_floor > max(CORE, a_target)
        hist.append((dt_, nav, pos, dd))
    h = pd.DataFrame(hist, columns=["date", "nav", "pos", "dd"]).set_index("date")
    mdd = h.dd.min()
    print(f"{label:<12} 全期 {(h.nav.iloc[-1]-1)*100:+7.1f}% | MDD {mdd*100:6.1f}% | 均仓 {h.pos.mean()*100:3.0f}% | "
          f"调仓{trades:4d}次 | 熔断{sum(1 for _, m in events if '熔断' in m)}次")
    return h, events

if __name__ == "__main__":
    pe = load_pe()
    f = build_frame()
    print(f"连续序列: {f.index[0]}~{f.index[-1]} 共{len(f)}个交易日\n")
    print("== 变体矩阵（连续单账户）==")
    res = {}
    res["V11(无锁,500)"] = run(f, pe, lock=False, minhist=500, label="V11")
    res["V12L(锁,500)"] = run(f, pe, lock=True, minhist=500, label="V12L")
    res["V12H(无锁,750)"] = run(f, pe, lock=False, minhist=750, label="V12H")
    res["V12(锁+750)"] = run(f, pe, lock=True, minhist=750, label="V12")
    print("\n== 消融（V12参数）==")
    run(f, pe, use_a=False, use_b=False, label="CORE only")
    run(f, pe, lock=True, minhist=750, use_b=False, label="CORE+A")
    run(f, pe, lock=True, minhist=750, use_a=False, label="CORE+B")
    hfull, ev = res["V12(锁+750)"]
    avgp = hfull.pos.mean()
    run(f, pe, static=round(avgp, 2), label=f"STATIC{avgp*100:.0f}%")
    bench = (1 + f["hs_ret"].fillna(0) + 0.025/244).cumprod()
    bm = (bench/bench.cummax()-1).min()
    print(f"{'满仓指数':<12} 全期 {(bench.iloc[-1]-1)*100:+7.1f}% | MDD {bm*100:6.1f}%")
    print("\n== V12关键事件 ==")
    for d, m in ev:
        if "熔断" in m or "地板" in m or "观察" in m: print(f"  {d}: {m}")
    print("\n== V12分段（同一账户内） ==")
    seg_bounds = [("2019-2023", None, "20231231"), ("2024H1", "20240101", "20240617"), ("2024H2-2026", "20240618", None)]
    for name, s0, s1 in seg_bounds:
        seg = hfull.loc[s0:s1] if s0 else hfull.loc[:s1]
        if len(seg) < 2: continue
        print(f"  {name}: {(seg.nav.iloc[-1]/seg.nav.iloc[0]-1)*100:+.1f}% | 段内最深dd {(seg.dd.min())*100:.1f}% | 均仓 {seg.pos.mean()*100:.0f}%")
