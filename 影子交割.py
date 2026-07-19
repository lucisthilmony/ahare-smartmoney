# -*- coding: utf-8 -*-
"""
影子交割执行器（v6.4 P2 · 2026-07-10）——每交易日18:55 cron。

目的（外部审查P2）：失效判据不能靠实盘笔数（太慢且停做后死锁）。本脚本每日**机械模拟**
"系统规则本来会做的卫星交易"，形成两条主影子流和一条预注册研究流：
  A流 = A门执行卡（top-1修复型A候选）  C流 = classic执行卡（top-1候选，不加A门）
  R流 = A门内按固定SHA-256排序的确定性随机top-1（只检验评分排序，不参与失效判据）
规则与回测/实盘同源（策略规格.py）：次日收盘入场（高开放弃）、15日/MA10/2R卖半/收盘止损次日开盘出、
全成本、每流最多同时3只/每日开1只。影子流不依赖用户是否真的下单，停做期间照常运行→失效判据可自动恢复。

同时逐日记录核心四账户：现金/纯底仓/底仓+A流/底仓+C流，并另记底仓+R研究账户。每个账户独立记录现金、
底仓市值、卫星市值、真实费用、日收益和净值；原 R 字段保留给冻结期失效判据，另列实际R。

输出：影子交割.csv（平仓流水，失效判据v2的慢判据数据源）
      前向影子净值.csv（日频四账户净值及归因）
      影子决策快照.jsonl（每日输入/候选/选择的不可覆盖快照）
状态：.shadow_state.json（持仓、待成交队列和账户账本；原子写入并保留 .bak，禁止随意删除）
"""
import os, sys, json, time, hashlib, subprocess, datetime as dt
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import 策略规格 as SPEC
import shadow_ledger as LEDGER

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, ".shadow_state.json")
TRADES = os.path.join(HERE, "影子交割.csv")
NAV = os.path.join(HERE, "前向影子净值.csv")
EVENTS = os.path.join(HERE, "影子事件.csv")
BASE_TRADES = os.path.join(HERE, "影子底仓成交.csv")
DECISIONS = os.path.join(HERE, "影子决策快照.jsonl")
COMMIT_MARK = os.path.join(HERE, ".shadow_commit_pending.json")   # 半提交检测标记（复审四轮）
HOLD_MAX, MAX_POS = 15, SPEC.MAX_POS
INIT_CAPITAL = float(getattr(C, "DEFAULT_CAPITAL", 500000))
RISK_PCT = float(getattr(C, "RISK_PCT", 0.0075))
ETF_COST, REBAL_BAND = 0.0003, 0.05
THEME_CAP = 0.30
RANDOM_SEED = "20260719"

def log(m): print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)

def load_state():
    if not os.path.exists(STATE):
        st = {"A": {"open": [], "pending_entry": None, "pending_exit": []},
              "C": {"open": [], "pending_entry": None, "pending_exit": []}, "last_run": None}
        return LEDGER.ensure_state(st, INIT_CAPITAL)
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
        if st.get("recovery_required"):     # 复审二轮(0719)：恢复后必须人工确认，未确认前每次运行都停
            raise RuntimeError(
                "⛔ recovery_required 锁存在（%s 从备份恢复）。请核对：①state.last_run=%s 与 前向影子净值.csv 末行一致 "
                "②影子交割.csv 无晚于该日的平仓 ③持仓与快照吻合；确认后运行 `影子交割.py --confirm-recovery` 解锁。"
                % (st["recovery_required"].get("at"), st.get("last_run")))
        return LEDGER.ensure_state(st, INIT_CAPITAL)
    except Exception as e_main:
        if "recovery_required" in str(e_main):
            raise
        try:
            with open(STATE + ".bak", encoding="utf-8") as f:
                bak_st = json.load(f)
        except Exception as e_bak:
            raise RuntimeError("影子状态及备份均无法读取；为防重复建仓已停止："
                               f"main={e_main} | bak={e_bak}")
        # 复审修复(0719)：主损坏→①隔离损坏件留证 ②从.bak原子恢复主文件（不动.bak）③今日停跑待核对
        quarantine = STATE + ".corrupt-" + dt.datetime.now().strftime("%Y%m%d%H%M%S")
        os.replace(STATE, quarantine)
        bak_st["recovery_required"] = {"at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                       "quarantine": os.path.basename(quarantine)}   # 持久锁：自动续跑被禁止
        tmp = STATE + ".restore.tmp"
        with open(tmp, "w", encoding="utf-8") as dst:
            json.dump(bak_st, dst, ensure_ascii=False, indent=1); dst.flush(); os.fsync(dst.fileno())
        os.replace(tmp, STATE)
        raise RuntimeError(
            f"⚠️ 主状态损坏（已隔离为 {os.path.basename(quarantine)}），已从 .bak 原子恢复主文件，"
            f".bak 未被改动。恢复点 last_run={bak_st.get('last_run')}。已写入 recovery_required 持久锁——"
            f"核对后运行 `影子交割.py --confirm-recovery` 解锁，未解锁前每日任务都会停跑。")

def save_state(st):
    if os.path.exists(STATE):
        try:                                   # 复审修复(0719)：损坏的主文件禁止覆盖好备份
            with open(STATE, encoding="utf-8") as f:
                json.load(f)
            rotate_ok = True
        except Exception:
            rotate_ok = False
            log("⚠️ 现有主状态不是合法JSON，跳过轮换以保护 .bak")
        if rotate_ok:
            with open(STATE, "rb") as src, open(STATE + ".bak.tmp", "wb") as dst:
                dst.write(src.read()); dst.flush(); os.fsync(dst.fileno())
            os.replace(STATE + ".bak.tmp", STATE + ".bak")
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, STATE)

class QuoteAPIError(RuntimeError):
    """行情API失败（≠停牌/空数据）——调用方必须显式处理，禁止静默沿用旧价。"""

def daily_bars(code, start):
    ts = code + (".SH" if code.startswith("6") else ".SZ")
    try:
        df = P._ts_query("daily", ts_code=ts, start_date=start,
                         fields="trade_date,open,high,low,close")
    except Exception as e:
        raise QuoteAPIError(f"行情API失败 {ts}: {e}")   # 复审修复(0719)
    time.sleep(0.12)
    return df.sort_values("trade_date").reset_index(drop=True) if df is not None else None

def _atomic_csv(path, frame):
    tmp = path + ".tmp"
    frame.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, path)

def upsert_csv(row, path, keys):
    """幂等写 CSV；崩溃后重跑不会重复成交或净值行。"""
    old = pd.read_csv(path, dtype=str, encoding="utf-8-sig") if os.path.exists(path) else pd.DataFrame()
    new = pd.DataFrame([row])
    if len(old):
        mask = pd.Series(True, index=old.index)
        for k in keys:
            mask &= old.get(k, pd.Series("", index=old.index)).fillna("").astype(str) == str(row.get(k, ""))
        old = old.loc[~mask]
    columns = list(dict.fromkeys(list(old.columns) + list(new.columns)))
    _atomic_csv(path, pd.concat([old.reindex(columns=columns), new.reindex(columns=columns)], ignore_index=True))

_STAGED = []   # 复审三轮(0719)：运行内暂存全部CSV副作用；仅在提交点落盘——任何闸门失败=磁盘零变化

def _stage(row, path, keys):
    _STAGED.append((dict(row), path, tuple(keys)))

def _flush_staged():
    global _STAGED
    for row, path, keys in _STAGED:
        upsert_csv(row, path, keys)
    _STAGED = []

def _discard_staged():
    global _STAGED
    if _STAGED:
        log(f"（已丢弃 {len(_STAGED)} 条未落盘副作用——本次运行对磁盘零变化）")
    _STAGED = []

def append_trade(row):
    _stage(row, TRADES, ("流", "开仓日", "代码", "平仓日"))

def cost_frac(board, date):
    return 2 * SPEC.SLIP.get(board, 0.001) + 2 * SPEC.COMM_RATE + SPEC.stamp_rate(date)

def _board_rules():
    return {k: dict(v, slip=SPEC.SLIP.get(k, 0.001)) for k, v in C.BOARDS.items()}

def _fund_ts_code(code):
    code = str(code or "")
    return code + (".SH" if code.startswith(("5", "6")) else ".SZ")

_FUND_PRICE_CACHE = {}
def fund_close(code, date):
    key = (str(code), str(date))
    if key in _FUND_PRICE_CACHE:
        return _FUND_PRICE_CACHE[key]
    try:
        df = P._ts_query("fund_daily", ts_code=_fund_ts_code(code), start_date=date, end_date=date,
                         fields="trade_date,close")
        px = float(df.iloc[0]["close"]) if df is not None and len(df) else None
        if px is None:
            log(f"⚠️ ETF {code} 于 {date} 无收盘价（数据未发布或代码异常）")
    except Exception as e:
        px = None
        log(f"⚠️ ETF行情API失败 {code} {date}: {str(e)[:60]}")   # 复审修复(0719)：不再静默
    _FUND_PRICE_CACHE[key] = px
    return px

def _update_positions(stream, st, today):
    """先处理已有持仓；严格执行 T+1、收盘确认后次日开盘卖。"""
    s, account = st[stream], st["accounts"][stream]
    for pos in list(s["open"]):
        bars = daily_bars(pos["code"], pos["entry_date"])
        if bars is None or not len(bars):
            continue
        bars = bars[(bars["trade_date"] > pos["entry_date"]) & (bars["trade_date"] <= today)]
        new = bars.iloc[int(pos.get("hold", 0)):]
        for _, b in new.iterrows():
            pos["hold"] = int(pos.get("hold", 0)) + 1
            d = str(b["trade_date"])
            hi, cl, op = float(b["high"]), float(b["close"]), float(b["open"])
            pos["last_px"] = cl
            if pos.get("exit_next_open"):
                _close(stream, st, pos, d, op, pos["exit_next_open"])
                s["open"].remove(pos)
                break
            if not pos.get("half") and hi >= pos["target"]:
                held = int(pos.get("shares", 0))
                lot = int(C.BOARDS[pos["board"]]["lot"])
                half = ((held // 2) if pos["board"] == "star" else (held // 2) // lot * lot)
                LEDGER.sell_satellite(account, pos, half, pos["target"], d, _board_rules(),
                                      SPEC.COMM_RATE, SPEC.COMM_MIN, SPEC.stamp_rate)
                pos["half"] = True
            if cl < pos["stop"]:
                pos["exit_next_open"] = "止损(已减半)" if pos.get("half") else "止损"
                continue
            if pos.get("half"):
                ma10 = _ma10(pos["code"], d)
                if ma10 and cl < ma10:
                    pos["exit_next_open"] = "跌破MA10"
                    continue
            if pos["hold"] >= HOLD_MAX:
                _close(stream, st, pos, d, cl, "2R后时间止损" if pos.get("half") else "时间止损")
                s["open"].remove(pos)
                break

def _execute_pending_entry(stream, st, today):
    """成交此前决策：只允许使用决策日之后、今日之前或当日的第一根日线。"""
    s, account = st[stream], st["accounts"][stream]
    pe = s.get("pending_entry")
    if not pe:
        return
    try:
        bars = daily_bars(pe["code"], pe["decide_date"])
    except QuoteAPIError as e:
        log(f"  [{stream}] {e} → 排队保留，不计停牌重试")   # 复审修复(0719)
        return
    if bars is None or not len(bars):
        pe["tries"] = pe.get("tries", 0) + 1
        if pe["tries"] >= 3:
            _event(stream, pe, "停牌放弃"); s["pending_entry"] = None
        return
    prev = bars[bars["trade_date"] == pe["decide_date"]]
    nxt = bars[(bars["trade_date"] > pe["decide_date"]) & (bars["trade_date"] <= today)]
    if not len(prev) or not len(nxt):
        pe["tries"] = pe.get("tries", 0) + 1
        if pe["tries"] >= 3:
            _event(stream, pe, "停牌放弃"); s["pending_entry"] = None
        return
    s["pending_entry"] = None
    r0, r1 = prev.iloc[-1], nxt.iloc[0]
    gap = C.BOARDS[pe["board"]]["gap"]
    thr = P.limit_up_thr(pe["board"], str(r1["trade_date"]))
    if r0["close"] and r1["close"] / r0["close"] - 1 >= thr - 0.003:
        _event(stream, pe, "涨停未成交")
        return
    if not r0["close"] or r1["open"] / r0["close"] - 1 > gap:
        _event(stream, pe, "高开放弃")
        return
    entry, stop = float(r1["close"]), float(pe.get("stop_price") or 0)
    if entry <= stop:
        _event(stream, pe, "止损价无效")
        return
    compare_streams = ("C",) if stream == "A" else (("A",) if stream == "C" else ("A", "C"))
    other_codes = set()
    for other in compare_streams:
        other_codes |= {p["code"] for p in st[other]["open"]}
        if st[other].get("pending_entry"):
            other_codes.add(st[other]["pending_entry"]["code"])
    ov = pe["code"] in other_codes
    sizing = LEDGER.buy_satellite(
        account, s["open"], pe, entry, stop, str(r1["trade_date"]), pe.get("cap", 0),
        RISK_PCT, _board_rules(), C.EXPOSURE_20CM_CAP, THEME_CAP,
        SPEC.COMM_RATE, SPEC.COMM_MIN,
    )
    if not sizing:
        _event(stream, pe, "仓位不足放弃")
        return
    pos = dict(code=pe["code"], name=pe["name"], board=pe["board"], ind=pe.get("ind", ""),
               score=pe.get("score"), sec_rank=pe.get("sec_rank"), entry=entry, stop=stop,
               target=entry + 2 * (entry - stop), entry_date=str(r1["trade_date"]),
               half=False, hold=0, overlap=("Y" if ov else "N"), pnl_r=0.0, **sizing)
    s["open"].append(pos)
    log(f"  [{stream}] 影子入场 {pe['name']} @{entry:.2f} × {sizing['shares']}股" +
        ("（与另一流重叠）" if ov else ""))

def _queue_new_entry(stream, st, today, cands, can_open, cap):
    """返回实际动作记录（复审修复0719：快照必须与真实排队一致）。"""
    s = st[stream]
    held = {p["code"] for p in s["open"]}
    raw_pool = _eligible(cands, stream)
    held_excluded = [c.get("code") for c in raw_pool if c.get("code") in held]
    action = dict(queued_code=None, queued_name=None, held_excluded=held_excluded,
                  eligible_after_exclusion=len(raw_pool) - len(held_excluded))
    if not can_open:
        action["skip_reason"] = "state_can_open_false"; return action
    if len(s["open"]) >= MAX_POS:
        action["skip_reason"] = "portfolio_full"; return action
    if s.get("pending_entry") is not None:
        action["skip_reason"] = "pending_entry_exists"; return action
    pool = [c for c in raw_pool if c.get("code") not in held]
    if not pool:
        action["skip_reason"] = "all_eligible_held" if raw_pool else "no_eligible_candidate"
        return action
    c0 = _selected(pool, stream, today, already_eligible=True)
    s["pending_entry"] = dict(code=c0["code"], name=c0.get("name", ""), board=c0.get("board", "main"),
                              ind=c0.get("ind") or c0.get("sec", ""), score=c0.get("score"),
                              sec_rank=c0.get("sec_rank"), stop_price=c0.get("stop_price"),
                              cap=cap, decide_date=today, tries=0)
    action.update(queued_code=c0["code"], queued_name=c0.get("name", ""), skip_reason="queued")
    log(f"  [{stream}] 排队入场 {c0.get('name')}（明日收盘成交）")
    return action

def _ma10(code, upto):
    bars = daily_bars(code, (dt.datetime.strptime(upto, "%Y%m%d") - dt.timedelta(days=30)).strftime("%Y%m%d"))
    if bars is None:
        return None
    bars = bars[bars["trade_date"] <= upto]
    return float(bars["close"].tail(10).mean()) if len(bars) >= 10 else None

def _event(stream, pe, kind):
    """不可成交类事件（涨停未成交/停牌放弃/高开放弃）——评估可达性偏差用。"""
    row = {"流": stream, "决策日": pe.get("decide_date"), "代码": pe.get("code"),
           "名称": pe.get("name"), "事件": kind}
    _stage(row, EVENTS, ("流", "决策日", "代码", "事件"))
    log(f"  [{stream}] {kind}: {pe.get('name')}")

def _close(stream, st, pos, date, px, reason):
    account = st["accounts"][stream]
    LEDGER.sell_satellite(account, pos, int(pos.get("shares", 0)), px, date, _board_rules(),
                          SPEC.COMM_RATE, SPEC.COMM_MIN, SPEC.stamp_rate)
    cost = cost_frac(pos["board"], date)
    risk = pos["entry"] - pos["stop"]
    if pos.get("half"):
        gross = 0.5 * (pos["target"] - pos["entry"]) + 0.5 * (px - pos["entry"])
    else:
        gross = px - pos["entry"]
    r = (gross - pos["entry"] * cost) / risk if risk > 0 else 0.0
    actual_pnl = (float(pos.get("sale_proceeds", 0)) - float(pos.get("cost_basis", 0))
                  if pos.get("accounted", True) else None)
    risk_amt = float(pos.get("actual_risk_amt", 0) or 0)
    actual_r = actual_pnl / risk_amt if actual_pnl is not None and risk_amt else None
    st[stream]["cum_r"] = float(st[stream].get("cum_r", 0)) + r
    if actual_r is not None:
        st[stream]["cum_actual_r"] = float(st[stream].get("cum_actual_r", 0)) + actual_r
    append_trade({"流": stream, "开仓日": pos["entry_date"], "代码": pos["code"], "名称": pos["name"],
                  "入场": round(pos["entry"], 2), "止损": round(pos["stop"], 2),
                  "平仓日": date, "平仓价": round(px, 2), "原因": reason, "R": round(r, 3),
                  "重叠": pos.get("overlap", ""), "股数": pos.get("entry_shares", 0),
                  "实际买入价": round(float(pos.get("buy_px", 0)), 4) if pos.get("accounted", True) else None,
                  "实际末次卖价": round(float(pos.get("last_sell_px", 0)), 4) if pos.get("accounted", True) else None,
                  "实际盈亏": round(actual_pnl, 2) if actual_pnl is not None else None,
                  "实际R": round(actual_r, 3) if actual_r is not None else None})
    log(f"  [{stream}] 影子平仓 {pos['name']} {reason} R={r:+.2f}")

def _eligible(cands, stream):
    if stream in ("A", "R"):
        return [c for c in cands if SPEC.satellite_gate(c, "codexA") is True]
    return list(cands)

def _random_key(candidate, decision_date):
    raw = f"{RANDOM_SEED}|{decision_date}|{candidate.get('code', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _selected(cands, stream, decision_date, already_eligible=False):
    pool = list(cands) if already_eligible else _eligible(cands, stream)
    if not pool:
        return None
    if stream == "R":
        return min(pool, key=lambda c: _random_key(c, decision_date))
    return max(pool, key=lambda c: c.get("score", 0))

def _file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def _strategy_version():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=HERE, text=True, stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=HERE,
            text=True, stderr=subprocess.DEVNULL,
        ).strip())
        return commit + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"

def _decision_record(today, stream, cands, action):
    """复审修复(0719)：原始排名与最终实际动作并存，快照与真实排队不再可能背离。"""
    pool = _eligible(cands, stream)
    if stream == "R":
        ranked = sorted(pool, key=lambda c: _random_key(c, today))
        rank_rule = f"sha256:{RANDOM_SEED}"
    else:
        ranked = sorted(pool, key=lambda c: c.get("score", 0), reverse=True)
        rank_rule = "score_desc"
    return {
        "decision_id": f"{today}-{stream}-v2",
        "stream": stream,
        "rank_rule": rank_rule,
        "eligible_count": len(ranked),
        "candidate_rank": [{"rank": i + 1, "code": c.get("code"), "score": c.get("score"),
                            "rank_hash": _random_key(c, today) if stream == "R" else None}
                           for i, c in enumerate(ranked)],
        "raw_top1": (ranked[0].get("code") if ranked else None),
        "actual": action,                       # 实际排队结果（含held_excluded与最终skip_reason）
        "skip_reason": (action or {}).get("skip_reason", ""),
    }

def check_snapshot_conflict(today, raw_text):
    """前置检查（复审修复0719）：同日已有快照→输入/代码变化则停止；一致则返回True表示今日免写。"""
    if not os.path.exists(DECISIONS):
        return False
    data_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    source_hashes = {
        os.path.basename(__file__): _file_sha256(__file__),
        os.path.basename(LEDGER.__file__): _file_sha256(LEDGER.__file__),
        os.path.basename(SPEC.__file__): _file_sha256(SPEC.__file__),
    }
    with open(DECISIONS, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            old = json.loads(line)
            if old.get("date") == today:
                if old.get("data_sha256") != data_hash:
                    raise RuntimeError("同日 data.js 已变化；保留既有影子决策快照并停止执行")
                if old.get("source_hashes") != source_hashes:
                    raise RuntimeError("同日策略代码已变化；保留既有影子决策快照并停止执行")
                return True
    return False

def write_decision_snapshot(today, data, raw_text, actions, skip_write=False):
    """写入含"原始排名+实际动作"的当日快照（在全部排队完成后调用）。"""
    if skip_write:
        return
    cands = data.get("candidates") or []
    state = data.get("state") or {}
    source_hashes = {
        os.path.basename(__file__): _file_sha256(__file__),
        os.path.basename(LEDGER.__file__): _file_sha256(LEDGER.__file__),
        os.path.basename(SPEC.__file__): _file_sha256(SPEC.__file__),
    }
    data_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    payload = {
        "date": today,
        "data_date": data.get("data_date"),
        "generated_at": data.get("generated_at"),
        "state": state,
        "base": data.get("base") or {},
        "candidate_count": len(cands),
        "candidates": cands,
        "decisions": {s: _decision_record(today, s, cands, actions.get(s)) for s in ("A", "C", "R")},
        "data_sha256": data_hash,
        "input_hash": data_hash,
        "strategy_commit": _strategy_version(),
        "source_hashes": source_hashes,
        "spec_version": "v6.4.1",
        "random_seed": RANDOM_SEED,
        "rule_version": "v6.4.1-shadow-ledger-v2+rank-r1",
        "rerun_id": f"{today}-scheduled",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    with open(DECISIONS, "a", encoding="utf-8") as f:
        f.write(encoded + "\n"); f.flush(); os.fsync(f.fileno())

def rebalance_base_accounts(st, base, today):
    for name in ("base", "A", "C", "R"):
        trades = LEDGER.rebalance_base(st["accounts"][name], base, today, fund_close,
                                       ETF_COST, REBAL_BAND)
        for t in trades:
            row = {"账户": name, "日期": t["date"], "方向": t["side"], "代码": t["code"],
                   "股数": t["shares"], "价格": round(t["price"], 4), "费用": round(t["fee"], 2)}
            _stage(row, BASE_TRADES, ("账户", "日期", "方向", "代码"))

def write_nav(st, state, base, today, stale_codes=None):
    b = LEDGER.snapshot_account(st["accounts"]["base"], [], INIT_CAPITAL)
    a = LEDGER.snapshot_account(st["accounts"]["A"], st["A"]["open"], INIT_CAPITAL)
    c = LEDGER.snapshot_account(st["accounts"]["C"], st["C"]["open"], INIT_CAPITAL)
    r = LEDGER.snapshot_account(st["accounts"]["R"], st["R"]["open"], INIT_CAPITAL)
    row = {
        "date": today, "tier": state.get("tier"), "cap": state.get("cap"),
        "base_inst": base.get("etf"), "base_target_w": base.get("weight"),
        "cash_nav": 1.0,
        "base_nav": round(b["nav"], 8), "base_equity": round(b["equity"], 2),
        "base_cash": round(b["cash"], 2), "base_mv": round(b["base_mv"], 2),
        "base_actual_w": round(b["base_weight"], 6), "base_daily_ret": round(b["daily_return"], 8),
        "base_dd": round(b["drawdown"], 8),
        "A_nav": round(a["nav"], 8), "A_equity": round(a["equity"], 2),
        "A_cash": round(a["cash"], 2), "A_base_mv": round(a["base_mv"], 2),
        "A_sat_mv": round(a["sat_mv"], 2), "A_base_w": round(a["base_weight"], 6),
        "A_sat_w": round(a["sat_weight"], 6), "A_daily_ret": round(a["daily_return"], 8),
        "A_dd": round(a["drawdown"], 8),
        "A_open": len(st["A"]["open"]), "A_cum_R": round(float(st["A"].get("cum_r", 0)), 4),
        "A_cum_actual_R": round(float(st["A"].get("cum_actual_r", 0)), 4),
        "C_nav": round(c["nav"], 8), "C_equity": round(c["equity"], 2),
        "C_cash": round(c["cash"], 2), "C_base_mv": round(c["base_mv"], 2),
        "C_sat_mv": round(c["sat_mv"], 2), "C_base_w": round(c["base_weight"], 6),
        "C_sat_w": round(c["sat_weight"], 6), "C_daily_ret": round(c["daily_return"], 8),
        "C_dd": round(c["drawdown"], 8),
        "C_open": len(st["C"]["open"]), "C_cum_R": round(float(st["C"].get("cum_r", 0)), 4),
        "C_cum_actual_R": round(float(st["C"].get("cum_actual_r", 0)), 4),
        "R_nav": round(r["nav"], 8), "R_equity": round(r["equity"], 2),
        "R_cash": round(r["cash"], 2), "R_base_mv": round(r["base_mv"], 2),
        "R_sat_mv": round(r["sat_mv"], 2), "R_base_w": round(r["base_weight"], 6),
        "R_sat_w": round(r["sat_weight"], 6), "R_daily_ret": round(r["daily_return"], 8),
        "R_dd": round(r["drawdown"], 8), "R_open": len(st["R"]["open"]),
        "R_cum_R": round(float(st["R"].get("cum_r", 0)), 4),
        "R_cum_actual_R": round(float(st["R"].get("cum_actual_r", 0)), 4),
        "accounting_start": st.get("accounting_start"), "state_version": st.get("state_version"),
        "stale_px_codes": "|".join(stale_codes or []),   # 复审二轮(0719)：停牌沿用旧价的持仓，显式可见
    }
    upsert_csv(row, NAV, ("date",))

def _read_snapshot(today):
    if not os.path.exists(DECISIONS):
        return {}
    with open(DECISIONS, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                if obj.get("date") == today:
                    return obj
    return {}

def confirm_recovery(force=False):
    """核对通过才解锁；发现问题保持锁定（复审三轮）。--force-unlock=人工对账后强制解锁。"""
    with open(STATE, encoding="utf-8") as f:
        st = json.load(f)
    lock = st.get("recovery_required")
    if not lock:
        print("无 recovery_required 锁，无需解锁。"); return
    last = st.get("last_run")
    problems = []
    if os.path.exists(TRADES):
        t = pd.read_csv(TRADES, dtype=str)
        late = t[t["平仓日"].astype(str) > str(last or "")]
        if len(late):
            problems.append(f"交割表存在晚于恢复点({last})的平仓 {len(late)} 笔——存在重放/丢单风险，请先人工比对")
    if os.path.exists(NAV):
        n = pd.read_csv(NAV, dtype=str)
        if len(n) and str(n.iloc[-1]["date"]) != str(last):
            problems.append(f"NAV末行({n.iloc[-1]['date']})与恢复点last_run({last})不一致")
    for msg in problems:
        print("⚠️", msg)
    if problems and not force:
        print(f"⛔ 核对发现 {len(problems)} 项问题：**保持锁定，状态未改动**。"
              f"请人工处理后重跑本命令；确已人工对账且接受风险，可用 --force-unlock 强制解锁。")
        return False
    print(("检查通过，" if not problems else "--force-unlock 已确认人工对账，") + "解锁 recovery_required。")
    st.pop("recovery_required", None)
    save_state(st)
    return True

def main(today=None):
    if os.path.exists(COMMIT_MARK):
        try:
            with open(COMMIT_MARK, encoding="utf-8") as f:
                mk = json.load(f)
        except Exception:
            mk = {}
        log(f"⛔ 检测到上次提交未完成（COMMIT_MARK {mk.get('date')} {mk.get('at')}）——磁盘可能半提交。"
            f"请逐一核对：①影子底仓成交.csv ②影子事件.csv ③影子决策快照.jsonl ④前向影子净值.csv ⑤.shadow_state.json，"
            f"与该日预期一致后删除 {os.path.basename(COMMIT_MARK)}，幂等补跑会去重。未删除前每日停跑。")
        return
    _discard_staged()   # 复审三轮：清理可能的残留暂存
    today = today or dt.date.today().strftime("%Y%m%d")   # 可注入：测试/补跑用
    if today not in set(P._recent_trade_dates(8)):
        log("非交易日，跳过。"); return
    try:
        with open(C.DATA_JS_PATH, encoding="utf-8") as f:
            txt = f.read()
        d = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
    except Exception as e:
        log(f"读data.js失败：{e}"); return
    if (d.get("data_date") or "").replace("-", "") != today:
        log("data.js非当日数据（18:30刷新未跑？），跳过以防错位。"); return
    try:
        st = load_state()
    except Exception as e:
        log(str(e)); return
    if st.get("last_run") == today:
        log("今日已运行过，跳过（幂等）。"); return
    state = d.get("state") or {}
    cands = d.get("candidates") or []
    base = d.get("base") or {}
    if not st.get("accounting_start"):
        st["accounting_start"] = today
    try:
        snapshot_done = check_snapshot_conflict(today, txt)
    except Exception as e:
        log(f"影子决策快照冲突：{e}"); return
    # 复审修复(0719)：价格预检失败关闭——目标ETF或任一账户持有ETF当日无价 → 今日不交易不记账
    need_px = set()
    if base.get("etf") and (base.get("weight") or 0) > 0:
        need_px.add(str(base["etf"]))
    for name in ("base", "A", "C", "R"):
        h = (st.get("accounts", {}).get(name) or {}).get("base")
        if h and h.get("shares", 0) > 0:
            need_px.add(str(h["code"]))
    missing = [c for c in sorted(need_px) if fund_close(c, today) is None]
    if missing:
        log(f"⛔ 失败关闭：底仓ETF当日收盘价缺失 {missing}——今日不记账不交易（幂等，修复后可当日手动重跑）")
        for c in missing:
            upsert_csv({"流": "base", "决策日": today, "代码": c, "名称": "底仓ETF", "事件": "行情缺失-失败关闭"},
                       EVENTS, ("流", "决策日", "代码", "事件"))   # 无状态变更前的早退：直接落盘
        return
    stale_codes = []
    # 复审二轮(0719)：个股持仓预检——当日无K线（data.js已确认今日全市场数据存在→视为停牌）
    # 允许沿用旧价标记，但必须显式：事件表留痕 + NAV行stale_px_codes列。API失败则中止（QuoteAPIError冒泡）。
    for stream in ("A", "C", "R"):
        for pos in st[stream]["open"]:
            bars = daily_bars(pos["code"], pos["entry_date"])
            if bars is None or today not in set(bars["trade_date"].astype(str)):
                stale_codes.append(pos["code"])
                _stage({"流": stream, "决策日": today, "代码": pos["code"], "名称": pos.get("name", ""),
                        "事件": "当日无K线-沿用旧价(原因待确认)"}, EVENTS, ("流", "决策日", "代码", "事件"))
    if stale_codes:
        log(f"⚠️ 个股当日无K线：{stale_codes}——按旧价标记并显式记录（原因待确认：停牌/退市/数据缺失）")
    # 时间顺序与组合回测一致：已有仓先出场 → 底仓调仓 → 昨日信号尾盘入场 → 今日信号排队。
    for stream in ("A", "C", "R"):
        _update_positions(stream, st, today)
    rebalance_base_accounts(st, base, today)
    actions = {}
    for stream in ("A", "C", "R"):
        _execute_pending_entry(stream, st, today)
        actions[stream] = _queue_new_entry(stream, st, today, cands,
                                           bool(state.get("can_open")), state.get("cap", 0))
    try:
        if snapshot_done:
            # 复审三轮(0719)：补跑必须与既有快照的**完整actual**逐流一致（不只queued_code）；
            # 背离→丢弃全部暂存副作用（交割/事件/底仓成交均未落盘）、不写NAV、不推进last_run、不保存状态。
            prior = _read_snapshot(today)
            for sname in ("A", "C", "R"):
                old_a = (prior.get("decisions", {}).get(sname, {}) or {}).get("actual") or {}
                new_a = actions.get(sname) or {}
                if old_a != new_a:
                    log(f"⛔ 补跑背离：快照[{sname}]actual={old_a} 而本次重算={new_a}——状态漂移，停止执行，"
                        f"请人工核对 .shadow_state.json 与快照后处理")
                    _discard_staged()
                    return
    except Exception as e:
        log(f"补跑一致性检查失败：{e}"); _discard_staged(); return
    try:
        LEDGER.validate_state(st)
    except Exception as e:
        log(str(e)); _discard_staged(); return
    # ---- 提交点：以上全部闸门通过后才允许触盘 ----
    # 复审四轮(0719)如实声明：提交阶段是多文件顺序写、非原子事务；故障依赖幂等补跑。
    # COMMIT_MARK=半提交检测：提交前落标记、五步全成后删除；下次运行见标记即停，强制五类产物核对。
    with open(COMMIT_MARK, "w", encoding="utf-8") as f:
        json.dump({"date": today, "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f)
        f.flush(); os.fsync(f.fileno())
    try:
        _flush_staged()
        if not snapshot_done:
            write_decision_snapshot(today, d, txt, actions)
        write_nav(st, state, base, today, stale_codes)
        st["last_run"] = today
        save_state(st)
    except Exception as e:
        log(f"⛔ 提交失败（COMMIT_MARK保留）：{e}——磁盘可能处于半提交。请核对五类产物"
            f"（底仓成交/事件/快照/NAV/状态）后删除 {os.path.basename(COMMIT_MARK)} 再补跑。")
        return
    os.remove(COMMIT_MARK)
    log(f"影子执行完成：A流{len(st['A']['open'])} C流{len(st['C']['open'])} "
        f"R流{len(st['R']['open'])}；核心四账户+R研究账户净值已记账")

if __name__ == "__main__":
    if "--confirm-recovery" in sys.argv:
        confirm_recovery(force=("--force-unlock" in sys.argv))
    else:
        main()
