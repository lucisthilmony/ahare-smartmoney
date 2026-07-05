# -*- coding: utf-8 -*-
"""
龙虎榜数据拉取（席位性格研究备料，2026-07-02）
按交易日拉 top_list（上榜个股）+ top_inst（席位明细），存 pickle 缓存；支持断点续传（每50天落盘一次）。
用法：./.venv/bin/python 龙虎榜拉取.py 20190101 20231231
     ./.venv/bin/python 龙虎榜拉取.py 20240618 20260630
输出：.toplist_cache_<start>_<end>.pkl  → {"top_list": DataFrame, "top_inst": DataFrame, "done_dates": set}
"""
import os, sys, time, pickle, datetime as dt
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline as P

def log(m): print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)

def main(start, end):
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), f".toplist_cache_{start}_{end}.pkl")
    state = {"top_list": [], "top_inst": [], "done_dates": set()}
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            saved = pickle.load(f)
        state["top_list"] = [saved["top_list"]] if len(saved["top_list"]) else []
        state["top_inst"] = [saved["top_inst"]] if len(saved["top_inst"]) else []
        state["done_dates"] = saved["done_dates"]
        log(f"断点续传：已有 {len(state['done_dates'])} 天")
    cal = P._ts_query("trade_cal", exchange="SSE", start_date=start, end_date=end, is_open="1")
    dates = [d for d in sorted(cal["cal_date"].tolist()) if d not in state["done_dates"]]
    log(f"待拉 {len(dates)} 天…")

    def flush():
        P.assert_cache_write_ok()   # pandas版本护栏
        tl = pd.concat(state["top_list"], ignore_index=True) if state["top_list"] else pd.DataFrame()
        ti = pd.concat(state["top_inst"], ignore_index=True) if state["top_inst"] else pd.DataFrame()
        with open(cache, "wb") as f:
            pickle.dump({"top_list": tl, "top_inst": ti, "done_dates": state["done_dates"]}, f)
        state["top_list"] = [tl] if len(tl) else []
        state["top_inst"] = [ti] if len(ti) else []

    for k, d in enumerate(dates):
        try:
            tl = P._ts_query("top_list", trade_date=d,
                             fields="trade_date,ts_code,name,close,pct_change,turnover_rate,amount,net_amount,reason")
            if tl is not None and len(tl):
                state["top_list"].append(tl)
            time.sleep(0.12)
            ti = P._ts_query("top_inst", trade_date=d,
                             fields="trade_date,ts_code,exalter,side,buy,sell,net_buy")
            if ti is not None and len(ti):
                state["top_inst"].append(ti)
            state["done_dates"].add(d)
        except Exception as e:
            log(f"  {d} 失败: {str(e)[:60]}（跳过，可重跑续传）")
        time.sleep(0.12)
        if k % 50 == 49:
            flush(); log(f"  …{k+1}/{len(dates)} 已落盘（至 {d}）")
    flush()
    log(f"完成：{cache}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
