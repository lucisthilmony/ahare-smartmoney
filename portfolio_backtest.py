# -*- coding: utf-8 -*-
"""
A股短线波段策略 · 组合级回测（事件驱动，按手册规则真实执行）
与 backtest.py 的区别：backtest.py 是"逐笔信号分析"（每个候选都独立模拟，回答"信号有没有预测力"）；
本脚本回答"**按手册的资金/仓位/熔断规则实际去执行，账户曲线长什么样**"。

执行的手册规则（全部对齐《零基础操作手册 v6.1》）：
  §3  市场状态档位 → 总仓位上限 60/40/20/0%，板块状态门
  §4  候选池 + 实盘 config 的主线门（TOP_SECTORS/CORE_THEMES）
  §5  次日尾盘(≈收盘)入场；高开放弃；每天最多新开 2 笔
  §6  R=总资金×0.75% 倒推股数；单票上限 20%/12%；20cm合计≤30%；同行业(主题)合计≤30%；
      最多同时持有 3 只；回撤8% → R减半+档位降一档；回撤15% → 清仓停做20交易日
  §7  2R卖半(盘中触价)；剩余跌破MA10次日开盘卖；止损收盘确认次日开盘卖；15日时间止损收盘卖
  T+1：入场当日不卖
成本：佣金万2.5(最低5元/笔)、印花税卖出0.05%、滑点 主板0.1%/20cm 0.2%（每边）
用法：./.venv/bin/python portfolio_backtest.py [START_YYYYMMDD] [END_YYYYMMDD]
产出：02_回测报告/portfolio_report_<tag>.md / portfolio_trades_<tag>.csv / portfolio_equity_<tag>.png
"""
import os, sys, time, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import backtest as B

# ===== 组合参数（全部来自手册，不新调参）=====
INIT_CAPITAL = float(getattr(C, "DEFAULT_CAPITAL", 500000))
RISK_PCT     = float(getattr(C, "RISK_PCT", 0.0075))
MAX_POS      = 3          # 最多同时持有（手册§5：2–3只，取3）
MAX_OPEN_DAY = 2          # 每天最多新开（手册§5：1–2笔，取2）
HOLD_MAX     = 15         # 时间止损（v5.2 采纳：15日/破MA10）
TRAIL        = "ma10"
CAP_20CM     = 0.30       # 创业板+科创板合计敞口上限（§6）
CAP_THEME    = 0.30       # 同行业(主题)合计敞口上限（§6.9：25–30%，取30%）
DD_HALF      = -0.08      # 回撤8%：R减半+档位降一档
DD_KILL      = -0.15      # 回撤15%：清仓停做
HALT_DAYS    = 20         # 熔断后停做的交易日数（手册"回模拟复盘"，取20日后重启并重置高点）
SLIP         = {"main": 0.001, "chinext": 0.002, "star": 0.002}   # 每边滑点
COMM_RATE, COMM_MIN, STAMP = 0.00025, 5.0, 0.0005
TIER_DOWN    = {60: 40, 40: 20, 20: 0, 0: 0}

# ===== 实验B · ETF底仓层（核心-卫星）=====
# 思路：状态门(样本外唯一被验证有效的部件)管一个指数/主线ETF底仓吃beta；个股波段层(卫星)完全不动。
# base_mode: "none"=无底仓(原版) / "hs300"=固定沪深300 / "strong3"=三指数(沪深300/创业板指/科创50)每5日按20日动量择强
#            / "strongsec"=实验C：10个中证全指一级行业指数择强（机制/参数与 strong3 完全一致，仅换池，预注册见 experiment_sector_base.md）
BASE_TARGET  = {60: 0.50, 40: 0.30, 20: 0.10, 0: 0.0}   # 档位→底仓目标权重（预注册，不扫参）
ETF_COST     = 0.0003     # ETF 每边成本(佣金+滑点)
REBAL_BAND   = 0.05       # 目标与实际偏离超过总资产5%才再平衡（防日常抖动）
IDX_CN       = {"hs300": "沪深300", "gem": "创业板指", "star": "科创50"}
SEC_IDX      = {"000986.SH": "能源", "000987.SH": "材料", "000988.SH": "工业",
                "000989.SH": "可选消费", "000990.SH": "主要消费", "000991.SH": "医药卫生",
                "000992.SH": "金融地产", "000993.SH": "信息技术", "000994.SH": "电信业务",
                "000995.SH": "公用事业"}   # 中证全指一级行业（实验C择强池，预注册不改）
# 实验D · 红利防守腿（预注册见 experiment_div_base.md）：base_mode="strong3div"
# 进攻腿=strong3 原样；防守腿=中证红利全收益，目标权重 = DIV_TOTAL − 进攻腿目标（60档0/40档20%/20档40%/0档50%）
DIV_IDX      = "H00922.CSI"   # 中证红利全收益（含股息再投资；实盘对应 515080/510880，费差未建模）
DIV_TOTAL    = 0.50           # 底仓两腿合计恒为50%（=最高档进攻目标，单一公式无新参数）

log = B.log

def _fees(mv, side):
    f = max(COMM_MIN, mv * COMM_RATE)
    if side == "sell":
        f += mv * STAMP
    return f

def fetch_idx_series(codes, start, end, cache_name):
    """拉一组指数日线（含160自然日预热保证窗口首日有ret20）。小缓存避免重复拉。codes: {ts_code: 名称}"""
    import pickle
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), f".{cache_name}_cache_{start}_{end}.pkl")
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return pickle.load(f)
    start_pull = (dt.datetime.strptime(start, "%Y%m%d").date() - dt.timedelta(days=160)).strftime("%Y%m%d")
    out = {}
    for code, nm in codes.items():
        di = P._ts_query("index_daily", ts_code=code, fields="ts_code,trade_date,close",
                         start_date=start_pull, end_date=end)
        di = di.sort_values("trade_date").reset_index(drop=True)
        out[code] = di
        log(f"  指数 {nm} {code}：{len(di)} 天")
        time.sleep(0.15)
    P.assert_cache_write_ok()   # pandas版本护栏
    with open(cache, "wb") as f:
        pickle.dump(out, f)
    return out

def fetch_sector_idx(start, end):
    return fetch_idx_series(SEC_IDX, start, end, "sector_idx")

def run_portfolio(start, end, tag, base_mode="none", no_satellite=False):
    data = B.fetch_all(start, end)
    P_ = B.prepare(data)
    frames = P_["frames"]
    win_dates = data["win_dates"]
    date_pos = B.build_date_pos(frames)

    # 指数序列（底仓用；含预热期，窗口首日即有 ret20）
    idxs = {}
    if base_mode == "strongsec":     # 实验C：择强池换成10个行业指数（机制不变）
        for code, di in fetch_sector_idx(start, end).items():
            r20 = di["close"] / di["close"].shift(20) - 1
            idxs[code] = dict(close=dict(zip(di["trade_date"], di["close"])),
                              ret20=dict(zip(di["trade_date"], r20)))
        base_inst = None     # 行业池无自然缺省，首个可执行日按前日动量择强（预注册）
    else:
        for nm in ("hs300", "gem", "star"):
            di = data["idx"][nm].sort_values("trade_date")
            r20 = di["close"] / di["close"].shift(20) - 1
            idxs[nm] = dict(close=dict(zip(di["trade_date"], di["close"])),
                            ret20=dict(zip(di["trade_date"], r20)))
        base_inst = "hs300"  # 当前底仓标的
    base_units = 0.0         # 底仓"份额"（指数点位记账）
    base_switches = 0
    # 实验D · 防守腿（仅 strong3div）：中证红利全收益序列 + 独立份额记账
    div_close = {}
    div_units = 0.0
    if base_mode == "strong3div":
        di = fetch_idx_series({DIV_IDX: "中证红利全收益"}, start, end, "div_idx")[DIV_IDX]
        div_close = dict(zip(di["trade_date"], di["close"]))

    log("生成每日候选（与实盘同源 + 实盘主线门）…")
    cand_by_day = {}
    for d, state, cands in B.daily_candidates(data, P_, date_pos):
        live = [c for c in cands if B.live_gate(c)]
        live.sort(key=lambda c: c.get("score", 0), reverse=True)
        cand_by_day[d] = (state, live)

    # 沪深300 基准（同窗归一）
    hs = data["idx"]["hs300"]
    hs_close = dict(zip(hs["trade_date"], hs["close"]))

    cash = INIT_CAPITAL
    positions = {}      # ts -> dict
    pending = {}        # ts -> reason（明日开盘卖出）
    closed = []         # 已平仓交易
    curve = []          # 每日 dict(date, equity, exposure, n_pos, dd)
    peak = INIT_CAPITAL
    halted_until = -1   # 熔断解除的 win_dates 下标
    kill_events = []

    log(f"开始组合模拟 {len(win_dates)} 天…")
    for i, d in enumerate(win_dates):
        rows = {ts: date_pos[ts].get(d) for ts in list(positions)}

        # ---- 1) 开盘：执行昨日收盘确认的卖出信号 ----
        for ts, reason in list(pending.items()):
            j = rows.get(ts)
            if ts not in positions or j is None:
                continue  # 停牌顺延
            pos = positions[ts]; sub = frames[ts]
            px = float(sub["open"].iloc[j]) * (1 - SLIP[pos["board"]])
            mv = pos["shares"] * px
            cash += mv - _fees(mv, "sell")
            pos["pnl"] += pos["shares"] * (px - pos["entry"]) - _fees(mv, "sell")
            pos["shares"] = 0
            _close_trade(closed, pos, d, px, reason)
            del positions[ts]; del pending[ts]

        # ---- 2) 盘中：2R 触价卖半（T+1：入场当日不卖）----
        for ts, pos in positions.items():
            j = rows.get(ts)
            if j is None or j <= pos["entry_i"] or pos["half_done"]:
                continue
            sub = frames[ts]
            if float(sub["high"].iloc[j]) >= pos["target"]:
                half = (pos["shares"] // 2) // pos["lot"] * pos["lot"] if pos["lot"] > 1 else pos["shares"] // 2
                if half > 0:
                    mv = half * pos["target"]
                    cash += mv - _fees(mv, "sell")
                    pos["pnl"] += half * (pos["target"] - pos["entry"]) - _fees(mv, "sell")
                    pos["shares"] -= half
                    pos["half_done"] = True

        # ---- 3) 收盘：时间止损当日了结；止损/破MA10 → 明日开盘 ----
        for ts, pos in list(positions.items()):
            j = rows.get(ts)
            if j is None or j <= pos["entry_i"]:
                continue
            sub = frames[ts]; cl = float(sub["close"].iloc[j])
            hold = j - pos["entry_i"]
            if hold >= HOLD_MAX:                     # 手册：第15日收盘了结
                px = cl * (1 - SLIP[pos["board"]])
                mv = pos["shares"] * px
                cash += mv - _fees(mv, "sell")
                pos["pnl"] += pos["shares"] * (px - pos["entry"]) - _fees(mv, "sell")
                pos["shares"] = 0
                _close_trade(closed, pos, d, px, "2R后时间止损" if pos["half_done"] else "时间止损")
                del positions[ts]; pending.pop(ts, None)
                continue
            if cl < pos["stop"]:
                pending[ts] = "止损(已减半)" if pos["half_done"] else "止损"
            elif pos["half_done"]:
                mt = sub[TRAIL].iloc[j]
                if pd.notna(mt) and cl < float(mt):
                    pending[ts] = "跌破MA10"

        # ---- 3.5) 尾盘：底仓层先行调整（实验B；卫星层用剩余现金）----
        equity_prev = curve[-1]["equity"] if curve else INIT_CAPITAL
        dd_prev = equity_prev / peak - 1
        if base_mode != "none" and i > 0:
            st_c = cand_by_day.get(win_dates[i - 1])
            tier_cap = st_c[0]["cap"] if st_c else 0
            if dd_prev <= DD_HALF:
                tier_cap = TIER_DOWN.get(tier_cap, 0)
            tgt_w = 0.0 if i < halted_until else BASE_TARGET.get(tier_cap, 0.0)
            if base_mode in ("strong3", "strongsec", "strong3div") and (i % 5 == 0 or base_inst is None):  # 每5日按20日动量择强
                d_prev = win_dates[i - 1]
                mom = {nm: idxs[nm]["ret20"].get(d_prev) for nm in idxs}
                mom = {k: v for k, v in mom.items() if v is not None and not pd.isna(v)}
                if mom:
                    new_inst = max(mom, key=mom.get)
                    if new_inst != base_inst and base_units > 0:
                        px_old = idxs[base_inst]["close"].get(d)
                        if px_old:
                            mv_old = base_units * px_old
                            cash += mv_old - mv_old * ETF_COST
                            base_units = 0.0; base_switches += 1
                    base_inst = new_inst
            px = idxs[base_inst]["close"].get(d) if base_inst else None
            if px:
                base_mv = base_units * px
                tgt_mv = tgt_w * equity_prev
                if abs(tgt_mv - base_mv) > REBAL_BAND * equity_prev or (tgt_w == 0 and base_mv > 0):
                    delta = tgt_mv - base_mv
                    if delta > 0:
                        delta = min(delta, max(0.0, cash / (1 + ETF_COST)))
                    cash -= delta + abs(delta) * ETF_COST
                    base_units += delta / px
            if base_mode == "strong3div":     # 实验D · 防守腿：目标 = DIV_TOTAL − 进攻腿目标
                dpx = div_close.get(d)
                if dpx:
                    div_tgt = 0.0 if i < halted_until else max(0.0, DIV_TOTAL - BASE_TARGET.get(tier_cap, 0.0))
                    div_mv0 = div_units * dpx
                    dtgt_mv = div_tgt * equity_prev
                    if abs(dtgt_mv - div_mv0) > REBAL_BAND * equity_prev or (div_tgt == 0 and div_mv0 > 0):
                        delta = dtgt_mv - div_mv0
                        if delta > 0:
                            delta = min(delta, max(0.0, cash / (1 + ETF_COST)))
                        cash -= delta + abs(delta) * ETF_COST
                        div_units += delta / dpx

        # ---- 4) 尾盘：按昨日候选开新仓 ----
        if (not no_satellite) and i > 0 and i >= halted_until:
            state_c = cand_by_day.get(win_dates[i - 1])
            if state_c:
                state, cands = state_c
                cap_pct = state["cap"]
                r_eff = RISK_PCT
                if dd_prev <= DD_HALF:               # §6.7 回撤降档
                    cap_pct = TIER_DOWN.get(cap_pct, 0); r_eff *= 0.5
                opens = 0
                for cd in cands:
                    if opens >= MAX_OPEN_DAY or len(positions) >= MAX_POS or cap_pct <= 0:
                        break
                    ts = cd["ts"]
                    if ts in positions:
                        continue
                    j = date_pos[ts].get(d)
                    if j is None or j != cd["p"] + 1:
                        continue                      # 今天没交易/信号过期
                    sub = frames[ts]; board = cd["board"]
                    c0 = float(sub["close"].iloc[cd["p"]]); o1 = float(sub["open"].iloc[j])
                    if not c0 or o1 / c0 - 1 > C.BOARDS[board]["gap"]:
                        continue                      # 高开放弃
                    entry = float(sub["close"].iloc[j])
                    stop = float(cd["stop_price"])
                    risk = entry - stop
                    if risk <= 0:
                        continue
                    # 各路上限取最小
                    mv_now = _mark(positions, frames, rows, d)
                    lim = [equity_prev * r_eff / risk * entry,                     # 按风险
                           equity_prev * C.BOARDS[board]["cap"],                   # 单票上限
                           equity_prev * cap_pct / 100.0 - mv_now["total"],        # 总仓位上限
                           cash / (1 + SLIP[board] + COMM_RATE)]                   # 现金
                    if board in ("chinext", "star"):
                        lim.append(equity_prev * CAP_20CM - mv_now["cm20"])
                    lim.append(equity_prev * CAP_THEME - mv_now["ind"].get(cd["ind"], 0.0))
                    mv_max = max(0.0, min(lim))
                    lot = C.BOARDS[board]["lot"]
                    shares = int(mv_max / entry)
                    if board == "star":
                        shares = shares if shares >= lot else 0    # 科创板≥200股、可1股递增
                    else:
                        shares = shares // lot * lot
                    if shares <= 0:
                        continue
                    buy_px = entry * (1 + SLIP[board])
                    cost = shares * buy_px
                    cash -= cost + _fees(cost, "buy")
                    positions[ts] = dict(ts=ts, code=cd["code"], name=cd["name"], board=board,
                                         ind=cd["ind"], score=cd["score"], sec_rank=cd["sec_rank"],
                                         shares=shares, lot=lot, entry=buy_px, entry_raw=entry,
                                         stop=stop, target=entry + 2 * risk, half_done=False,
                                         entry_i=j, entry_date=d, entry_shares=shares,
                                         r_amt=equity_prev * r_eff, pnl=-_fees(cost, "buy"))
                    rows[ts] = j
                    opens += 1

        # ---- 5) 收盘结算 & 熔断 ----
        mv_now = _mark(positions, frames, rows, d)
        base_px = idxs[base_inst]["close"].get(d) if base_inst else None
        base_mv = base_units * base_px if base_px else base_units * 0.0
        div_px = div_close.get(d)
        div_mv = div_units * div_px if div_px else div_units * 0.0
        equity = cash + mv_now["total"] + base_mv + div_mv
        peak = max(peak, equity)
        dd = equity / peak - 1
        if dd <= DD_KILL and (positions or base_units > 0 or div_units > 0) and i + 1 < len(win_dates):   # §6.7 回撤15%：清仓停做
            for ts in positions:
                pending[ts] = "回撤15%熔断清仓"
            halted_until = i + 1 + HALT_DAYS     # 底仓在停做期内 tgt=0，次日收盘自动清
            kill_events.append(d)
            peak = equity        # 重启后以当前净值为新基准（手册未细化，取"复盘后重新出发"）
        curve.append(dict(date=d, equity=equity,
                          exposure=(mv_now["total"] + base_mv + div_mv) / equity if equity else 0,
                          base_w=base_mv / equity if equity else 0,
                          div_w=div_mv / equity if equity else 0,
                          base_inst=(SEC_IDX.get(base_inst, IDX_CN.get(base_inst, "")) if base_units > 0 else ""),
                          n_pos=len(positions), dd=dd, hs300=hs_close.get(d)))
        if i % 40 == 0:
            log(f"  …{i}/{len(win_dates)}  净值 {equity/INIT_CAPITAL:.3f}  持仓 {len(positions)}  累计平仓 {len(closed)}")

    # 期末强制平仓（按最后收盘）
    last_d = win_dates[-1]
    for ts, pos in list(positions.items()):
        sub = frames[ts]; j = date_pos[ts].get(last_d)
        px = float(sub["close"].iloc[j if j is not None else -1])
        _close_trade(closed, pos, last_d, px, "期末未平仓")
    meta = dict(base_mode=base_mode, base_switches=base_switches)
    return pd.DataFrame(curve), pd.DataFrame(closed), kill_events, win_dates, meta

def _mark(positions, frames, rows, d):
    """以当日收盘(停牌用最近价)估市值：总额 / 20cm合计 / 分行业。"""
    total, cm20, ind = 0.0, 0.0, {}
    for ts, pos in positions.items():
        j = rows.get(ts)
        sub = frames[ts]
        px = float(sub["close"].iloc[j]) if j is not None else float(pos.get("last_px", pos["entry"]))
        pos["last_px"] = px
        mv = pos["shares"] * px
        total += mv
        if pos["board"] in ("chinext", "star"):
            cm20 += mv
        ind[pos["ind"]] = ind.get(pos["ind"], 0.0) + mv
    return dict(total=total, cm20=cm20, ind=ind)

def _close_trade(closed, pos, d, px, reason):
    pnl = pos["pnl"] if not pos["shares"] else pos["pnl"] + pos["shares"] * (px - pos["entry"])
    cost0 = pos["entry_shares"] * pos["entry"]
    closed.append(dict(entry_date=pos["entry_date"], exit_date=d, code=pos["code"], name=pos["name"],
                       board=pos["board"], ind=pos["ind"], score=pos["score"], sec_rank=pos["sec_rank"],
                       shares=pos["entry_shares"], entry=round(pos["entry"], 3), exit=round(px, 3),
                       reason=reason, pnl=round(pnl, 1),
                       R=round(pnl / pos["r_amt"], 3) if pos["r_amt"] else None,
                       ret_pct=round(pnl / cost0 * 100, 2) if cost0 else None))

def report(curve, trades, kills, win_dates, tag, meta=None):
    meta = meta or {}
    eq = curve["equity"].values
    ret = pd.Series(eq).pct_change().dropna()
    total = eq[-1] / INIT_CAPITAL - 1
    years = len(curve) / 244.0
    cagr = (eq[-1] / INIT_CAPITAL) ** (1 / years) - 1 if years > 0 else 0
    peak = np.maximum.accumulate(eq); mdd = ((eq - peak) / peak).min()
    sharpe = ret.mean() / ret.std() * np.sqrt(244) if len(ret) > 2 and ret.std() else float("nan")
    hs = curve["hs300"].astype(float)
    hs_total = (hs.iloc[-1] / hs.dropna().iloc[0] - 1) if hs.notna().any() else float("nan")
    n = len(trades)
    win = (trades["pnl"] > 0).mean() if n else float("nan")
    avgR = trades["R"].mean() if n else float("nan")

    BASE = B.BASE
    trades.to_csv(os.path.join(BASE, f"portfolio_trades_{tag}.csv"), index=False, encoding="utf-8-sig")
    curve.to_csv(os.path.join(BASE, f"portfolio_curve_{tag}.csv"), index=False, encoding="utf-8-sig")

    L = [f"# 组合级回测报告（{tag}）——按手册规则真实执行\n"]
    L.append(f"- 生成：{dt.datetime.now():%Y-%m-%d %H:%M} ｜ 窗口：{win_dates[0]} ~ {win_dates[-1]}（{len(win_dates)} 交易日）")
    L.append(f"- 初始资金 {INIT_CAPITAL:,.0f} ｜ R={RISK_PCT*100:.2f}% ｜ 最多持 {MAX_POS} 只 ｜ 每日最多开 {MAX_OPEN_DAY} 笔 ｜ 出场 {HOLD_MAX}日/破MA10")
    L.append(f"- 执行约束：状态档位仓位上限、单票 20%/12%、20cm合计≤30%、同行业≤30%、T+1、"
             f"回撤8%→R减半+降档、回撤15%→清仓停做{HALT_DAYS}日")
    L.append(f"- 成本：佣金万2.5(最低5元) + 印花税卖出0.05% + 滑点每边 主板0.1%/20cm 0.2%\n")
    L.append("## 结果\n")
    L.append(f"| 指标 | 数值 |\n|---|---|")
    L.append(f"| 区间总收益 | **{total*100:.1f}%** |")
    L.append(f"| 年化(CAGR) | {cagr*100:.1f}% |")
    L.append(f"| 最大回撤 | **{mdd*100:.1f}%** |")
    L.append(f"| 日频Sharpe(年化) | {sharpe:.2f} |")
    L.append(f"| 同期沪深300 | {hs_total*100:.1f}% |")
    L.append(f"| 平仓笔数 | {n} |")
    L.append(f"| 胜率 | {win*100:.1f}% |")
    L.append(f"| 平均R | {avgR:.3f} |")
    L.append(f"| 平均敞口 | {curve['exposure'].mean()*100:.1f}% |")
    if meta.get("base_mode", "none") != "none":
        L.append(f"| 底仓模式 | {meta['base_mode']}（档位→目标 50/30/10/0%；换标的 {meta.get('base_switches',0)} 次） |")
        L.append(f"| 平均底仓权重 | {curve['base_w'].mean()*100:.1f}% |")
        if "div_w" in curve.columns and curve["div_w"].abs().max() > 0:
            L.append(f"| 平均防守腿(红利)权重 | {curve['div_w'].mean()*100:.1f}% |")
    L.append(f"| 空仓天数占比 | {(curve['n_pos']==0).mean()*100:.1f}% |")
    L.append(f"| 15%熔断触发 | {len(kills)} 次 {('：' + '、'.join(kills)) if kills else ''} |")
    if n:
        L.append("\n## 按出场原因\n\n| 原因 | 笔数 | 胜率 | 平均R | 平均收益% |\n|---|---|---|---|---|")
        for rsn, g in trades.groupby("reason"):
            L.append(f"| {rsn} | {len(g)} | {(g['pnl']>0).mean()*100:.0f}% | {g['R'].mean():.3f} | {g['ret_pct'].mean():.2f} |")
        trades["yr"] = trades["exit_date"].str[:4]
        L.append("\n## 按年份\n\n| 年 | 笔数 | 胜率 | 平均R |\n|---|---|---|---|")
        for y, g in trades.groupby("yr"):
            L.append(f"| {y} | {len(g)} | {(g['pnl']>0).mean()*100:.0f}% | {g['R'].mean():.3f} |")
        cy = curve.copy(); cy["yr"] = cy["date"].str[:4]
        L.append("\n## 净值分年\n\n| 年 | 年收益 | 年内最大回撤 |\n|---|---|---|")
        for y, g in cy.groupby("yr"):
            e = g["equity"].values
            pk = np.maximum.accumulate(e)
            L.append(f"| {y} | {(e[-1]/e[0]-1)*100:.1f}% | {((e-pk)/pk).min()*100:.1f}% |")
    L.append("""
## 与逐笔信号回测(backtest_report)的关系
- 逐笔报告回答"信号平均有没有优势"；本报告回答"**受资金/仓位/每日开仓数约束后，你实际能吃到多少**"。
- 每天只能开 1–2 笔、最多持 3 只 → 绝大多数候选被跳过，实际结果对"选哪几只"高度敏感（这里按评分从高到低取，与尾盘信号一致）。

## 诚实限制
- 熔断后 20 个交易日重启并以重启时净值为新高点基准——手册只说"清仓停做、复盘后恢复"，重启节奏是本脚本的假设。
- 2R 卖半按盘中触价成交（限价单假设）；停牌期间止损无法执行、顺延到复牌，与实盘一致但会放大个别损失。
- 入场按次日收盘近似 14:50 尾盘；未模拟盘中"三道门"复核与"同日大盘总闸"（后者是盘中人工规则，无分钟数据）。
- 本报告不构成投资建议。
""")
    png = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                               gridspec_kw={"height_ratios": [3, 1]})
        x = np.arange(len(curve))
        ax[0].plot(x, (curve["equity"] / INIT_CAPITAL - 1) * 100, label="Strategy")
        if curve["hs300"].notna().any():
            base = curve["hs300"].dropna().iloc[0]
            ax[0].plot(x, (curve["hs300"] / base - 1) * 100, alpha=.6, label="HS300")
        ax[0].set_ylabel("Cumulative %"); ax[0].legend(); ax[0].grid(alpha=.3)
        ax[0].set_title(f"Portfolio backtest ({tag}) — rules as handbook")
        ax[1].fill_between(x, curve["dd"] * 100, 0, color="tab:red", alpha=.4)
        ax[1].set_ylabel("DD %"); ax[1].grid(alpha=.3)
        plt.tight_layout()
        png = os.path.join(BASE, f"portfolio_equity_{tag}.png"); plt.savefig(png, dpi=110)
        L.append(f"\n资金曲线图：`portfolio_equity_{tag}.png`")
    except Exception as e:
        log(f"画图跳过：{str(e)[:60]}")
    open(os.path.join(BASE, f"portfolio_report_{tag}.md"), "w", encoding="utf-8").write("\n".join(L))
    log(f"组合级报告已生成：portfolio_report_{tag}.md")

if __name__ == "__main__":
    t0 = time.time()
    plain = [a for a in sys.argv[1:] if not a.startswith("--")]
    base_mode = "none"; no_sat = False
    for a in sys.argv[1:]:
        if a.startswith("--base="):
            base_mode = a.split("=", 1)[1]
        if a == "--nosat":
            no_sat = True
    assert base_mode in ("none", "hs300", "strong3", "strongsec", "strong3div"), f"未知 base_mode: {base_mode}"
    start, end, tag = B.window_args(plain)
    if base_mode != "none":
        tag = f"{tag}_base-{base_mode}"
    if no_sat:
        tag = f"{tag}_nosat"
    log(f"组合级回测窗口 {start} ~ {end}（tag={tag}，底仓={base_mode}，卫星={'关' if no_sat else '开'}）")
    curve, trades, kills, wd, meta = run_portfolio(start, end, tag, base_mode=base_mode, no_satellite=no_sat)
    report(curve, trades, kills, wd, tag, meta)
    log(f"全部完成，用时 {time.time()-t0:.0f}s")
