# -*- coding: utf-8 -*-
"""次新质量成长策略：数据收集（预注册2026-08-04配套，断点续传）。

只收原始数据不算收益：
1. .cixin_universe.pkl  —— 股票基础表（L/D/P全量，除北交所），含list_date/delist_date/market
2. .cixin_fina_v2.pkl   —— 上市于2016-07-01~2025-06-30个股的fina_indicator
                           （ann_date/end_date/or_yoy/op_yoy/netprofit_yoy/netprofit_margin/
                             profit_dedt/update_flag——评审P2：锁首次披露版本+扣非盈利判定）
3. .cixin_dailybasic.pkl—— 三窗口各月末决策日全市场daily_basic（pe_ttm/total_mv）
4. .cixin_index.pkl     —— 000852.SH（价格）/H00852.CSI（全收益，判据②基准）/932000.CSI（若可得）
"""
import os, sys, time, pickle
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
import pipeline as P
import pandas as pd

U_PKL, F_PKL, B_PKL, I_PKL = ".cixin_universe.pkl", ".cixin_fina_v2.pkl", ".cixin_dailybasic.pkl", ".cixin_index.pkl"

def log(*a):
    print("[%s]" % time.strftime("%H:%M:%S"), *a, flush=True)

# ── 1. 宇宙 ──
if os.path.exists(U_PKL):
    sb = pickle.load(open(U_PKL, "rb"))
else:
    frames = []
    for st in ("L", "D", "P"):
        d = P._ts_query("stock_basic", exchange="", list_status=st,
                        fields="ts_code,name,list_date,delist_date,market")
        if d is not None and len(d):
            d["list_status"] = st
            frames.append(d)
        time.sleep(0.2)
    sb = pd.concat(frames, ignore_index=True)
    sb = sb[~sb.ts_code.str.endswith(".BJ")].reset_index(drop=True)
    pickle.dump(sb, open(U_PKL, "wb"))
log("宇宙:", len(sb), "只（含退市，除北交所）")

# ── 2. 财务（断点续传）──
targets = sb[(sb.list_date >= "20160701") & (sb.list_date <= "20250630")].ts_code.tolist()
fina = pickle.load(open(F_PKL, "rb")) if os.path.exists(F_PKL) else {}
todo = [c for c in targets if c not in fina]
log("财务目标 %d 只，待拉 %d 只" % (len(targets), len(todo)))
FLD = "ts_code,ann_date,end_date,or_yoy,op_yoy,netprofit_yoy,netprofit_margin,profit_dedt,update_flag"
for i, code in enumerate(todo):
    try:
        d = P._ts_query("fina_indicator", ts_code=code, fields=FLD)
        fina[code] = d if d is not None else pd.DataFrame()
    except Exception as e:
        log("跳过", code, e)
        time.sleep(1.0)
        continue
    if (i + 1) % 100 == 0:
        pickle.dump(fina, open(F_PKL, "wb"))
        log("财务进度 %d/%d" % (i + 1, len(todo)))
    time.sleep(0.12)
pickle.dump(fina, open(F_PKL, "wb"))
log("财务完成:", len(fina), "只")

# ── 3. 月末决策日横截面 ──
idx = P._ts_query("index_daily", ts_code="000852.SH", start_date="20181201", end_date="20260630")
idx = idx.sort_values("trade_date")
cal = idx.trade_date.tolist()
month_ends = pd.Series(cal).groupby(pd.Series(cal).str[:6]).max().tolist()
dec_dates = [d for d in month_ends if "201812" <= d[:6] <= "202603"]   # 评审P1：连续覆盖，含2023-07~2024-05披露窗
db = pickle.load(open(B_PKL, "rb")) if os.path.exists(B_PKL) else {}
for d in dec_dates:
    if d in db:
        continue
    try:
        x = P._ts_query("daily_basic", trade_date=d, fields="ts_code,pe_ttm,total_mv,circ_mv")
        db[d] = x if x is not None else pd.DataFrame()
        log("daily_basic", d, len(db[d]))
    except Exception as e:
        log("daily_basic失败", d, e)
    time.sleep(0.15)
pickle.dump(db, open(B_PKL, "wb"))
log("决策日横截面完成:", len(db), "个日期")

# ── 4. 指数（价格+全收益基准）──
out = {"000852.SH": idx}
for tc in ("H00852.CSI", "932000.CSI"):
    try:
        z = P._ts_query("index_daily", ts_code=tc, start_date="20181201", end_date="20260630")
        if z is not None and len(z):
            out[tc] = z.sort_values("trade_date")
            log(tc, "可得:", len(z), "行, 最早", z.trade_date.min())
        else:
            log(tc, "不可得")
    except Exception as e:
        log(tc, "拉取异常:", e)
    time.sleep(0.2)
pickle.dump(out, open(I_PKL, "wb"))
log("全部收集完成 ✅")
