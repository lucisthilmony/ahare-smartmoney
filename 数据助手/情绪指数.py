# -*- coding: utf-8 -*-
"""
A股赚钱效应/情绪指数 · 日频记录器（前向观察层，2026-07-02 起）

定位（重要）：**只记录，不门控**。2026-07-02 回测已证明：可观测状态开关救不了负期望的入场逻辑
（见《回测全过程详录》第4节"主线稳定性开关：否定"）。本脚本的目的不是造新开关，而是：
  ① 前向攒一份与决策无关的情绪指标日志，供日后诊断"策略失效期 vs 情绪状态"的关系（观察→再预注册）；
  ② 给失效判据（滚动60笔期望）提供环境注释，复盘时能区分"策略死了"还是"环境冰点"。

指标（全部由日线+pre_close计算，无盘中数据；游资蒸馏资料中的高频口径）：
  up_cnt/down_cnt      上涨/下跌家数（收盘 vs 昨收）
  amount_yi            全市场成交额(亿元)——资料口径"1万亿生死线/1.3万亿首板环境"
  limit_up/limit_down  涨停/跌停家数（按板块/日期规则：主板9.7%、创业板2020-08-24后19.7%、科创19.7%）
  zha_rate             炸板率≈盘中触及涨停(high达阈)但收盘未封 / (触及总数)——资料阈值">30家/率高→停止打板"
  lianban_cnt          连板家数(今日涨停且昨日也涨停)
  max_streak           最高连板高度——资料"破6板=破局信号；空间板状态"
  promo_rate           晋级率：昨日涨停股今日再涨停占比——赚钱效应核心
  ylu_open_prem        昨日涨停股今日平均开盘溢价%（竞价承接）
  ylu_close_ret        昨日涨停股今日平均收盘涨幅%（打板隔日溢价——资料判定赚钱效应的第一指标）

已知近似（诚实限制）：
  - ST(5%涨停)不会被计入涨停统计（阈值检不到）；北交所排除；炸板用日线high近似，略低估真实炸板。
  - pre_close 为交易所除权后口径，涨跌幅计算天然正确，无需复权。

用法：
  ./.venv/bin/python 情绪指数.py                       # 增量：补齐最近40个交易日中缺失的日期
  ./.venv/bin/python 情绪指数.py --backfill 20190101 20260630   # 历史回填（约1800次API调用，10-20分钟）
输出：数据助手/情绪指数_日频.csv（按日期upsert，可重复运行）
"""
import os, sys, time, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline as P

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "情绪指数_日频.csv")
WARMUP = 30          # 连板高度回溯所需的头部预热交易日数
def log(m): print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)

def trade_dates(start, end):
    cal = P._ts_query("trade_cal", exchange="SSE", start_date=start, end_date=end, is_open="1")
    return sorted(cal["cal_date"].tolist())

def pull_day(d):
    df = P._ts_query("daily", fields="ts_code,trade_date,open,high,low,close,pre_close,amount", trade_date=d)
    if df is None or not len(df):
        return None
    df["board"] = df["ts_code"].str[:6].map(P.board_of)
    df = df[df["board"].notna()].copy()          # 排除北交所等
    df["ret"] = df["close"] / df["pre_close"] - 1
    df["hret"] = df["high"] / df["pre_close"] - 1
    df["oret"] = df["open"] / df["pre_close"] - 1
    thr = df.apply(lambda r: P.limit_up_thr(r["board"], d), axis=1)
    df["is_limit"] = df["ret"] >= thr
    df["touched"] = df["hret"] >= thr
    df["is_ldown"] = df["ret"] <= -thr
    return df

def compute(dates):
    """顺序计算每个日期的指标（dates 含预热头部；预热部分只维护状态不输出）。"""
    rows = []
    prev_limit = None      # 昨日涨停集合
    streak = {}            # code -> 连板数
    for k, d in enumerate(dates):
        df = pull_day(d)
        time.sleep(0.12)
        if df is None:
            continue
        lim_set = set(df.loc[df["is_limit"], "ts_code"])
        # 连板状态更新
        streak = {c: streak.get(c, 0) + 1 for c in lim_set}
        lianban = sum(1 for v in streak.values() if v >= 2)
        max_streak = max(streak.values()) if streak else 0
        rec = None
        if prev_limit is not None and k >= 1:
            alive = df[df["ts_code"].isin(prev_limit)]
            n_alive = len(alive)
            promo = (alive["is_limit"].mean() * 100) if n_alive else np.nan
            oprem = (alive["oret"].mean() * 100) if n_alive else np.nan
            cret = (alive["ret"].mean() * 100) if n_alive else np.nan
        else:
            promo = oprem = cret = np.nan
        touched = int(df["touched"].sum()); limup = int(df["is_limit"].sum())
        rows.append(dict(date=d,
                         up_cnt=int((df["ret"] > 0).sum()), down_cnt=int((df["ret"] < 0).sum()),
                         amount_yi=round(df["amount"].sum() / 1e5, 0),   # amount单位千元→亿
                         limit_up=limup, limit_down=int(df["is_ldown"].sum()),
                         zha_cnt=touched - limup,
                         zha_rate=round((touched - limup) / touched * 100, 1) if touched else np.nan,
                         lianban_cnt=lianban, max_streak=max_streak,
                         promo_rate=round(promo, 1) if promo == promo else np.nan,
                         ylu_open_prem=round(oprem, 2) if oprem == oprem else np.nan,
                         ylu_close_ret=round(cret, 2) if cret == cret else np.nan))
        prev_limit = lim_set
        if k % 40 == 0:
            log(f"  …{k}/{len(dates)}  {d}")
    return pd.DataFrame(rows)

def upsert(new_df, skip_head):
    out = new_df.iloc[skip_head:].copy()      # 丢掉预热段（连板/晋级状态未就绪）
    if os.path.exists(CSV):
        old = pd.read_csv(CSV, dtype={"date": str})
        merged = pd.concat([old[~old["date"].isin(out["date"])], out], ignore_index=True)
    else:
        merged = out
    merged = merged.sort_values("date").reset_index(drop=True)
    merged.to_csv(CSV, index=False, encoding="utf-8-sig")
    log(f"已写入 {CSV}：共 {len(merged)} 天（本次新增/更新 {len(out)} 天）")

if __name__ == "__main__":
    t0 = time.time()
    if len(sys.argv) >= 4 and sys.argv[1] == "--backfill":
        start, end = sys.argv[2], sys.argv[3]
        head = (dt.datetime.strptime(start, "%Y%m%d").date() - dt.timedelta(days=60)).strftime("%Y%m%d")
        dates = trade_dates(head, end)
        n_head = len([d for d in dates if d < start])
        log(f"回填 {start}~{end}：{len(dates)} 天（含预热 {n_head} 天）")
        upsert(compute(dates), n_head)
    else:
        today = dt.date.today().strftime("%Y%m%d")
        start = (dt.date.today() - dt.timedelta(days=90)).strftime("%Y%m%d")
        dates = trade_dates(start, today)[-(40 + WARMUP):]
        done = set()
        if os.path.exists(CSV):
            done = set(pd.read_csv(CSV, dtype={"date": str})["date"])
        if all(d in done for d in dates[WARMUP:]):
            log("最近40个交易日已齐，无需更新。")
        else:
            log(f"增量更新：重算最近 {len(dates)} 天（预热 {WARMUP} 天）")
            upsert(compute(dates), WARMUP)
    log(f"完成，用时 {time.time()-t0:.0f}s")
