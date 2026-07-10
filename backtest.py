# -*- coding: utf-8 -*-
"""
A股短线波段策略 · 回测引擎
设计原则：诚实、抗过拟合、与实盘工具同源（复用 pipeline 的 筛选/打分/市场状态 函数）。
做两件事：
  ① 信号验证：每天的候选按 评分/RS 分档，看未来 1/3/5/10 日真实收益与胜率（验证打分有没有预测力）。
  ② 机械策略模拟：按手册出场规则(止损/2R卖半/跌破MA5/8日时间止损) + 手续费印花税滑点，算每笔 R 倍数与资金曲线。
数据：Tushare https 直连（复用 pipeline._ts_query）。按 trade_date 拉全市场，天然包含当时在交易的票（含后来退市的），降低幸存者偏差。
产出：backtest_report.md（报告）、backtest_trades.csv（逐笔）、backtest_equity.png（资金曲线）。
注意：日线近似 14:50 尾盘买点；成本与滑点为假设值；主线行业指数为合成近似。结论看方向与分档单调性，不要当精确收益承诺。
"""
import os, sys, time, pickle, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P

# ===== 回测参数 =====
MONTHS_BACK = 24          # 回测窗口（月），未指定起止日期时用
LOOKBACK_DAYS = 75        # 指标预热交易日数
TOP_N_EQUITY = 3          # 资金曲线：每天最多取分数最高的 N 只
COST_RATE = 0.004         # 单笔往返成本(佣金+印花税+滑点)≈0.4%，计入每笔
HOLD_MAX = 8             # 最大持有交易日（时间止损）
BASE = os.path.join(C.BASE_DIR, "02_回测报告"); os.makedirs(BASE, exist_ok=True)  # 报告统一输出到此文件夹

def log(m): print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)

def window_args(argv=None):
    """命令行窗口参数：backtest.py [START_YYYYMMDD] [END_YYYYMMDD]。缺省=近 MONTHS_BACK 个月。"""
    argv = sys.argv[1:] if argv is None else argv
    today = dt.date.today()
    end = argv[1] if len(argv) >= 2 else today.strftime("%Y%m%d")
    start = argv[0] if len(argv) >= 1 else (today - dt.timedelta(days=int(MONTHS_BACK * 30.5))).strftime("%Y%m%d")
    tag = f"qfq_{start[:4]}-{end[:4]}"
    return start, end, tag

def cache_path(start, end):
    return os.path.join(C.BASE_DIR, "数据助手", f".backtest_cache_qfq_{start}_{end}.pkl")

# ---------------- 拉数据（带缓存；v2：前复权）----------------
def fetch_all(start_win, end):
    cache = cache_path(start_win, end)
    if os.path.exists(cache):
        log(f"发现缓存 {os.path.basename(cache)}，直接读取（删除可重新拉数据）")
        with open(cache, "rb") as f:
            data = pickle.load(f)
        # 缓存里存的 board 列是当时的映射；board_of 修正后（2026-07-02 补002/003）按现行规则重算，缓存无需重拉
        data["basic"]["board"] = data["basic"]["symbol"].apply(P.board_of)
        return data
    start_pull = (dt.datetime.strptime(start_win, "%Y%m%d").date() - dt.timedelta(days=160)).strftime("%Y%m%d")
    log("拉交易日历…")
    cal = P._ts_query("trade_cal", exchange="SSE", start_date=start_pull, end_date=end, is_open="1")
    dates = sorted(cal["cal_date"].tolist())
    win_dates = [d for d in dates if d >= start_win]
    pull_dates = dates[-(len(win_dates) + LOOKBACK_DAYS):]
    log(f"窗口交易日 {len(win_dates)} 天；含预热共拉 {len(pull_dates)} 天的全市场日线…")
    # 股票元数据（含退市，降低幸存者偏差）
    metas = []
    for st in ("L", "D", "P"):
        try:
            metas.append(P._ts_query("stock_basic", fields="ts_code,symbol,name,industry,market,list_date", list_status=st))
        except Exception:
            pass
    basic = pd.concat(metas, ignore_index=True).drop_duplicates("ts_code")
    basic["board"] = basic["symbol"].apply(P.board_of)
    frames = []
    for i, d in enumerate(pull_dates):
        try:
            df = P._ts_query("daily", fields="ts_code,trade_date,open,high,low,close,vol,amount", trade_date=d)
            if df is not None and len(df):
                frames.append(df)
        except Exception as e:
            log(f"  {d} 拉取失败: {str(e)[:60]}")
        if i % 40 == 0:
            log(f"  …{i}/{len(pull_dates)}")
        time.sleep(0.10)
    panel = pd.concat(frames, ignore_index=True)
    # 前复权（锚定窗口内各股最新一天）：不复权价会把除权除息当成真实暴跌，污染指标与每笔收益。
    # 价格上下限过滤(4–80元)要用【当时真实价】，先留一份 close_raw 再做复权。
    log("拉复权因子…")
    factors = P.fetch_adj_factors(pull_dates, sleep=0.10, log=log)
    panel["close_raw"] = panel["close"]
    panel = P.apply_qfq(panel, factors)
    panel["amount_yuan"] = panel["amount"] * 1000.0
    # 指数
    idx = {}
    for name, code in (("hs300", C.IDX_HS300), ("gem", C.IDX_GEM), ("star", C.IDX_STAR)):
        di = P._ts_query("index_daily", ts_code=code, start_date=start_pull).sort_values("trade_date").reset_index(drop=True)
        di["ma20"] = di["close"].rolling(20).mean(); di["ma60"] = di["close"].rolling(60).mean()
        di["vol_ma5"] = di["vol"].rolling(5).mean()
        idx[name] = di
    data = {"panel": panel, "basic": basic, "win_dates": win_dates, "idx": idx}
    cache = cache_path(start_win, end)
    P.assert_cache_write_ok()   # pandas版本护栏：不符则拒写共享缓存
    with open(cache, "wb") as f:
        pickle.dump(data, f)
    log("数据已缓存。")
    return data

# ---------------- 预处理：指标/行业/广度 ----------------
def prepare(data):
    panel, basic = data["panel"], data["basic"]
    name_map = dict(zip(basic["ts_code"], basic["name"]))
    ind_map = dict(zip(basic["ts_code"], basic["industry"].fillna("其他")))
    board_map = dict(zip(basic["ts_code"], basic["board"]))
    st_set = set(basic.loc[basic["name"].apply(P.is_st), "ts_code"])
    # 次新过滤基准（手册§1：上市不满60交易日不做，≈96自然日；ST 用当前名回溯是已知近似，见报告"限制"）
    list_map = dict(zip(basic["ts_code"], basic["list_date"].fillna("19900101")))

    log("计算个股指标…")
    panel = panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    g = panel.groupby("ts_code", sort=False)
    for n in (5, 10, 20, 60):
        panel[f"ma{n}"] = g["close"].transform(lambda s: s.rolling(n).mean())
    panel["vol_ma5"] = g["vol"].transform(lambda s: s.rolling(5).mean())
    panel["amt20"] = g["amount_yuan"].transform(lambda s: s.rolling(20).mean())
    panel["ma20_5ago"] = g["ma20"].transform(lambda s: s.shift(5))
    # screen_one / score_candidate 需要 ret 与 body_pct
    panel["prev_close"] = panel.groupby("ts_code", sort=False)["close"].shift(1)
    panel["ret"] = panel["close"] / panel["prev_close"] - 1
    panel["body_pct"] = (panel["close"] - panel["open"]) / panel["open"]

    # 行业合成指数（等权归一）→ 每日 gate 与 strength
    log("计算行业合成指数（v6.4.1时点口径：申万L2成分含进出日期，替代静态当前行业）…")
    _pit = __import__("时点数据"); _pitdb = _pit.load()
    import numpy as _np
    _ind_col = _np.full(len(panel), "其他", dtype=object)
    _pos0 = 0
    for _code, _sub in panel.groupby("ts_code", sort=False):
        _ivs = _pitdb["ind"].get(_code)
        if _ivs:
            _dates = _sub["trade_date"].values
            _seg = _np.full(len(_dates), "其他", dtype=object)
            for _nm, _a, _b in _ivs:
                _m = (_dates >= _a) & (_dates <= _b)
                _seg[_m] = _nm
            _ind_col[_sub.index.values] = _seg
    panel["ind"] = _ind_col
    ind_strength = {}  # (ind, date) -> strength ; ind_ok via >0 of (idx>ma20)
    ind_gate = {}
    sec_ret = {}       # date -> {ind: 20日涨幅}
    for ind, sub in panel.groupby("ind"):
        piv = sub.pivot_table(index="trade_date", columns="ts_code", values="close").sort_index()
        if piv.shape[0] < 25:
            continue
        _first = piv.apply(lambda col: col.loc[col.first_valid_index()] if col.first_valid_index() is not None else _np.nan)
        norm = piv.div(_first)   # v6.4.1：按各股首个有效值归一（时点成分中途加入的股票也计入合成）
        series = norm.mean(axis=1)
        ma20 = series.rolling(20).mean()
        ret20 = series / series.shift(20) - 1
        for d in series.index:
            m = ma20.loc[d]
            if pd.notna(m) and m:
                ind_gate[(ind, d)] = bool(series.loc[d] > m)
                ind_strength[(ind, d)] = float(series.loc[d] / m - 1)
            r = ret20.loc[d]
            if pd.notna(r):
                sec_ret.setdefault(d, {})[ind] = float(r)
    # 每日板块按20日涨幅排名（1=最强主线）→ 用于验证"只抱强主线"
    sector_rank = {}
    for d, m in sec_ret.items():
        ordered = sorted(m.items(), key=lambda kv: kv[1], reverse=True)
        sector_rank[d] = {ind: i + 1 for i, (ind, _) in enumerate(ordered)}

    # 每日广度/量能（用本回测股票池）
    log("计算每日广度/量能…")
    bd = panel.copy()
    _bm = getattr(__import__("策略规格"), "BREADTH_MODE", "body")
    _ref = bd["prev_close"] if _bm == "prevclose" else bd["open"]   # v6.4：body=现行口径(阳线家数)；prevclose=待验变体
    bd["up"] = (bd["close"] > _ref).astype(int)
    bd["down"] = (bd["close"] < _ref).astype(int)
    day_stat = bd.groupby("trade_date").agg(up_cnt=("up", "sum"), down_cnt=("down", "sum"),
                                            amt=("amount_yuan", "sum")).sort_index()
    day_stat["amt_ma20"] = day_stat["amt"].rolling(20).mean()

    # 指数最后行 dict（每日）
    idx = data["idx"]
    def idx_row(name, d):
        di = idx[name]; r = di[di["trade_date"] == d]
        if not len(r): return {}
        r = r.iloc[0]
        return {"close": float(r["close"]),
                "ma20": float(r["ma20"]) if pd.notna(r["ma20"]) else None,
                "ma60": float(r["ma60"]) if pd.notna(r["ma60"]) else None,
                "vol": float(r["vol"]), "vol_ma5": float(r["vol_ma5"]) if pd.notna(r["vol_ma5"]) else None}
    # 沪深300 ret20
    hs = idx["hs300"][["trade_date", "close"]].copy()
    hs["ret20"] = hs["close"] / hs["close"].shift(20) - 1
    hs_ret20 = dict(zip(hs["trade_date"], hs["ret20"]))

    # 个股按 code 切分（dict of arrays），便于前向模拟
    log("切分个股序列…")
    frames = {}
    for code, sub in panel.groupby("ts_code", sort=False):
        sub = sub.reset_index(drop=True)
        frames[code] = sub
    return dict(panel=panel, frames=frames, name_map=name_map, ind_map=ind_map, board_map=board_map,
                st_set=st_set, list_map=list_map, ind_gate=ind_gate, ind_strength=ind_strength,
                day_stat=day_stat, idx_row=idx_row, hs_ret20=hs_ret20, sector_rank=sector_rank)

# ---------------- 出场模拟（按手册规则）----------------
def simulate(sub, p, board, gap_thr, hold_max=HOLD_MAX, trail="ma5", stop_mode="next_open"):
    """sub: 该股指标df; p: 决策日(收盘)行号; 次日 p+1 入场。硬止损不变，盈利端可调(hold_max/trail)。返回 dict 或 None。
    出场时点（v2 修正）：手册规则是"收盘出信号 → 次日开盘卖"。旧版用信号当日收盘价成交，
    吃不到隔夜低开损失、系统性高估期望；现改为信号次日开盘成交（时间止损仍按当日收盘，与手册一致）。
    stop_mode：\"next_open\"=收盘确认→次日开盘卖（默认）；\"intraday\"=盘中触价条件单（手册§7允许的变体）——
    当日最低价≤止损价即按 min(开盘,止损价) 成交（低开跳空按开盘）；与2R同日冲突时保守地先算止损。"""
    n = len(sub)
    if p + 1 >= n: return None
    o1 = sub["open"].iloc[p + 1]; c0 = sub["close"].iloc[p]
    if not c0 or o1 / c0 - 1 > gap_thr: return None      # 高开放弃
    entry = float(sub["close"].iloc[p + 1])              # 次日尾盘≈收盘 入场
    ma10p = sub["ma10"].iloc[p]; lowp = sub["low"].iloc[p]
    ref = min(ma10p, lowp) if pd.notna(ma10p) else lowp
    stop = ref * (1 - C.BOARDS[board]["stop"])
    risk = entry - stop
    if risk <= 0: return None
    target = entry + 2 * risk

    def _next_open(j):
        """信号日 j 的次日开盘价；已是最后一根则退回当日收盘（截尾样本）。"""
        if j + 1 < n:
            return float(sub["open"].iloc[j + 1]), j + 1
        return float(sub["close"].iloc[j]), j

    half = False; half_px = None; rem_exit = None; exit_reason = "时间止损"; exit_j = min(p + 1 + hold_max, n - 1)
    for j in range(p + 2, min(p + 2 + hold_max, n)):
        hi = sub["high"].iloc[j]; cl = sub["close"].iloc[j]; mt = sub[trail].iloc[j]
        if stop_mode == "intraday":
            lo = sub["low"].iloc[j]; op = sub["open"].iloc[j]
            if lo <= stop:      # 触价即出（保守：同日2R冲突先算止损）
                rem_exit = float(min(op, stop)); exit_j = j
                exit_reason = "止损(触价)" if not half else "止损(触价,已减半)"
                break
        if not half and hi >= target:
            half = True; half_px = target
        if stop_mode != "intraday" and cl < stop:
            rem_exit, exit_j = _next_open(j); exit_reason = "止损" if not half else "止损(已减半)"
            break
        if half and pd.notna(mt) and cl < mt:
            rem_exit, exit_j = _next_open(j); exit_reason = "跌破均线"
            break
    if rem_exit is None:
        exit_j = min(p + 1 + hold_max, n - 1)
        rem_exit = float(sub["close"].iloc[exit_j])
        exit_reason = "2R后时间止损" if half else "时间止损"
    if half:
        gross = 0.5 * (half_px - entry) + 0.5 * (rem_exit - entry)
    else:
        gross = rem_exit - entry
    net = gross - entry * COST_RATE
    R = net / risk
    return dict(entry=round(entry, 2), stop=round(stop, 2), target=round(target, 2),
                exit=round(rem_exit, 2), reason=exit_reason, hold=exit_j - (p + 1),
                R=round(R, 3), ret_pct=round(net / entry * 100, 2), half=half)

def fwd_returns(sub, p):
    n = len(sub); c0 = sub["close"].iloc[p]; out = {}
    for k in (1, 3, 5, 10):
        out[f"fwd{k}"] = round((sub["close"].iloc[p + k] / c0 - 1) * 100, 2) if p + k < n and c0 else np.nan
    return out

# ---------------- 每日候选生成（run 与 组合级回测 共用，保证同源）----------------
def build_date_pos(frames):
    return {code: {d: i for i, d in enumerate(sub["trade_date"].values)} for code, sub in frames.items()}

def daily_state(P_, d):
    """决策日 d 收盘后的市场状态（§3），与实盘 score_market 同源。d 无数据返回 None。"""
    ds = P_["day_stat"]
    if d not in ds.index: return None
    row = ds.loc[d]
    hs, gem, star = P_["idx_row"]("hs300", d), P_["idx_row"]("gem", d), P_["idx_row"]("star", d)
    amt_3d = False
    try:
        pos = ds.index.get_loc(d)
        if pos >= 2:
            amt_3d = ds["amt"].iloc[pos] < ds["amt"].iloc[pos-1] < ds["amt"].iloc[pos-2]
    except Exception:
        pass
    return P.score_market(hs, gem, star, int(row["up_cnt"]), int(row["down_cnt"]),
                          float(row["amt"]), float(row["amt_ma20"]) if pd.notna(row["amt_ma20"]) else None, amt_3d)

def daily_candidates(data, P_, date_pos=None):
    """逐日yield (d, state, cands)。cand含 ts/code/board/ind/score/sec_rank/p行号/stop_price 等。
    过滤与实盘 pipeline 同源；价格上下限用当时真实价 close_raw（复权价会失真）。"""
    panel, frames = P_["panel"], P_["frames"]
    win_dates = data["win_dates"]
    if date_pos is None:
        date_pos = build_date_pos(frames)
    price_col = "close_raw" if "close_raw" in panel.columns else "close"
    for di, d in enumerate(win_dates):
        state = daily_state(P_, d)
        if state is None: continue
        if not state["can_open"]:
            yield d, state, []
            continue
        day = panel[panel["trade_date"] == d]
        pf = day[(day["close"] > day["ma20"]) & (day["ma10"] > day["ma20"]) &
                 (day[price_col].between(C.PRICE_MIN, C.PRICE_MAX)) &
                 (day["amt20"] >= C.MIN_AMOUNT_20D) &
                 ((day["close"] / day["ma10"] - 1).abs() <= C.SCREEN["pullback_band"] + 0.01)]
        d_dt = dt.datetime.strptime(d, "%Y%m%d").date()
        cands = []
        for _, r0 in pf.iterrows():
            code = r0["ts_code"]; board = P_["board_map"].get(code)
            if board is None: continue
            if __import__("时点数据").st_at(code, d): continue   # v6.4.1：时点ST（替代当前名回溯）
            ld = str(P_["list_map"].get(code, "19900101"))[:8]
            try:  # 次新过滤：上市不满约60交易日(≈96自然日)不做（手册§1；旧版漏了这条）
                if (d_dt - dt.datetime.strptime(ld, "%Y%m%d").date()).days < int(C.MIN_LIST_DAYS * 1.6):
                    continue
            except ValueError:
                pass
            if board == "chinext" and not state["gate_chinext"]: continue
            if board == "star" and not state["gate_star"]: continue
            sub = frames[code]; p = date_pos[code].get(d)
            if p is None or p < 25: continue
            di_slice = sub.iloc[:p + 1]
            ind = r0["ind"] if isinstance(r0.get("ind"), str) else "其他"   # v6.4.1：时点行业（决策日当时的归属）
            ind_ok = P_["ind_gate"].get((ind, d), True) if C.SCREEN["use_industry_gate"] else True
            cand = P.screen_one(di_slice, board, C.SCREEN, industry_ok=ind_ok)
            if not cand: continue
            cc = di_slice["close"]
            stock_ret20 = float(cc.iloc[-1] / cc.iloc[-21] - 1) if len(cc) >= 21 else 0.0
            rs = stock_ret20 - (P_["hs_ret20"].get(d) or 0.0)
            amt20_yi = round(float(r0["amt20"]) / 1e8, 2) if pd.notna(r0["amt20"]) else None
            # v2：补传 amt20_yi——容量微调此前只在实盘打分生效、回测缺失，两边不同源
            sc = P.score_candidate(di_slice, board, P_["ind_strength"].get((ind, d)), rs=rs, amt20_yi=amt20_yi)
            sec_rank = P_["sector_rank"].get(d, {}).get(ind, 999)
            is_core = ind in getattr(C, "CORE_THEMES", [])
            score = min(100, sc["score"] + (getattr(C, "CORE_BONUS", 0) if is_core else 0))
            grade = "A" if score >= 75 else ("B" if score >= 60 else "C")   # 加分后重评级，与实盘一致
            sc["grade"] = grade
            prior60 = float(sub["close"].iloc[p] / sub["close"].iloc[p - 60] - 1) if p >= 60 else float("nan")
            cands.append(dict(ts=code, code=code.split(".")[0], name=P_["name_map"].get(code, ""),
                              board=board, ind=ind, p=p, score=min(100, score), grade=sc["grade"],
                              rs=round(rs * 100, 1), sec_rank=sec_rank, core=is_core,
                              stop_price=cand["stop_price"],
                              prior60=(round(prior60 * 100, 1) if prior60 == prior60 else None),
                              amt20=amt20_yi))
        yield d, state, cands

def live_gate(cand):
    """实盘 config 的主线门（TOP_SECTORS / CORE_THEMES），组合级回测用；逐笔分析层不加以便对照。"""
    TOP = getattr(C, "TOP_SECTORS", 0)
    if not TOP: return True
    rank_gate = getattr(C, "CORE_RANK", 10) if cand["core"] else TOP
    return cand["sec_rank"] <= rank_gate

# ---------------- 主回测 ----------------
def run(start, end):
    data = fetch_all(start, end)
    P_ = prepare(data)
    frames = P_["frames"]
    win_dates = data["win_dates"]
    trades = []
    log(f"开始逐日回测 {len(win_dates)} 天…")
    n_done = 0
    for d, state, cands in daily_candidates(data, P_):
        n_done += 1
        for cd in cands:
            code = cd["ts"]; board = cd["board"]; p = cd["p"]
            sub = frames[code]
            gap = C.BOARDS[board]["gap"]
            sim = simulate(sub, p, board, gap)                       # 现状 8日/破MA5
            if sim is None: continue
            simL = simulate(sub, p, board, gap, hold_max=15, trail="ma10")  # 拉长 15日/破MA10
            simT = simulate(sub, p, board, gap, hold_max=20, trail="ma20")  # 趋势 20日/破MA20
            fr = fwd_returns(sub, p)
            trades.append(dict(date=d, code=cd["code"], name=cd["name"],
                               board=board, score=cd["score"], grade=cd["grade"], rs=cd["rs"],
                               sec_rank=cd["sec_rank"], prior60=cd["prior60"],
                               amt20=cd["amt20"], **sim, **fr,
                               R_long=(simL or {}).get("R"), hold_long=(simL or {}).get("hold"), ret_long=(simL or {}).get("ret_pct"),
                               R_trend=(simT or {}).get("R"), hold_trend=(simT or {}).get("hold"), ret_trend=(simT or {}).get("ret_pct")))
        if n_done % 40 == 0:
            log(f"  …{n_done}/{len(win_dates)}  累计 {len(trades)} 笔")
    log(f"回测完成，共 {len(trades)} 笔候选交易。")
    return pd.DataFrame(trades), win_dates

# ---------------- 统计与报告 ----------------
def report(tr, win_dates, tag="qfq"):
    if not len(tr):
        log("无交易，结束。"); return
    tr.to_csv(os.path.join(BASE, f"backtest_trades_{tag}.csv"), index=False, encoding="utf-8-sig")

    def stat(df):
        n = len(df)
        if not n: return dict(n=0, win="-", avgR="-", exp="-", payoff="-", avgret="-", hold="-")
        wins = df[df["R"] > 0]; losses = df[df["R"] <= 0]
        win = len(wins) / n
        payoff = (wins["R"].mean() / abs(losses["R"].mean())) if len(losses) and len(wins) else np.nan
        return dict(n=n, win=f"{win*100:.1f}%", avgR=f"{df['R'].mean():.3f}", exp=f"{df['R'].mean():.3f}",
                    payoff=f"{payoff:.2f}" if pd.notna(payoff) else "-",
                    avgret=f"{df['ret_pct'].mean():.2f}%", hold=f"{df['hold'].mean():.1f}")

    L = []
    L.append(f"# A股短线波段策略 · 回测报告（{tag}）\n")
    L.append(f"- 生成：{dt.datetime.now():%Y-%m-%d %H:%M}")
    L.append(f"- 窗口：{win_dates[0]} ~ {win_dates[-1]}（{len(win_dates)} 交易日）")
    L.append(f"- 候选交易样本：**{len(tr)}** 笔（每笔=按手册机械出场的一次模拟）")
    L.append(f"- 成本假设：往返 {COST_RATE*100:.1f}%（佣金+印花税+滑点）；入场≈次日尾盘收盘；最大持有 {HOLD_MAX} 日")
    L.append("- **v2 口径修正**（与旧 backtest_report.md 不可直接对比）：① 前复权（旧版未复权，除权除息被当成真实涨跌）；"
             "② 止损/破均线出场按**信号次日开盘价**成交（旧版按信号当日收盘，偏乐观）；"
             "③ 补上次新股过滤；④ 评分补传容量微调、含核心主线加分（与实盘打分完全同源）")
    s = stat(tr)
    L.append(f"\n## 总体\n")
    L.append(f"胜率 **{s['win']}** ｜ 平均R(期望) **{s['exp']}** ｜ 盈亏比 {s['payoff']} ｜ 平均收益 {s['avgret']} ｜ 平均持有 {s['hold']} 日")
    L.append(f"\n> 期望(平均R)>0 才说明这套机械规则在样本期是正期望；分档单调=打分有预测力。")

    def table(by, label, buckets):
        L.append(f"\n## 按{label}分档\n")
        L.append("| 档 | 笔数 | 胜率 | 平均R(期望) | 盈亏比 | 平均收益 |")
        L.append("|---|---|---|---|---|---|")
        for name_, mask in buckets:
            d = tr[mask]; st = stat(d)
            L.append(f"| {name_} | {st['n']} | {st['win']} | {st['avgR']} | {st['payoff']} | {st['avgret']} |")

    table("score", "评分", [("A(≥75)", tr["score"]>=75), ("B(60-74)", (tr["score"]>=60)&(tr["score"]<75)), ("C(<60)", tr["score"]<60)])
    qs = tr["score"].quantile([.25,.5,.75])
    table("评分四分位", "评分四分位", [
        (f"Q1低(≤{qs[.25]:.0f})", tr["score"]<=qs[.25]),
        (f"Q2", (tr["score"]>qs[.25])&(tr["score"]<=qs[.5])),
        (f"Q3", (tr["score"]>qs[.5])&(tr["score"]<=qs[.75])),
        (f"Q4高(>{qs[.75]:.0f})", tr["score"]>qs[.75])])
    table("RS", "相对强度RS", [("RS>10%", tr["rs"]>10), ("RS 0~10%", (tr["rs"]>0)&(tr["rs"]<=10)), ("RS≤0(弱于大盘)", tr["rs"]<=0)])
    table("board", "板块", [("主板", tr["board"]=="main"), ("创业板", tr["board"]=="chinext"), ("科创板", tr["board"]=="star")])
    tr["yr"] = tr["date"].str[:4]
    table("年份", "年份", [(y, tr["yr"]==y) for y in sorted(tr["yr"].unique())])

    # 主线集中度：只抱强主线能否提升Alpha
    table("板块强弱排名", "板块强弱排名（1=最强主线）", [
        ("Top1-5 强主线", tr["sec_rank"] <= 5),
        ("6-15 中等", (tr["sec_rank"] > 5) & (tr["sec_rank"] <= 15)),
        ("16+ 弱/熊板块", tr["sec_rank"] > 15)])
    L.append("\n## 关键验证：「只抱强主线」 vs 「全做」（板块按20日涨幅排名）\n")
    L.append("| 范围 | 笔数 | 胜率 | 平均R(期望) | 平均收益 |")
    L.append("|---|---|---|---|---|")
    for nm, d in [
        ("全样本·全部", tr),
        ("全样本·仅Top5主线", tr[tr["sec_rank"] <= 5]),
        ("全样本·仅Top3主线", tr[tr["sec_rank"] <= 3]),
        ("2026·全部", tr[tr["yr"] == "2026"]),
        ("2026·仅Top5主线", tr[(tr["yr"] == "2026") & (tr["sec_rank"] <= 5)]),
        ("2026·仅Top3主线", tr[(tr["yr"] == "2026") & (tr["sec_rank"] <= 3)]),
    ]:
        st = stat(d); L.append(f"| {nm} | {st['n']} | {st['win']} | {st['avgR']} | {st['avgret']} |")

    # 卖出时机对比：持有拉长（同硬止损，只放宽盈利端）
    L.append("\n## 卖出时机对比：持有拉长能不能更好（同样的硬止损，只放宽盈利端）\n")
    L.append("| 范围 · 出场方式 | 平均R(期望) | 胜率 | 平均持有日 | 平均收益 |")
    L.append("|---|---|---|---|---|")
    def evar(d, cR, cret, chold):
        rr = d[cR].dropna()
        if not len(rr): return ("-", "-", "-", "-")
        return (f"{rr.mean():.3f}", f"{(rr>0).mean()*100:.1f}%",
                f"{d[chold].dropna().mean():.1f}", f"{d[cret].dropna().mean():.2f}%")
    for nm, mask in [("全样本", pd.Series(True, index=tr.index)), ("仅Top5主线", tr["sec_rank"] <= 5)]:
        d = tr[mask]
        for vlabel, cR, cret, chold in [("现状 8日/破MA5", "R", "ret_pct", "hold"),
                                        ("拉长 15日/破MA10", "R_long", "ret_long", "hold_long"),
                                        ("趋势 20日/破MA20", "R_trend", "ret_trend", "hold_trend")]:
            a, b, c, e = evar(d, cR, cret, chold)
            L.append(f"| {nm} · {vlabel} | {a} | {b} | {c} | {e} |")
    L.append("\n> 看净期望(平均R)：拉长通常牺牲胜率、换更大的平均盈利。哪种期望更高且回撤可接受，就用哪种。")

    # 高位惯性测试：决策前60日涨幅 vs 表现（验证游资"追高位趋势"，对照我们打分里的过度乖离惩罚）
    pm = tr["prior60"]
    table("决策前60日涨幅(高位惯性)", "决策前60日涨幅", [
        ("跌(<0%)", pm < 0),
        ("0–30%", (pm >= 0) & (pm < 30)),
        ("30–60%", (pm >= 30) & (pm < 60)),
        ("60–100%", (pm >= 60) & (pm < 100)),
        (">100%(已翻倍)", pm >= 100)])
    L.append("\n> 若高涨幅档期望更高=游资『高位惯性』成立、我们的过度乖离惩罚应放松；若更低=惩罚是对的。仅Top5主线下另看一遍：")
    L.append("| 档(仅Top5主线) | 笔数 | 胜率 | 平均R(期望) | 平均收益 |")
    L.append("|---|---|---|---|---|")
    for nm, lo, hi in [("跌(<0%)", -1e9, 0), ("0–30%", 0, 30), ("30–60%", 30, 60), ("60–100%", 60, 100), (">100%", 100, 1e9)]:
        d = tr[(tr["sec_rank"] <= 5) & (pm >= lo) & (pm < hi)]
        st = stat(d); L.append(f"| {nm} | {st['n']} | {st['win']} | {st['avgR']} | {st['avgret']} |")

    # 大容量审美测试：近20日日均成交额(容量/流动性) vs 表现（验证游资#8"大容量核心更优"）
    am = tr["amt20"]
    table("近20日日均成交额(容量)", "近20日日均成交额", [
        ("2–5亿", (am >= 2) & (am < 5)),
        ("5–10亿", (am >= 5) & (am < 10)),
        ("10–20亿", (am >= 10) & (am < 20)),
        (">20亿(大容量)", am >= 20)])
    L.append("\n> 仅Top5主线下另看一遍（容量越大期望越高=『大容量审美』成立，可把容量设为打分正因子）：")
    L.append("| 档(仅Top5主线) | 笔数 | 胜率 | 平均R(期望) | 平均收益 |")
    L.append("|---|---|---|---|---|")
    for nm, lo, hi in [("2–5亿", 2, 5), ("5–10亿", 5, 10), ("10–20亿", 10, 20), (">20亿", 20, 1e9)]:
        d = tr[(tr["sec_rank"] <= 5) & (am >= lo) & (am < hi)]
        st = stat(d); L.append(f"| {nm} | {st['n']} | {st['win']} | {st['avgR']} | {st['avgret']} |")

    # 信号验证：前瞻收益(无出场规则) 按评分档
    L.append("\n## 信号验证：纯前瞻收益（不带出场规则，看打分预测力）\n")
    L.append("| 评分档 | 笔数 | 次日% | 3日% | 5日% | 10日% |")
    L.append("|---|---|---|---|---|---|")
    for name_, mask in [("A(≥75)", tr["score"]>=75), ("B(60-74)", (tr["score"]>=60)&(tr["score"]<75)), ("C(<60)", tr["score"]<60)]:
        d = tr[mask]
        if not len(d): continue
        L.append(f"| {name_} | {len(d)} | {d['fwd1'].mean():.2f} | {d['fwd3'].mean():.2f} | {d['fwd5'].mean():.2f} | {d['fwd10'].mean():.2f} |")

    # 资金曲线（每日取分数最高 TOP_N，固定 0.75% 风险/笔）
    eq = build_equity(tr, tag)
    L.append("\n## 资金曲线（每日取评分最高 %d 只，单笔风险 0.75%%）\n" % TOP_N_EQUITY)
    L.append(f"区间总收益 **{eq['total']:.1f}%** ｜ 最大回撤 **{eq['mdd']:.1f}%** ｜ 入场笔数 {eq['n']}")
    if eq.get("png"): L.append(f"\n资金曲线图：`backtest_equity_{tag}.png`")
    L.append("\n> ⚠️ 这条曲线是**逐笔R的简单串联**，不模拟仓位上限/每日开仓数/T+1/回撤熔断，"
             "也没有应用 TOP_SECTORS 主线门——只用于分档比较，**不代表可实现的账户曲线**。"
             "要看真实可执行的曲线，请看组合级回测 `portfolio_report_*.md`（portfolio_backtest.py 生成）。")

    # 限制
    L.append("""
## 诚实限制（务必读）
- **日线近似**：实盘是 14:50 盘中决策、次日尾盘买；回测用收盘价近似，封板/滑点/真实成交无法完全还原。
- **成本/滑点为假设**（往返约0.4%），实际可能更高，短线对成本极敏感。
- **行业主线为合成近似**，与券商口径不同。
- **ST 排除用当前股票名回溯**（历史曾 ST 已摘帽的会被误杀、当时是 ST 的可能漏排），轻微前视，影响很小。
- **前复权锚定窗口末**：回测里的成交价是复权价、非当时真实盘面价；比例类统计(R/收益率)不受影响。
- **正期望≠能赚钱**：还要能机械执行、扛住回撤；这正是"先回测、再模拟实盘练人"的原因。
- 本报告不构成投资建议。
""")
    open(os.path.join(BASE, f"backtest_report_{tag}.md"), "w", encoding="utf-8").write("\n".join(L))
    log(f"报告已生成：backtest_report_{tag}.md / backtest_trades_{tag}.csv")

def build_equity(tr, tag="qfq"):
    sub = tr.sort_values(["date", "score"], ascending=[True, False])
    picks = sub.groupby("date").head(TOP_N_EQUITY)
    cap = 1.0; curve = []; risk = 0.0075
    for _, r in picks.iterrows():
        cap *= (1 + risk * r["R"])
        curve.append(cap)
    if not curve:
        return dict(total=0, mdd=0, n=0)
    arr = np.array(curve); peak = np.maximum.accumulate(arr); mdd = ((arr - peak) / peak).min() * 100
    png = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(9, 4)); plt.plot((arr - 1) * 100)
        plt.title("Backtest Equity (top-%d/day, 0.75%% risk)" % TOP_N_EQUITY)
        plt.ylabel("Cumulative %"); plt.xlabel("Trade #"); plt.grid(alpha=.3); plt.tight_layout()
        png = os.path.join(BASE, f"backtest_equity_{tag}.png"); plt.savefig(png, dpi=110)
    except Exception as e:
        log(f"画图跳过：{str(e)[:60]}")
    return dict(total=(arr[-1]-1)*100, mdd=mdd, n=len(picks), png=png)

if __name__ == "__main__":
    t0 = time.time()
    start, end, tag = window_args()
    log(f"回测窗口 {start} ~ {end}（tag={tag}）")
    tr, wd = run(start, end)
    report(tr, wd, tag)
    log(f"全部完成，用时 {time.time()-t0:.0f}s")
