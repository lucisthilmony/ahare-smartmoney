# -*- coding: utf-8 -*-
"""
前向观察 · 席位负面筛选 + Codex格子标志（记录不执行，2026-07-03 ~ 2026-10-03）

来源：席位性格研究Q3（观察性）——买方全为营业部（无"机构专用"）的上榜票，两窗口5日超额系统性为负。
本脚本每日盘后把**当天全部候选**（data.js）与近5个交易日龙虎榜比对，逐票记录标志位——
**只写CSV，不改变候选、不出现在尾盘信号里**，保证前向检验不被人为行为污染。

3个月后（2026-10-03）评估（协议见 02_回测报告/前向观察-协议-2026-07-03.md）：
  比较 flag_纯营业部=Y vs N 两组候选的5日前向收益差；方向与观察研究一致且样本足够 → 才升级为§4减分项。

输出：数据助手/前向观察_席位筛选.csv（逐日追加，含全部候选=对照组内建）
用法：每日盘后 cron 自动跑；手动补跑直接运行即可（同日重复运行自动去重）。
"""
import os, sys, json, time, datetime as dt
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P

CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "前向观察_席位筛选.csv")
LOOKBACK = 5   # 近5个交易日上过榜才算

def _n(v, d=0.0):
    try:
        return float(v) if v is not None else d
    except Exception:
        return d

def codex_flags(c):
    """Codex Alpha两个格子的标志（2026-07-03复核：A半真半假、B判为幸运格子；均只记录不执行，2026-10-03评估）。
    需要 pipeline 候选带 prior60/amt20_yi（2026-07-03起有）；缺字段返回空串。"""
    if c.get("prior60") is None or c.get("amt20_yi") is None:
        return "", ""
    sec, rs, prior, amt, score = (_n(c.get("sec_rank"), 999), _n(c.get("rs")),
                                  _n(c.get("prior60")), _n(c.get("amt20_yi")), _n(c.get("score")))
    a = "Y" if (sec <= 5 and rs > 0 and prior < 0 and 2 <= amt < 5) else "N"
    b = "Y" if (score >= 75 and sec <= 10 and 60 <= prior < 100 and amt >= 5) else "N"
    return a, b

def log(m): print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)

def recent_lhb(dates):
    """近N个交易日的龙虎榜：返回 {ts_code: {"dates": [...], "pure_yzb": bool}}（pure=买方净买>0席位中无'机构专用'）"""
    out = {}
    for d in dates:
        try:
            ti = P._ts_query("top_inst", trade_date=d, fields="trade_date,ts_code,exalter,side,net_buy")
        except Exception as e:
            log(f"  {d} top_inst失败: {str(e)[:50]}"); continue
        time.sleep(0.12)
        if ti is None or not len(ti):
            continue
        buys = ti[(ti["side"].astype(str) == "0") & (ti["net_buy"] > 0)]
        for ts_code, g in buys.groupby("ts_code"):
            rec = out.setdefault(ts_code, {"dates": [], "has_inst": False})
            rec["dates"].append(d)
            if g["exalter"].astype(str).str.contains("机构专用").any():
                rec["has_inst"] = True
    return out

def main():
    today = dt.date.today().strftime("%Y%m%d")
    tds = P._recent_trade_dates(LOOKBACK + 2)
    if today not in tds:
        log("非交易日，跳过。"); return
    try:
        txt = open(C.DATA_JS_PATH, encoding="utf-8").read()
        d = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
    except Exception as e:
        log(f"读候选池失败：{e}"); return
    cands = d.get("candidates") or []
    data_date = (d.get("data_date") or d.get("date") or "").replace("-", "") or today
    if not cands:
        log("候选池为空，今日无记录。"); return
    lhb = recent_lhb([x for x in tds if x <= data_date][-LOOKBACK:])
    rows = []
    for c in cands:
        code = c.get("code", "")
        ts = code + (".SH" if code.startswith("6") else ".SZ")
        hit = lhb.get(ts)
        fa, fb = codex_flags(c)
        rows.append(dict(记录日期=data_date, 代码=code, 名称=c.get("name", ""),
                         评分=c.get("score", ""), 主线排名=c.get("sec_rank", ""),
                         近5日上榜="Y" if hit else "N",
                         纯营业部=("Y" if (hit and not hit["has_inst"]) else ("N" if hit else "")),
                         上榜日=("|".join(hit["dates"]) if hit else ""),
                         修复型A=fa, 中继型B=fb))
    new = pd.DataFrame(rows)
    if os.path.exists(CSV):
        old = pd.read_csv(CSV, dtype=str)
        old = old[~((old["记录日期"] == str(data_date)))]   # 同日重跑覆盖
        new = pd.concat([old, new.astype(str)], ignore_index=True)
    new.to_csv(CSV, index=False, encoding="utf-8-sig")
    n_hit = sum(1 for r in rows if r["近5日上榜"] == "Y")
    n_pure = sum(1 for r in rows if r["纯营业部"] == "Y")
    log(f"已记录 {len(rows)} 个候选（上榜{n_hit}、纯营业部{n_pure}）→ {os.path.basename(CSV)}")

if __name__ == "__main__":
    main()
