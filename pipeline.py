# -*- coding: utf-8 -*-
"""
A股短线波段操作助手 · 数据管线
职责：拉数据 → 算指标 → 市场状态打分(§3) → 选股(§4) → 写 data.js
设计：纯计算函数(add_indicators/score_market/screen_one)与取数函数分离，便于离线自测。
数据源：Tushare(全市场扫描，推荐) 优先；无 token 时退回 AKShare(自选清单模式)。盘中实时用新浪。
"""
import os, json, time, datetime as dt
import pandas as pd, numpy as np
import config as C

# 境内数据源(tushare/sina/eastmoney)需直连。绕过本机代理(如 Shadowrocket 127.0.0.1:1082)，
# 否则 tushare 请求会被代理拦截并 Read timed out。本行让 requests 对所有域名都不走代理。
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.pop("HTTP_PROXY", None); os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None); os.environ.pop("https_proxy", None)
os.environ.pop("ALL_PROXY", None); os.environ.pop("all_proxy", None)

# ---------------- 环境版本护栏（2026-07-03）----------------
# 两台机器经 OneDrive 共享 .pkl 缓存；pandas 3.x 写出的 pickle 在 2.3.3 下读不了（StringDtype 格式不兼容），
# 曾把样本外回测缓存覆盖损坏。全体统一锁 pandas==2.3.3（requirements.txt）；版本不符时：
# 导入即警告，写共享缓存前调用 assert_cache_write_ok() 直接拒绝（读不拦，向后兼容读通常没问题）。
PANDAS_PINNED = "2.3.3"
if pd.__version__ != PANDAS_PINNED:
    print(f"⚠️⚠️ 本机 pandas=={pd.__version__}，项目锁定 {PANDAS_PINNED}。"
          f"请运行「对齐pandas版本.command」或 pip install pandas=={PANDAS_PINNED}；"
          f"版本不符时禁止写共享 .pkl 缓存（会毒化其它机器）。", flush=True)

def assert_cache_write_ok():
    """写 OneDrive 共享 pickle 缓存前必须调用；pandas 版本不符即抛错。"""
    if pd.__version__ != PANDAS_PINNED:
        raise RuntimeError(
            f"拒绝写缓存：本机 pandas=={pd.__version__} ≠ 项目锁定 {PANDAS_PINNED}。"
            f"先运行「对齐pandas版本.command」对齐版本（否则写出的 pickle 其它机器读不了）。")

# ---------------- 通用小工具 ----------------
def board_of(code):
    c = str(code)[:6]
    if c.startswith("68"): return "star"       # 688/689 科创板
    if c.startswith("30"): return "chinext"    # 300/301/302… 创业板
    if c.startswith(("60", "00")): return "main"   # 沪主板 + 深主板000-003（002原中小板2021年已并入深主板，10cm）
    return None  # 北交所(8/4/92)等 → 不做
    # 2026-07-02 修正：旧版主板前缀只有("60","000","001")，约960只002/003深主板股被静默排除，
    # 与手册§0"沪深主板+创业板+科创板"的可交易范围不符（手册§1的板块代码表同步更正）。

def sina_symbol(code):
    c = str(code)[:6]
    pre = "sh" if c.startswith(("60", "688", "5")) else "sz"
    return pre + c

def is_st(name):
    return ("ST" in str(name).upper()) or ("退" in str(name))

def limit_up_thr(board, date=None):
    """涨停判定阈值。创业板 2020-08-24 注册制改 20cm，之前是 10cm——回测跨这个日期时按当日规则判。"""
    if board == "main":
        return 0.097
    if board == "chinext" and date is not None and str(date) < "20200824":
        return 0.097
    return 0.197

# ---------------- 纯计算：指标 ----------------
def add_indicators(df):
    """df: 单只股票日线，列含 open/high/low/close/vol，按日期升序。"""
    df = df.copy().reset_index(drop=True)
    for n in (5, 10, 20, 60):
        df["ma%d" % n] = df["close"].rolling(n).mean()
    df["vol_ma5"] = df["vol"].rolling(5).mean()
    df["prev_close"] = df["close"].shift(1)
    df["ret"] = df["close"] / df["prev_close"] - 1
    df["body_pct"] = (df["close"] - df["open"]) / df["open"]
    return df

# ---------------- 纯计算：选股(§4) ----------------
def screen_one(df, board, params, industry_ok=True):
    """返回候选 dict 或 None。df 需已 add_indicators 且按日期升序、行数尽量≥60。"""
    if df is None or len(df) < 25:
        return None
    last = df.iloc[-1]
    ma10, ma20, ma60 = last.get("ma10"), last.get("ma20"), last.get("ma60")
    if pd.isna(ma10) or pd.isna(ma20):
        return None

    # ② 趋势向上
    ma20_5ago = df["ma20"].iloc[-6] if len(df) >= 6 else np.nan
    trend = (last["close"] > ma20) and (ma10 > ma20) and (not pd.isna(ma20_5ago)) and (ma20 >= ma20_5ago)

    # ③ 资金参与过：近N日 有涨停 或 放量大阳（涨停阈值按当日规则：创业板2020-08前是10cm）
    look = df.tail(params["fund_lookback"])
    if "trade_date" in look.columns:
        thr = look["trade_date"].astype(str).map(lambda d: limit_up_thr(board, d))
    else:
        thr = limit_up_thr(board)
    big_yang = (look["ret"] > params["fund_big_yang_pct"]) & (look["vol"] > params["fund_big_yang_vol"] * look["vol"].shift(1))
    fund = bool((look["ret"] >= thr).any() or big_yang.any())

    # ④ 红肥绿瘦：阳线实体均值 ≥ 阴线实体均值 × ratio
    r = df.tail(params["rfgs_lookback"])
    up_body = r.loc[r["body_pct"] > 0, "body_pct"].mean()
    dn_body = (-r.loc[r["body_pct"] < 0, "body_pct"]).mean()
    rfgs = (not pd.isna(up_body)) and (pd.isna(dn_body) or up_body >= dn_body * params["rfgs_ratio"])

    # ⑤ 缩量回踩 MA10
    near = abs(last["close"] / ma10 - 1) <= params["pullback_band"]
    shrink = (not pd.isna(last["vol_ma5"])) and (last["vol"] < last["vol_ma5"] * params["shrink_ratio"])
    pullback = bool(near and shrink)

    # ⑥ 未破位：未跌破MA20；近3日无放量长阴
    last3 = df.tail(3)
    long_yin = ((last3["ret"] < -params["long_yin_pct"]) & (last3["vol"] > last3["vol"].shift(1))).any()
    not_broken = bool(last["close"] >= ma20 and not long_yin)

    checks = {
        "主线板块": bool(industry_ok), "趋势向上": bool(trend), "资金参与": fund,
        "红肥绿瘦": bool(rfgs), "缩量回踩": pullback, "未破位": not_broken,
    }
    if not all(checks.values()):
        return None

    b = C.BOARDS[board]
    ref = min(ma10, last["low"])
    stop_price = round(ref * (1 - b["stop"]), 2)
    return {
        "code": last.get("code", ""), "name": last.get("name", ""), "board": board,
        "board_cn": b["name"], "close": round(float(last["close"]), 2),
        "ma10": round(float(ma10), 2), "ma20": round(float(ma20), 2),
        "stop_price": stop_price, "gap_thr": b["gap"], "checks": checks,
    }

# ---------------- 纯计算：候选股打分(0-100) ----------------
def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def score_candidate(di, board, ind_strength, rs=None, amt20_yi=None):
    """对已通过§4筛选的候选股打分。6个维度，越高越强越优先。返回 score/grade/sub。"""
    last = di.iloc[-1]
    close = float(last["close"]); ma10 = float(last["ma10"]); ma20 = float(last["ma20"])
    ma60 = float(last["ma60"]) if not pd.isna(last.get("ma60")) else ma20
    vol = float(last["vol"]); vol_ma5 = float(last["vol_ma5"]) if not pd.isna(last["vol_ma5"]) else vol
    low = float(last["low"])

    # ① 趋势强度：MA20斜率 + 多头排列
    ma20_10 = di["ma20"].iloc[-11] if len(di) >= 11 and not pd.isna(di["ma20"].iloc[-11]) else ma20
    slope20 = (ma20 / ma20_10 - 1) if ma20_10 else 0.0
    align = 20 if (ma10 > ma20 > ma60) else (10 if ma10 > ma20 else 0)
    trend = min(100.0, _clamp(slope20 / 0.10) * 80 + align)

    # ② 主线/板块强度：所属行业指数高于其MA20的幅度
    sector = 50.0 if ind_strength is None else _clamp(ind_strength / 0.08) * 100

    # ③ 资金参与：近期涨停/放量大阳的强度×新近度（涨停阈值按当日规则）
    look = di.tail(C.SCREEN["fund_lookback"]).reset_index(drop=True)
    has_dt = "trade_date" in look.columns
    n = len(look); best = 0.0
    for i in range(n):
        thr = limit_up_thr(board, str(look["trade_date"].iloc[i]) if has_dt else None)
        r = look["ret"].iloc[i]; v = look["vol"].iloc[i]
        pv = look["vol"].iloc[i - 1] if i > 0 else v
        es = 0.0
        if r >= thr: es = 1.0
        elif r > 0.05 and pv > 0 and v > 2 * pv: es = _clamp((v / pv) / 4.0)
        if es > 0:
            recency = (i + 1) / n
            best = max(best, es * (0.5 + 0.5 * recency))
    money = _clamp(best) * 100

    # ④ 回踩质量：贴近MA10 + 缩量
    prox = 1 - _clamp(abs(close / ma10 - 1) / 0.03)
    shrink = _clamp((1 - vol / vol_ma5) / 0.5) if vol_ma5 else 0.0
    pullback = (prox * 0.6 + shrink * 0.4) * 100

    # ⑤ 红肥绿瘦：阳线实体/阴线实体
    r10 = di.tail(C.SCREEN["rfgs_lookback"])
    ub = r10.loc[r10["body_pct"] > 0, "body_pct"].mean()
    db = (-r10.loc[r10["body_pct"] < 0, "body_pct"]).mean()
    if pd.isna(ub): ub = 0.0
    ratio = 3.0 if (pd.isna(db) or db == 0) else ub / db
    rfgs = _clamp((ratio - 1) / 2.0) * 100

    # ⑥ 风险/位置：不追过度乖离(防反转) + 止损相对紧
    ext = close / ma20 - 1
    # v5.3 放松过度乖离惩罚：回测显示在Top5强主线里高乖离/已大涨的龙头反而期望最高，
    # 只惩罚极端乖离（>15%才开始扣、>35%扣满），避免惩罚正该骑的主线龙头。
    overext = 100 - _clamp((ext - 0.15) / 0.20) * 100
    stop_ref = min(ma10, low) * (1 - C.BOARDS[board]["stop"])
    stop_dist = (close - stop_ref) / close if close else 0.10
    tight = (1 - _clamp(stop_dist / 0.12)) * 100
    risk = 0.7 * overext + 0.3 * tight

    # ⑦ 相对强度（尾盘选股精华）：个股近20日涨幅 − 沪深300近20日涨幅，个股要强于大盘
    rs_score = 50.0 if rs is None else _clamp(rs / 0.15) * 100

    comp = (0.15 * trend + 0.15 * sector + 0.15 * rs_score + 0.15 * money
            + 0.20 * pullback + 0.10 * rfgs + 0.10 * risk)
    # 容量微调(v5.4)：回测——5–20亿(尤其10–20亿)流动性期望最高；过小(<5亿)或超大盘(>30亿)偏弱。
    cap_adj = 0
    if amt20_yi is not None:
        if 5 <= amt20_yi <= 20: cap_adj = 4
        elif amt20_yi < 5 or amt20_yi > 30: cap_adj = -4
    comp = max(0.0, min(100.0, comp + cap_adj))
    grade = "A" if comp >= 75 else ("B" if comp >= 60 else "C")
    return {"score": round(comp), "grade": grade,
            "sub": {"趋势": round(trend), "主线": round(sector), "相对强度": round(rs_score),
                    "资金": round(money), "回踩": round(pullback), "红绿": round(rfgs),
                    "风险": round(risk), "容量": cap_adj}}

# ---------------- 纯计算：市场状态(§3) ----------------
def classify_regime(up, down, lu, ld, hs_ma20, veto):
    """大盘研判：健康/混沌/退潮/冰点（读状态，不预测）。"""
    ratio = (down / up) if up else 99.0
    if ld is not None and ld >= 80:
        return {"label": "冰点", "cls": "b-empty",
                "action": "恐慌极致/或接近底——别满仓抄底；次日看核心龙头能否放量企稳，可轻仓试核心"}
    if veto or ratio >= 1.5 or ((not hs_ma20) and down > up):
        return {"label": "退潮", "cls": "b-empty",
                "action": "持续下跌风险——空仓/降档、守现金；持仓跌破MA10就撤(§6.9)"}
    if up > down and hs_ma20:
        return {"label": "健康", "cls": "b-attack",
                "action": "可按市场状态档位出手；只做缩量回踩的主线龙头"}
    return {"label": "混沌", "cls": "b-std",
            "action": "震荡——涨做减法、跌做加法；只低吸核心、不追高(§16.2)"}

def score_market(hs, gem, star, up_cnt, down_cnt, amt_today, amt_ma20, amt_3d_shrink):
    """hs/gem/star: 各指数最后一行(含 close/ma20/ma60/vol/vol_ma5 之类)的 dict。"""
    def above(idx, key):
        v, m = idx.get("close"), idx.get(key)
        return (v is not None and m is not None and not pd.isna(v) and not pd.isna(m) and v > m)
    score = 0
    score += 1 if above(hs, "ma20") else 0
    score += 1 if above(hs, "ma60") else 0
    score += 1 if (amt_today is not None and amt_ma20 is not None and amt_today >= amt_ma20) else 0
    score += 1 if (up_cnt is not None and down_cnt is not None and up_cnt > down_cnt) else 0

    veto = False
    # 指数放量跌破60线
    if hs.get("close") is not None and hs.get("ma60") is not None and not pd.isna(hs["ma60"]):
        if hs["close"] < hs["ma60"] and (hs.get("vol") or 0) > (hs.get("vol_ma5") or 1e18):
            veto = True
    # 千股下跌
    total = (up_cnt or 0) + (down_cnt or 0)
    if total > 0 and down_cnt is not None and down_cnt / total > 0.70:
        veto = True

    tiers = [("空仓", 0), ("防守", 20), ("标准", 40), ("进攻", 60)]
    t = 3 if score >= 3 else (2 if score == 2 else (1 if score == 1 else 0))
    if amt_3d_shrink: t = max(0, t - 1)   # 量能预警：连续3日萎缩降一档
    if veto: t = 0
    name, cap = tiers[t]
    can_open = t >= 2
    gate_gem = above(gem, "ma20") and can_open
    gate_star = above(star, "ma20") and can_open
    return {
        "score": score, "tier": name, "cap": cap, "can_open": can_open,
        "veto": veto, "shrink": bool(amt_3d_shrink),
        "gate_chinext": bool(gate_gem), "gate_star": bool(gate_star),
        "up_cnt": up_cnt, "down_cnt": down_cnt,
    }

# ---------------- Tushare 取数（全市场，推荐）----------------
import requests as _rq
TS_URL = "https://api.tushare.pro"   # 本机网络拦截 http(80)，必须用 https 直连 POST

def _ts_query(api_name, fields="", **params):
    """直连 https 调 tushare（绕开库默认的 http endpoint 与本机代理）。返回 DataFrame。
    带限流/网络重试：大批量拉历史（回测）时不至于中途崩。"""
    if not C.TUSHARE_TOKEN:
        raise RuntimeError("未配置 TUSHARE_TOKEN")
    payload = {"api_name": api_name, "token": C.TUSHARE_TOKEN, "params": params, "fields": fields}
    last_err = None
    for attempt in range(5):
        try:
            r = _rq.post(TS_URL, json=payload, timeout=30)
            j = r.json()
            if j.get("code") == 0:
                d = j.get("data") or {}
                df = pd.DataFrame(d.get("items", []), columns=d.get("fields", []))
                for c in ("open", "high", "low", "close", "vol", "amount", "pre_close", "change", "pct_chg", "adj_factor"):
                    if c in df.columns:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                return df
            msg = str(j.get("msg") or "")
            last_err = RuntimeError(f"tushare {api_name} 返回错误: {msg}")
            if ("每分钟" in msg) or ("频率" in msg) or ("最多访问" in msg):
                time.sleep(25)          # 限流：等一个窗口再试
                continue
            raise last_err              # 权限/参数类错误，重试无意义
        except (ValueError, _rq.RequestException) as e:   # 网络抖动/JSON坏包
            last_err = e
            time.sleep(3 * (attempt + 1))
    raise last_err

def fetch_adj_factors(dates, sleep=0.1, log=None):
    """按交易日批量拉全市场复权因子。返回 DataFrame[ts_code, trade_date, adj_factor]。"""
    frames = []
    for i, d in enumerate(dates):
        df = _ts_query("adj_factor", fields="ts_code,trade_date,adj_factor", trade_date=d)
        if df is not None and len(df):
            frames.append(df)
        if log and i % 40 == 0:
            log(f"  复权因子 …{i}/{len(dates)}")
        time.sleep(sleep)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ts_code", "trade_date", "adj_factor"])

def apply_qfq(panel, factors):
    """把日线面板做前复权（锚定各股窗口内最新一天：最后一根K线价格=真实现价）。
    open/high/low/close × (factor/最新factor)；vol 反向调整保证跨送转可比；amount 不动。"""
    if factors is None or not len(factors):
        return panel
    panel = panel.merge(factors, on=["ts_code", "trade_date"], how="left")
    panel = panel.sort_values(["ts_code", "trade_date"])
    g = panel.groupby("ts_code", sort=False)
    panel["adj_factor"] = g["adj_factor"].ffill()
    panel["adj_factor"] = panel["adj_factor"].fillna(1.0)
    last_f = g["adj_factor"].transform("last")
    ratio = panel["adj_factor"] / last_f
    for c in ("open", "high", "low", "close"):
        if c in panel.columns:
            panel[c] = panel[c] * ratio
    if "vol" in panel.columns:
        panel["vol"] = panel["vol"] / ratio.replace(0, np.nan)
    return panel.drop(columns=["adj_factor"]).reset_index(drop=True)

def holder_number(ts_code, limit=12):
    """股东户数（近况，含每期环比%）。
    修复要点(2026-07-16)：Tushare stk_holdernumber 会混入 end_date==ann_date 的"公告占位空行"
    (holder_num=None)，且对部分科创板票(如炬芯688049)基本无覆盖——这是此前拉数据出 NaN/空的根因。
    改为：主源=东财 F10 ShareholderResearch(覆盖科创板/全市场、自带变化率)；备源=Tushare(过滤空行)。
    返回按日期升序的 [{'date','num','chg_pct'}]；无数据返回 []。"""
    code6 = ts_code.split(".")[0]
    if ts_code.endswith(".SH"):   ex = "SH"
    elif ts_code.endswith(".SZ"): ex = "SZ"
    elif ts_code.endswith(".BJ"): ex = "BJ"
    else:                          ex = "SH" if code6[:1] == "6" else "SZ"
    # 1) 东财 F10（主）
    try:
        r = _rq.get("https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax",
                    params={"code": ex + code6},
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://emweb.securities.eastmoney.com/"},
                    timeout=8)
        out = []
        for row in ((r.json() or {}).get("gdrs") or []):
            n = row.get("HOLDER_TOTAL_NUM"); d = (row.get("END_DATE") or "")[:10]
            if n is None or not d:
                continue
            rt = row.get("TOTAL_NUM_RATIO")
            out.append({"date": d, "num": int(n),
                        "chg_pct": (round(float(rt), 2) if rt is not None else None)})
        if out:
            out.sort(key=lambda x: x["date"])
            return out[-limit:]
    except Exception:
        pass
    # 2) Tushare（备，过滤 end_date==ann_date 的空行）
    try:
        df = _ts_query("stk_holdernumber", ts_code=ts_code,
                       start_date="20200101", end_date=dt.date.today().strftime("%Y%m%d"))
        if df is not None and len(df):
            df = df.copy()
            df["holder_num"] = pd.to_numeric(df["holder_num"], errors="coerce")
            df = df[df["holder_num"].notna() & (df["end_date"].astype(str) != df["ann_date"].astype(str))]
            df = df.drop_duplicates("end_date").sort_values("end_date")
            out = []; prev = None
            for _, rr in df.iterrows():
                n = int(rr["holder_num"]); s = str(rr["end_date"])
                out.append({"date": "%s-%s-%s" % (s[:4], s[4:6], s[6:8]), "num": n,
                            "chg_pct": (round((n / prev - 1) * 100, 2) if prev else None)})
                prev = n
            return out[-limit:]
    except Exception:
        pass
    return []

def _recent_trade_dates(n=70):
    today = dt.date.today().strftime("%Y%m%d")
    start = (dt.date.today() - dt.timedelta(days=160)).strftime("%Y%m%d")
    cal = _ts_query("trade_cal", exchange="SSE", start_date=start, end_date=today, is_open="1")
    return sorted(cal["cal_date"].tolist())[-n:]

def build_with_tushare():
    basic = _ts_query("stock_basic", fields="ts_code,symbol,name,industry,market,list_date",
                      exchange="", list_status="L")
    basic = basic[~basic["name"].apply(is_st)]
    basic["board"] = basic["symbol"].apply(board_of)
    basic = basic[basic["board"].notna()]
    if C.EXCLUDE_BSE:
        basic = basic[~basic["ts_code"].str.endswith(".BJ")]
    # 次新过滤
    cutoff = (dt.date.today() - dt.timedelta(days=int(C.MIN_LIST_DAYS * 1.6))).strftime("%Y%m%d")
    basic = basic[basic["list_date"] <= cutoff]
    name_map = dict(zip(basic["ts_code"], basic["name"]))
    # v6.4.1：行业改用申万L2时点成分的"当日值"（与回测同分类源）；缓存超7天自动重建；无归属回落静态行业
    try:
        _pit = __import__("时点数据"); _db = _pit.load()
        import datetime as _dt
        if (_dt.datetime.now() - _dt.datetime.strptime(_db["pulled_at"], "%Y-%m-%d %H:%M")).days > 7:
            _db = _pit.load(refresh=True)
        _today = _dt.date.today().strftime("%Y%m%d")
        _static = dict(zip(basic["ts_code"], basic["industry"].fillna("其他")))
        ind_map = {ts: (_pit.ind_at(ts, _today) or _static.get(ts, "其他")) for ts in basic["ts_code"]}
        print("[ok] 行业分类=申万L2时点成分（%s拉取）" % _db["pulled_at"])
    except Exception as _e:
        print("[warn] 时点行业不可用，回落静态行业：", str(_e)[:60])
        ind_map = dict(zip(basic["ts_code"], basic["industry"].fillna("其他")))
    board_map = dict(zip(basic["ts_code"], basic["board"]))
    keep = set(basic["ts_code"])

    dates = _recent_trade_dates(70)
    frames = []
    for d in dates:
        df = _ts_query("daily", fields="ts_code,trade_date,open,high,low,close,vol,amount", trade_date=d)
        if df is not None and len(df):
            frames.append(df[df["ts_code"].isin(keep)])
        time.sleep(0.12)
    alld = pd.concat(frames, ignore_index=True)
    # 前复权：不复权价会把除权除息当成真实暴跌，污染均线/涨停/红肥绿瘦判定（手册§13要求前复权）
    factors = fetch_adj_factors(dates, sleep=0.12)
    alld = apply_qfq(alld, factors)
    alld["amount_yuan"] = alld["amount"] * 1000.0  # tushare amount 单位千元 → 元

    # 市场广度 & 量能（用"最近真正有数据的一天"，避免开盘前/盘中刷新时取到当天空数据→0/0）
    last_day = alld["trade_date"].max()
    last_slice = alld[alld["trade_date"] == last_day]
    up_cnt = int((last_slice["close"] > last_slice["open"]).sum())
    down_cnt = int((last_slice["close"] < last_slice["open"]).sum())
    amt_by_day = alld.groupby("trade_date")["amount_yuan"].sum().sort_index()
    amt_today = float(amt_by_day.iloc[-1])
    amt_ma20 = float(amt_by_day.tail(20).mean())
    amt_3d_shrink = bool(len(amt_by_day) >= 4 and amt_by_day.iloc[-1] < amt_by_day.iloc[-2] < amt_by_day.iloc[-3])

    # 行业合成指数（等权归一）→ industry_ok = 行业指数 > 其MA20
    industry_ok_map = {}
    industry_strength_map = {}
    industry_ret20 = {}
    if C.SCREEN["use_industry_gate"]:
        alld["ind"] = alld["ts_code"].map(ind_map)
        for ind, g in alld.groupby("ind"):
            piv = g.pivot_table(index="trade_date", columns="ts_code", values="close").sort_index()
            norm = piv / piv.iloc[0]
            idx_series = norm.mean(axis=1)
            if len(idx_series) >= 21:
                ma20v = idx_series.tail(20).mean()
                industry_ok_map[ind] = bool(idx_series.iloc[-1] > ma20v)
                industry_strength_map[ind] = float(idx_series.iloc[-1] / ma20v - 1) if ma20v else 0.0
                industry_ret20[ind] = float(idx_series.iloc[-1] / idx_series.iloc[-21] - 1)
    # 板块按20日涨幅排名（1=最强主线）；只抱最强主线
    sector_rank_map = {ind: i + 1 for i, (ind, _) in
                       enumerate(sorted(industry_ret20.items(), key=lambda kv: kv[1], reverse=True))}
    TOP_SEC = getattr(C, "TOP_SECTORS", 0)

    # 指数
    def idx_last(code):
        s = (dt.date.today() - dt.timedelta(days=160)).strftime("%Y%m%d")
        di = _ts_query("index_daily", ts_code=code, start_date=s)
        if di is None or not len(di): return {}
        di = di.sort_values("trade_date").reset_index(drop=True)
        di = di.rename(columns={})
        di["ma20"] = di["close"].rolling(20).mean(); di["ma60"] = di["close"].rolling(60).mean()
        di["vol_ma5"] = di["vol"].rolling(5).mean()
        r = di.iloc[-1]
        return {"close": float(r["close"]), "ma20": float(r["ma20"]) if not pd.isna(r["ma20"]) else None,
                "ma60": float(r["ma60"]) if not pd.isna(r["ma60"]) else None,
                "vol": float(r["vol"]), "vol_ma5": float(r["vol_ma5"]) if not pd.isna(r["vol_ma5"]) else None}
    hs, gem, star = idx_last(C.IDX_HS300), idx_last(C.IDX_GEM), idx_last(C.IDX_STAR)

    # 相对强度基准(沪深300近20日涨幅) + 换手率/流通市值（尾盘选股精华）
    try:
        _hs = _ts_query("index_daily", ts_code=C.IDX_HS300,
                        start_date=(dt.date.today() - dt.timedelta(days=90)).strftime("%Y%m%d")).sort_values("trade_date")
        hs300_ret20 = float(_hs["close"].iloc[-1] / _hs["close"].iloc[-21] - 1) if len(_hs) >= 21 else 0.0
    except Exception:
        hs300_ret20 = 0.0
    try:
        db = _ts_query("daily_basic", trade_date=last_day, fields="ts_code,turnover_rate,circ_mv")
        turn_map = dict(zip(db["ts_code"], pd.to_numeric(db["turnover_rate"], errors="coerce")))
        mv_map = dict(zip(db["ts_code"], pd.to_numeric(db["circ_mv"], errors="coerce")))
    except Exception:
        turn_map, mv_map = {}, {}

    state = score_market(hs, gem, star, up_cnt, down_cnt, amt_today, amt_ma20, amt_3d_shrink)

    # 大盘研判：涨跌停家数 + 状态分类(健康/混沌/退潮/冰点)
    try:
        _lu = _ts_query("limit_list_d", trade_date=last_day, limit_type="U")
        _ld = _ts_query("limit_list_d", trade_date=last_day, limit_type="D")
        lu_n = int(len(_lu)) if _lu is not None else None
        ld_n = int(len(_ld)) if _ld is not None else None
    except Exception:
        lu_n = ld_n = None
    _hs_ma20 = bool((hs.get("close") or 0) >= (hs.get("ma20") or 0)) if hs else True   # ma20 可能为 None（历史不足）
    state["limit_up"] = lu_n
    state["limit_down"] = ld_n
    state["regime"] = classify_regime(up_cnt, down_cnt, lu_n, ld_n, _hs_ma20, bool(state.get("veto", False)))

    # 选股
    candidates = []
    amt20_by_code = alld.groupby("ts_code")["amount_yuan"].apply(lambda s: s.tail(20).mean())
    for code, g in alld.groupby("ts_code"):
        if amt20_by_code.get(code, 0) < C.MIN_AMOUNT_20D:
            continue
        g = g.sort_values("trade_date")
        last_close = g["close"].iloc[-1]
        if not (C.PRICE_MIN <= last_close <= C.PRICE_MAX):
            continue
        board = board_map.get(code)
        if board is None:
            continue
        # 板块状态门
        if board == "chinext" and not state["gate_chinext"]:
            continue
        if board == "star" and not state["gate_star"]:
            continue
        if not state["can_open"]:
            continue
        the_ind = ind_map.get(code, "")
        srank = sector_rank_map.get(the_ind, 999)
        is_core = the_ind in getattr(C, "CORE_THEMES", [])
        rank_gate = getattr(C, "CORE_RANK", 10) if is_core else TOP_SEC
        if TOP_SEC and srank > rank_gate:    # 只抱最强主线（核心战略主线门更宽）
            continue
        di = add_indicators(g.rename(columns={}))
        di["code"] = code; di["name"] = name_map.get(code, "")
        ind_ok = industry_ok_map.get(the_ind, True) if C.SCREEN["use_industry_gate"] else True
        cand = screen_one(di, board, C.SCREEN, industry_ok=ind_ok)
        if cand:
            cand["code"] = code.split(".")[0]; cand["name"] = name_map.get(code, "")
            cand["sec"] = the_ind; cand["sec_rank"] = srank; cand["core"] = bool(is_core)
            cc = di["close"]
            stock_ret20 = float(cc.iloc[-1] / cc.iloc[-21] - 1) if len(cc) >= 21 else 0.0
            rs = stock_ret20 - hs300_ret20
            cand.update(score_candidate(di, board, industry_strength_map.get(the_ind, None), rs=rs,
                                        amt20_yi=amt20_by_code.get(code, 0) / 1e8))
            if is_core:   # 核心战略主线加权
                cand["score"] = min(100, cand["score"] + getattr(C, "CORE_BONUS", 0))
                cand["grade"] = "A" if cand["score"] >= 75 else ("B" if cand["score"] >= 60 else "C")
            cand["rs"] = round(rs * 100, 1)
            # 前向观察需要的两个透明字段（2026-07-03：Codex格子标志用；纯展示，不参与门/评分）
            cand["prior60"] = round(float(cc.iloc[-1] / cc.iloc[-61] - 1) * 100, 1) if len(cc) >= 61 else None
            cand["amt20_yi"] = round(amt20_by_code.get(code, 0) / 1e8, 2)
            tv = turn_map.get(code); cand["turnover"] = round(float(tv), 2) if tv is not None and not pd.isna(tv) else None
            mv = mv_map.get(code); cand["circ_mv_yi"] = round(float(mv) / 1e4) if mv is not None and not pd.isna(mv) else None
            candidates.append(cand)

    _latest_cal = dates[-1] if dates else last_day
    _dd = "%s-%s-%s" % (last_day[:4], last_day[4:6], last_day[6:8])
    return _assemble(state, candidates, source="tushare",
                     data_date=_dd, is_fresh=(last_day == _latest_cal))

# ---------------- AKShare 取数（自选清单兜底）----------------
def build_with_akshare():
    import akshare as ak
    end = dt.date.today().strftime("%Y%m%d")
    start = (dt.date.today() - dt.timedelta(days=160)).strftime("%Y%m%d")

    def idx_last(symbol):
        try:
            di = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start, end_date=end)
            di = di.rename(columns={"日期": "trade_date", "收盘": "close", "成交量": "vol"})
            di["ma20"] = di["close"].rolling(20).mean(); di["ma60"] = di["close"].rolling(60).mean()
            di["vol_ma5"] = di["vol"].rolling(5).mean()
            r = di.iloc[-1]
            return {"close": float(r["close"]), "ma20": float(r["ma20"]), "ma60": float(r["ma60"]),
                    "vol": float(r["vol"]), "vol_ma5": float(r["vol_ma5"])}
        except Exception:
            return {}
    hs, gem, star = idx_last("000300"), idx_last("399006"), idx_last("000688")

    # 广度/量能用实时快照（盘后≈当日）
    up_cnt = down_cnt = amt_today = amt_ma20 = None; amt_3d_shrink = False
    try:
        spot = ak.stock_zh_a_spot_em()
        # v6.4：与Tushare路径/回测同口径=阳线家数（收盘>开盘）；此前用涨跌幅，两源同日会给出不同档位
        up_cnt = int((spot["最新价"] > spot["今开"]).sum()); down_cnt = int((spot["最新价"] < spot["今开"]).sum())
        amt_today = float(spot["成交额"].sum())
    except Exception:
        pass
    state = score_market(hs, gem, star, up_cnt, down_cnt, amt_today, amt_ma20, amt_3d_shrink)

    candidates = []
    for code in C.WATCHLIST:
        board = board_of(code)
        if board is None: continue
        if board == "chinext" and not state["gate_chinext"]: continue
        if board == "star" and not state["gate_star"]: continue
        if not state["can_open"]: continue
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
            df = df.rename(columns={"日期": "trade_date", "开盘": "open", "最高": "high",
                                    "最低": "low", "收盘": "close", "成交量": "vol", "成交额": "amount_yuan"})
            if df["amount_yuan"].tail(20).mean() < C.MIN_AMOUNT_20D: continue
            if not (C.PRICE_MIN <= df["close"].iloc[-1] <= C.PRICE_MAX): continue
            di = add_indicators(df)
            di["code"] = code
            cand = screen_one(di, board, C.SCREEN, industry_ok=True)  # 兜底模式不做行业门
            if cand:
                cand["code"] = code
                try: cand["name"] = ak.stock_individual_info_em(symbol=code).set_index("item").loc["股票简称", "value"]
                except Exception: cand["name"] = code
                cand.update(score_candidate(di, board, None))
                candidates.append(cand)
            time.sleep(0.3)
        except Exception:
            continue
    return _assemble(state, candidates, source="akshare")

# ---------------- 实时（盘中校验，新浪 L1）----------------
def realtime_sina(codes):
    import requests
    syms = ",".join(sina_symbol(c) for c in codes)
    url = "https://hq.sinajs.cn/list=" + syms
    out = {}
    try:
        r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=6)
        r.encoding = "gbk"
        for line in r.text.strip().split("\n"):
            if "=" not in line: continue
            key, val = line.split("=", 1)
            code6 = key.split("_")[-1][2:]
            f = val.strip().strip('";').split(",")
            if len(f) < 32: continue
            o, pc, price = float(f[1]), float(f[2]), float(f[3])
            out[code6] = {
                "name": f[0], "open": o, "prev_close": pc, "price": price,
                "gap_pct": round((o / pc - 1) * 100, 2) if pc else None,
                "chg_pct": round((price / pc - 1) * 100, 2) if pc else None,
            }
    except Exception as e:
        out["_error"] = str(e)
    return out

# ---------------- 实时大盘指数（盘中参考，新浪 L1）----------------
_MARKET_IDX = [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指"),
               ("sh000688", "科创50"), ("sh000300", "沪深300"), ("sh000852", "中证1000")]

_LIM_CACHE = {"t": 0.0, "up": None, "down": None}
def _limit_counts():
    """涨停/跌停家数(东财 push2ex, 一次调用拿 data.tc)。60秒缓存，防高频轮询被限流。"""
    import requests, time
    now = time.time()
    if now - _LIM_CACHE["t"] < 60 and _LIM_CACHE["up"] is not None:
        return {"up": _LIM_CACHE["up"], "down": _LIM_CACHE["down"]}
    ut = "7eea3edcaed734bea9cbfc24409ed989"   # 东财网页内置公开 token，非账号
    today = dt.date.today().strftime("%Y%m%d")
    out = {"up": None, "down": None}
    for key, api in (("up", "getTopicZTPool"), ("down", "getTopicDTPool")):
        try:
            r = requests.get("https://push2ex.eastmoney.com/" + api,
                             params={"ut": ut, "dpt": "wz.ztzt", "Pageindex": 0,
                                     "pagesize": 1, "sort": "fbt:asc", "date": today},
                             headers={"Referer": "https://quote.eastmoney.com/"}, timeout=6)
            d = r.json().get("data") or {}
            out[key] = d.get("tc")
        except Exception:
            pass
    if out["up"] is not None or out["down"] is not None:
        _LIM_CACHE.update({"t": now, "up": out["up"], "down": out["down"]})
    return out

def _intraday_regime(hs, zz, amt, lu, ld):
    """盘中研判(读状态、不预测)：大小盘背离 + 涨跌停 + 指数/成交额 → 健康/混沌/退潮/冰点。"""
    diverge = (hs is not None and zz is not None and (hs - zz) >= 0.6 and zz <= -0.5)
    note = "大小盘背离：指数被权重股撑住、小票更弱" if diverge else ""
    if ld is not None and ld >= 80:
        return {"label": "冰点", "cls": "b-empty", "note": (note or "跌停密集、恐慌极致"),
                "action": "别追跌、别满仓抄底；看核心龙头能否放量企稳再轻仓试核心"}
    if (hs is not None and hs <= -2) or (amt is not None and amt < 8000) \
       or (lu is not None and ld is not None and ld >= 30 and ld >= 1.5 * max(lu, 1)) or diverge:
        return {"label": "退潮", "cls": "b-empty", "note": note,
                "action": "空仓/降档、守现金；持仓跌破MA10就撤(§6.9)"}
    if hs is not None and hs >= 0.5 and zz is not None and zz >= 0:
        return {"label": "健康", "cls": "b-attack", "note": "大小盘同向走强、个股普涨确认",
                "action": "可按市场状态档位出手；只做缩量回踩龙头"}
    return {"label": "混沌", "cls": "b-std", "note": note,
            "action": "震荡——涨做减法、跌做加法；只低吸核心、不追高"}
def realtime_market():
    import requests
    syms = ",".join(s for s, _ in _MARKET_IDX) + ",sz399106"
    url = "https://hq.sinajs.cn/list=" + syms
    out = {"indices": [], "amt_total_yi": None, "ts": dt.datetime.now().strftime("%H:%M:%S")}
    try:
        r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=6)
        r.encoding = "gbk"
        data = {}
        for line in r.text.strip().split("\n"):
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            sym = key.split("_")[-1]
            f = val.strip().strip('";').split(",")
            if len(f) < 10:
                continue
            try:
                pc, price, amt = float(f[2]), float(f[3]), float(f[9])
            except Exception:
                continue
            data[sym] = {"price": price, "chg_pct": round((price / pc - 1) * 100, 2) if pc else None, "amount": amt}
        for sym, nm in _MARKET_IDX:
            d = data.get(sym)
            if d:
                out["indices"].append({"name": nm, "price": d["price"], "chg_pct": d["chg_pct"]})
        sh = data.get("sh000001", {}).get("amount")
        sz = data.get("sz399106", {}).get("amount")
        if sh is not None and sz is not None:
            out["amt_total_yi"] = round((sh + sz) / 1e8)
        # 盘中研判：大小盘背离(沪深300 vs 中证1000) + 涨跌停家数(push2ex)
        _hc = data.get("sh000300", {}).get("chg_pct")
        _zz = data.get("sh000852", {}).get("chg_pct")
        _lim = _limit_counts()
        out["limit_up"] = _lim.get("up")
        out["limit_down"] = _lim.get("down")
        out["divergence"] = (round(_hc - _zz, 2) if (_hc is not None and _zz is not None) else None)
        out["regime"] = _intraday_regime(_hc, _zz, out.get("amt_total_yi"), _lim.get("up"), _lim.get("down"))
    except Exception as e:
        out["_error"] = str(e)
    return out

# ---------------- 资金流 / 主线（盘后参考，Tushare）----------------
def realtime_flow(top=8):
    out = {"date": None, "ind_in": [], "ind_out": [], "north_yi": None,
           "limit_total": 0, "limit_top_ind": [], "max_streak": None,
           "ts": dt.datetime.now().strftime("%H:%M:%S")}
    try:
        dates = _recent_trade_dates(6)
        ind = None; last = None
        for d in reversed(dates[-3:]):          # 取最近"有数据"的交易日(盘中今日未出则退回上一日)
            t = _ts_query("moneyflow_ind_ths", trade_date=d)
            if t is not None and len(t):
                ind = t; last = d; break
        if last is None:
            last = dates[-1]
        out["date"] = "%s-%s-%s" % (last[:4], last[4:6], last[6:8])
        if ind is not None and len(ind):
            ind = ind.copy()
            ind["net_amount"] = pd.to_numeric(ind["net_amount"], errors="coerce")
            ind["pct_change"] = pd.to_numeric(ind["pct_change"], errors="coerce")
            ind = ind.dropna(subset=["net_amount"])
            def _row(r):
                return {"name": r["industry"],
                        "net": round(float(r["net_amount"]), 1),
                        "pct": (round(float(r["pct_change"]), 2) if not pd.isna(r["pct_change"]) else None),
                        "lead": (r.get("lead_stock", "") or "")}
            out["ind_in"] = [_row(r) for _, r in ind.sort_values("net_amount", ascending=False).head(top).iterrows()]
            out["ind_out"] = [_row(r) for _, r in ind.sort_values("net_amount", ascending=True).head(5).iterrows()]
        try:                                     # 北向资金(万元→亿)
            hg = _ts_query("moneyflow_hsgt", start_date=last, end_date=last)
            if hg is not None and len(hg):
                nm = pd.to_numeric(hg.iloc[0]["north_money"], errors="coerce")
                if not pd.isna(nm):
                    out["north_yi"] = round(float(nm) / 10000.0, 1)
        except Exception:
            pass
        try:                                     # 涨停分布
            lim = _ts_query("limit_list_d", trade_date=last, limit_type="U")
            if lim is not None and len(lim):
                out["limit_total"] = int(len(lim))
                by = lim.groupby("industry").size().sort_values(ascending=False).head(6)
                out["limit_top_ind"] = [{"name": k, "n": int(v)} for k, v in by.items()]
                lt = pd.to_numeric(lim["limit_times"], errors="coerce")
                if lt.notna().any():
                    out["max_streak"] = int(lt.max())
        except Exception:
            pass
    except Exception as e:
        out["_error"] = str(e)
    return out

# ---------------- 组装 & 落盘 ----------------
def _assemble(state, candidates, source, data_date=None, is_fresh=None):
    candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
    _today = dt.date.today().strftime("%Y-%m-%d")
    try:                                    # 失效判据状态（v6.3：HTML/信号共用；读不到不阻塞刷新）
        fj = __import__("失效判据").evaluate()
        fj = {"level": fj["level"], "n": fj["n"], "text": fj["text"]}
    except Exception:
        fj = None
    try:                                    # 底仓推荐（v6.3：strong3每5日择强；失败不阻塞刷新）
        base = __import__("底仓引擎").recommend(cap=(state or {}).get("cap"))
    except Exception:
        base = None
    return {
        "date": _today,
        "data_date": data_date or _today,   # 行情数据实际所属交易日
        "is_fresh": is_fresh,               # False=最新交易日数据还没发布(取到的是上一交易日)
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source, "state": state, "candidates": candidates,
        "fj": fj, "sat_gate": getattr(C, "SATELLITE_GATE", "classic"), "base": base,
    }

def build_data():
    src = C.DATA_SOURCE
    if src == "akshare":
        return build_with_akshare()
    if src == "tushare":
        return build_with_tushare()
    # auto
    try:
        if C.TUSHARE_TOKEN:
            return build_with_tushare()
    except Exception as e:
        print("[warn] Tushare 失败，转 AKShare：", e)
    return build_with_akshare()

def write_data_js(data):
    js = "window.STRATEGY_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n"
    with open(C.DATA_JS_PATH, "w", encoding="utf-8") as f:
        f.write(js)
    return C.DATA_JS_PATH

if __name__ == "__main__":
    t0 = time.time()
    data = build_data()
    p = write_data_js(data)
    print("✅ 数据已生成：%s" % p)
    print("   日期 %s ｜ 来源 %s ｜ 状态 %s/上限%d%% ｜ 候选 %d 只 ｜ 用时 %.1fs"
          % (data["date"], data["source"], data["state"]["tier"], data["state"]["cap"],
             len(data["candidates"]), time.time() - t0))
