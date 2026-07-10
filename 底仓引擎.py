# -*- coding: utf-8 -*-
"""
底仓引擎（strong3 · 实盘提醒层，2026-07-03）
严格复刻组合级回测的底仓规则（portfolio_backtest.py 实验B，双窗口唯一通过的进攻部件）：
  每5个交易日一个"择强检查点"，按检查点前一交易日的近20日涨幅，持有三大指数中最强者对应的ETF；
  目标权重 = 前一日档位 → 进攻50% / 标准30% / 防守10% / 空仓0%；偏离超总资产5%才调仓。

无状态设计：检查点相位从固定锚点(ANCHOR=样本内回测窗口首日)按交易日计数 mod 5 推出，
任何一天独立运行都得到同一答案——不依赖历史运行记录，漏跑/重跑均无影响。

被 尾盘信号.py（14:40，附操作提醒）与 pipeline._assemble（18:30，写入data.js供HTML显示）调用。
单独运行可查看当前推荐：./.venv/bin/python 底仓引擎.py
"""
import os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline as P
import 策略规格 as SPEC   # v6.4：锚点/权重表同源

CODES = [("000300.SH", "沪深300", "510300"),
         ("399006.SZ", "创业板指", "159915"),
         ("000688.SH", "科创50", "588000")]
ANCHOR = SPEC.ANCHOR          # 相位锚点（同源自策略规格.py）
BASE_TARGET = SPEC.BASE_TARGET  # 档位上限% → 底仓目标权重%（同源）

def _ret20_at(di, dref):
    """di: 单指数日线(升序)；dref: 参考日。返回 dref 收盘的近20日涨幅，数据不足返回 None。"""
    sub = di[di["trade_date"] <= dref]
    if len(sub) < 21:
        return None
    c = sub["close"].values
    return float(c[-1] / c[-21] - 1)

def recommend(cap=None):
    """返回 dict(etf, name, code, ret20, weight, tier_cap, is_cp_today, changed, prev_name, next_cp)；失败返回 None。"""
    today = dt.date.today().strftime("%Y%m%d")
    cal = P._ts_query("trade_cal", exchange="SSE", start_date=ANCHOR, end_date=today, is_open="1")
    days = sorted(cal["cal_date"].tolist())
    if len(days) < 30:
        return None
    i = len(days) - 1                    # 最近交易日下标（含今天，若今天是交易日）
    cp = i - (i % 5)                     # 当前生效的检查点
    dref = days[cp - 1] if cp >= 1 else days[0]          # 本检查点的动量参考日
    dref_prev = days[cp - 6] if cp >= 6 else None        # 上一检查点的参考日（判断是否换仓）
    start_pull = (dt.datetime.strptime(dref_prev or dref, "%Y%m%d").date()
                  - dt.timedelta(days=70)).strftime("%Y%m%d")
    best, best_r, prev_best = None, None, None
    for code, nm, etf in CODES:
        di = P._ts_query("index_daily", ts_code=code, fields="trade_date,close",
                         start_date=start_pull, end_date=dref).sort_values("trade_date")
        r = _ret20_at(di, dref)
        if r is not None and (best_r is None or r > best_r):
            best, best_r = (code, nm, etf), r
        if dref_prev:
            rp = _ret20_at(di, dref_prev)
            if rp is not None and (prev_best is None or rp > prev_best[1]):
                prev_best = ((code, nm, etf), rp)
    if best is None:
        return None
    nxt = None                            # 下一个检查点日期（供提示；日历不够长就留空）
    cal2 = P._ts_query("trade_cal", exchange="SSE", start_date=today,
                       end_date=(dt.date.today() + dt.timedelta(days=15)).strftime("%Y%m%d"), is_open="1")
    fut = [d for d in sorted(cal2["cal_date"].tolist()) if d > days[-1]]   # 严格今天之后（修正2026-07-06 off-by-one）
    need = cp + 5 - i                     # 距下一检查点还差几个交易日
    if 0 < need <= len(fut):
        nxt = fut[need - 1]
    code, nm, etf = best
    out = dict(code=code, name=nm, etf=etf, ret20=round(best_r * 100, 1),
               is_cp_today=(i == cp),
               changed=(prev_best is not None and prev_best[0][0] != code and i == cp),
               prev_name=(prev_best[0][1] if prev_best else None),
               prev_etf=(prev_best[0][2] if prev_best else None),
               next_cp=nxt, tier_cap=cap,
               weight=(BASE_TARGET.get(cap) if cap is not None else None))
    return out

_LASTW = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".base_last_weight.json")

def _weight_alert(weight):
    """目标权重较上次显示变化≥5pp → 返回醒目提醒（展示辅助；读写失败静默）。"""
    import json as _json
    prev = None
    try:
        prev = _json.load(open(_LASTW)).get("weight")
    except Exception:
        pass
    if weight is None:      # 手动无参运行不覆盖状态（否则会吞掉次日的调仓提醒）
        return ""
    try:
        _json.dump({"weight": weight, "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}, open(_LASTW, "w"))
    except Exception:
        pass
    if prev is None or weight is None or abs(weight - prev) < 5:
        return ""
    act = "买入加仓" if weight > prev else "卖出减仓"
    return f"\n　⚠️ **今日调仓**：目标权重 {prev}% → {weight}%（尾盘{act}至目标）"

def line(cap=None):
    """一行人话，供尾盘信号/日志用。"""
    try:
        r = recommend(cap)
    except Exception as e:
        return f"🏦 底仓(strong3)：计算失败（{str(e)[:40]}），按上次持仓不动"
    if not r:
        return "🏦 底仓(strong3)：数据不足，按上次持仓不动"
    w = f"目标权重 **{r['weight']}%**" if r["weight"] is not None else "权重看档位(进攻50/标准30/防守10/空仓0%)"
    s = f"🏦 底仓(strong3)：持有 **{r['name']}ETF {r['etf']}**（20日动量{r['ret20']:+.1f}%）｜ {w}"
    s += _weight_alert(r["weight"])
    if r["changed"]:
        s += f"\n　⚠️ **今日换仓日**：尾盘卖 {r['prev_name']}ETF {r['prev_etf']} → 买 {r['name']}ETF {r['etf']}"
    elif r["is_cp_today"]:
        s += "｜ 今日择强检查：标的不变"
    elif r["next_cp"]:
        s += f"｜ 下次择强 {r['next_cp'][4:6]}-{r['next_cp'][6:]}"
    s += "\n　（偏离目标超总资产5%才调仓；账户回撤>8%自行降一档、>15%清仓停做）"
    return s

if __name__ == "__main__":
    print(line())
