# -*- coding: utf-8 -*-
"""
时点数据层（v6.4 P3 · 2026-07-10）——消除回测的两类前视/幸存者偏差：
  ① ST状态：此前用"当前股票名"回溯（曾ST已摘帽的被误杀、当时ST的漏排）→ 改用 namechange 曾用名区间精确判定；
  ② 行业分类：此前用 stock_basic 当前静态行业（重分类前视，直接污染Top5主线门）→ 改用申万2021 **L2** 成分
     （含 in_date/out_date，粒度~134行业，与原细分行业最接近；这是"修复+分类源迁移"，回测实盘同步换）。

产出缓存：.pit_cache.pkl = {"st": {ts: [(start,end)]}, "ind": {ts: [(l2_name,in,out)]}, "pulled_at": str}
用法：./.venv/bin/python 时点数据.py   # 拉取/刷新缓存（约2-4分钟）
查询：import 时点数据; 时点数据.load(); 时点数据.st_at(ts,d); 时点数据.ind_at(ts,d)
"""
import os, sys, time, pickle, datetime as dt
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline as P

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pit_cache.pkl")
_DB = None

def log(m): print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)

def build():
    # ---- ① 曾用名 → ST区间 ----
    log("拉取全市场曾用名（namechange，分页）…")
    frames, offset = [], 0
    while True:
        df = P._ts_query("namechange", fields="ts_code,name,start_date,end_date", limit=10000, offset=offset)
        time.sleep(0.3)
        if df is None or not len(df):
            break
        frames.append(df)
        if len(df) < 10000:
            break
        offset += 10000
    nc = pd.concat(frames, ignore_index=True)
    log(f"  曾用名 {len(nc)} 条")
    st = {}
    for ts, g in nc.groupby("ts_code"):
        iv = []
        for _, r in g.iterrows():
            if P.is_st(r["name"]):
                iv.append((str(r["start_date"] or "19900101"), str(r["end_date"] or "29991231")))
        if iv:
            st[ts] = sorted(iv)
    log(f"  含ST/退区间的股票 {len(st)} 只")
    # ---- ② 申万L2成分（含历史进出）----
    log("拉取申万2021 L1列表与全部L2成分区间…")
    l1 = P._ts_query("index_classify", level="L1", src="SW2021", fields="index_code,industry_name")
    time.sleep(0.3)
    ind = {}
    for _, r in l1.iterrows():
        m = P._ts_query("index_member_all", l1_code=r["index_code"],
                        fields="ts_code,l2_name,in_date,out_date")
        time.sleep(0.25)
        if m is None:
            continue
        for _, x in m.iterrows():
            ind.setdefault(x["ts_code"], []).append(
                (x["l2_name"], str(x["in_date"] or "19900101"), str(x["out_date"] or "29991231")))
        log(f"  {r['industry_name']}: {len(m)} 条")
    db = {"st": st, "ind": ind, "pulled_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    P.assert_cache_write_ok()
    with open(CACHE, "wb") as f:
        pickle.dump(db, f)
    log(f"时点缓存已写入：ST股票{len(st)}只 / 行业成分股票{len(ind)}只")
    return db

def load(refresh=False):
    global _DB
    if _DB is not None and not refresh:
        return _DB
    if os.path.exists(CACHE) and not refresh:
        with open(CACHE, "rb") as f:
            _DB = pickle.load(f)
    else:
        _DB = build()
    return _DB

def st_at(ts, d):
    """d(YYYYMMDD)当日该股是否ST/退市整理。"""
    for a, b in load()["st"].get(ts, ()):
        if a <= d <= b:
            return True
    return False

def ind_at(ts, d):
    """d当日该股的申万L2行业名；无记录返回 None（≈次新/未入指数体系）。"""
    for nm, a, b in load()["ind"].get(ts, ()):
        if a <= d <= b:
            return nm
    return None

if __name__ == "__main__":
    build()
