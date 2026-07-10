# -*- coding: utf-8 -*-
"""
影子交割执行器（v6.4 P2 · 2026-07-10）——每交易日18:55 cron。

目的（外部审查P2）：失效判据不能靠实盘笔数（太慢且停做后死锁）。本脚本每日**机械模拟**
"系统规则本来会做的卫星交易"，形成两条影子流：
  A流 = A门执行卡（top-1修复型A候选）  C流 = classic执行卡（top-1候选，不加A门）
规则与回测/实盘同源（策略规格.py）：次日收盘入场（高开放弃）、15日/MA10/2R卖半/收盘止损次日开盘出、
全成本、每流最多同时3只/每日开1只。影子流不依赖用户是否真的下单，停做期间照常运行→失效判据可自动恢复。

同时逐日记录四影子账户归因数据：现金/纯底仓/底仓+A流/底仓+C流（分量分离记账，评估期合成）。

输出：影子交割.csv（平仓流水，失效判据v2的慢判据数据源）
      前向影子净值.csv（日频：档位/底仓标的/底仓权重/底仓日收益/两流累计R）
状态：.shadow_state.json（持仓与待成交队列；损坏可删除重建，仅损失在途仓）
"""
import os, sys, json, time, datetime as dt
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import 策略规格 as SPEC

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, ".shadow_state.json")
TRADES = os.path.join(HERE, "影子交割.csv")
NAV = os.path.join(HERE, "前向影子净值.csv")
HOLD_MAX, MAX_POS = 15, SPEC.MAX_POS

def log(m): print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"A": {"open": [], "pending_entry": None, "pending_exit": []},
                "C": {"open": [], "pending_entry": None, "pending_exit": []}, "last_run": None}

def save_state(st):
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)

def daily_bars(code, start):
    ts = code + (".SH" if code.startswith("6") else ".SZ")
    df = P._ts_query("daily", ts_code=ts, start_date=start,
                     fields="trade_date,open,high,low,close")
    time.sleep(0.12)
    return df.sort_values("trade_date").reset_index(drop=True) if df is not None else None

def append_trade(row):
    df = pd.DataFrame([row])
    if os.path.exists(TRADES):
        df.to_csv(TRADES, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(TRADES, index=False, encoding="utf-8-sig")

def cost_frac(board, date):
    return 2 * SPEC.SLIP.get(board, 0.001) + 2 * SPEC.COMM_RATE + SPEC.stamp_rate(date)

def process_stream(stream, st, today, cands, can_open):
    """更新一条影子流：成交昨日排队入场 → 更新持仓出场 → 排队新入场。"""
    s = st[stream]
    # 1) 昨日排队的入场：今日按当日收盘成交（高开放弃）
    pe = s.get("pending_entry")
    if pe:
        bars = daily_bars(pe["code"], pe["decide_date"])
        s["pending_entry"] = None
        if bars is not None and len(bars) >= 2:
            r0, r1 = bars.iloc[0], bars.iloc[1]
            gap = C.BOARDS[pe["board"]]["gap"]
            if r0["close"] and r1["open"] / r0["close"] - 1 <= gap:
                entry = float(r1["close"])
                stop = float(pe["stop_price"])
                if entry > stop:
                    s["open"].append(dict(code=pe["code"], name=pe["name"], board=pe["board"],
                                          entry=entry, stop=stop, target=entry + 2 * (entry - stop),
                                          entry_date=str(r1["trade_date"]), half=False, hold=0,
                                          pnl_r=0.0))
                    log(f"  [{stream}] 影子入场 {pe['name']} @{entry:.2f}")
    # 2) 持仓出场（与回测simulate同规则；pending_exit=次日开盘卖）
    for pos in list(s["open"]):
        bars = daily_bars(pos["code"], pos["entry_date"])
        if bars is None or not len(bars):
            continue
        bars = bars[bars["trade_date"] > pos["entry_date"]]
        # 从上次处理点续算：用hold记录已处理天数
        new = bars.iloc[pos["hold"]:]
        for _, b in new.iterrows():
            pos["hold"] += 1
            d, hi, cl, op = str(b["trade_date"]), float(b["high"]), float(b["close"]), float(b["open"])
            if pos.get("exit_next_open"):          # 昨日收盘确认，今日开盘出
                _close(stream, pos, d, op, pos["exit_next_open"]); s["open"].remove(pos); break
            if not pos["half"] and hi >= pos["target"]:
                pos["half"] = True                  # 2R卖半（触价）
            if cl < pos["stop"]:
                pos["exit_next_open"] = "止损"; continue
            if pos["half"]:
                ma10 = _ma10(pos["code"], d)
                if ma10 and cl < ma10:
                    pos["exit_next_open"] = "跌破MA10"; continue
            if pos["hold"] >= HOLD_MAX:
                _close(stream, pos, d, cl, "时间止损"); s["open"].remove(pos); break
    # 3) 新入场排队（每日最多1、最多持3、可开仓日、该流有候选且未持有）
    if can_open and len(s["open"]) < MAX_POS and s.get("pending_entry") is None:
        pool = [c for c in cands if SPEC.satellite_gate(c, "codexA") is True] if stream == "A" else cands
        pool = [c for c in pool if c.get("code") not in {p["code"] for p in s["open"]}]
        if pool:
            c0 = max(pool, key=lambda c: c.get("score", 0))
            s["pending_entry"] = dict(code=c0["code"], name=c0.get("name", ""), board=c0.get("board", "main"),
                                      stop_price=c0.get("stop_price"), decide_date=today)
            log(f"  [{stream}] 排队入场 {c0.get('name')}（明日收盘成交）")

def _ma10(code, upto):
    bars = daily_bars(code, (dt.datetime.strptime(upto, "%Y%m%d") - dt.timedelta(days=30)).strftime("%Y%m%d"))
    if bars is None:
        return None
    bars = bars[bars["trade_date"] <= upto]
    return float(bars["close"].tail(10).mean()) if len(bars) >= 10 else None

def _close(stream, pos, date, px, reason):
    cost = cost_frac(pos["board"], date)
    risk = pos["entry"] - pos["stop"]
    if pos["half"]:
        gross = 0.5 * (pos["target"] - pos["entry"]) + 0.5 * (px - pos["entry"])
    else:
        gross = px - pos["entry"]
    r = (gross - pos["entry"] * cost) / risk if risk > 0 else 0.0
    append_trade({"流": stream, "开仓日": pos["entry_date"], "代码": pos["code"], "名称": pos["name"],
                  "入场": round(pos["entry"], 2), "止损": round(pos["stop"], 2),
                  "平仓日": date, "平仓价": round(px, 2), "原因": reason, "R": round(r, 3)})
    log(f"  [{stream}] 影子平仓 {pos['name']} {reason} R={r:+.2f}")

def main():
    today = dt.date.today().strftime("%Y%m%d")
    if today not in set(P._recent_trade_dates(8)):
        log("非交易日，跳过。"); return
    try:
        txt = open(C.DATA_JS_PATH, encoding="utf-8").read()
        d = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
    except Exception as e:
        log(f"读data.js失败：{e}"); return
    if (d.get("data_date") or "").replace("-", "") != today:
        log("data.js非当日数据（18:30刷新未跑？），跳过以防错位。"); return
    st = load_state()
    if st.get("last_run") == today:
        log("今日已运行过，跳过（幂等）。"); return
    state = d.get("state") or {}
    cands = d.get("candidates") or []
    for stream in ("A", "C"):
        process_stream(stream, st, today, cands, bool(state.get("can_open")))
    # 四影子账户 · 日频分量记账
    base = d.get("base") or {}
    row = dict(date=today, tier=state.get("tier"), cap=state.get("cap"),
               base_inst=base.get("etf"), base_w=base.get("weight"),
               A_open=len(st["A"]["open"]), C_open=len(st["C"]["open"]))
    pd.DataFrame([row]).to_csv(NAV, mode="a" if os.path.exists(NAV) else "w",
                               header=not os.path.exists(NAV), index=False, encoding="utf-8-sig")
    st["last_run"] = today
    save_state(st)
    log(f"影子执行完成：A流持仓{len(st['A']['open'])} C流持仓{len(st['C']['open'])}")

if __name__ == "__main__":
    main()
