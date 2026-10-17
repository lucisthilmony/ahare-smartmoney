# -*- coding: utf-8 -*-
"""次新质量成长策略回放 v2（预注册v2 2026-08-04；评审16项修订已全部落地；冻结后一次通过）。

用法：./.venv/bin/python 研究_次新策略.py [outsample|bridge|insample|both]
     （both=三窗口全跑；bridge为强制披露窗不作判据）
数据：研究_次新收集.py 四个pkl；个股价格执行器内直拉（.cixin_px.pkl增量缓存，含退市股）。
输出：预注册§八全部判据指标 + 强制披露项；明细落 次新策略_事件明细_<窗口>.csv。
"""
import os, sys, time, pickle, hashlib
import datetime as dt
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
import pipeline as P
import pandas as pd
import numpy as np

# ── 预注册v2参数（冻结）──
WINDOWS = {
    "outsample": ("201901", "202306", "20240630"),   # 决策月起,止,结算截止（穿越2024年初崩盘）
    "bridge":    ("202307", "202405", "20260630"),   # 强制披露窗，不作判据
    "insample":  ("202406", "202603", "20260630"),
}
ENTRY_MIN, ENTRY_MAX, GRAD = 126, 504, 756
MV_CAP, MV_CAP_S1 = 600000.0, 1000000.0              # total_mv万元：60亿主判 / 100亿敏感性
PE_CAP = 40.0
COMM, SLIP = 0.00025, 0.001
N_CTRL, MAX_DEFER = 5, 20
SEED = "20260804"
ERAS = [("核准", "201901", "202008"), ("双轨", "202009", "202302"), ("全注册", "202303", "202612")]

def log(*a): print(*a, flush=True)

def stamp_tax(d): return 0.0005 if d > "20230827" else 0.001

def limit_pct(board, d):
    """(板块,日期)限幅表；判定阈值=限幅×0.95"""
    if board == "star": return 0.20
    if board == "chinext": return 0.20 if d >= "20200824" else 0.10
    return 0.10

# ── 数据装载 ──
def load_static():
    sb = pickle.load(open(".cixin_universe.pkl", "rb"))
    fina = pickle.load(open(".cixin_fina_v2.pkl", "rb"))
    db = pickle.load(open(".cixin_dailybasic.pkl", "rb"))
    idx = pickle.load(open(".cixin_index.pkl", "rb"))
    cal_df = P._ts_query("trade_cal", exchange="SSE", start_date="20150101",
                         end_date="20260630", is_open="1")
    cal_full = sorted(cal_df["cal_date"].tolist())
    return sb, fina, db, idx, cal_full

PX_PKL = ".cixin_px.pkl"
_px = pickle.load(open(PX_PKL, "rb")) if os.path.exists(PX_PKL) else {}
_px_dirty = [0]
def prices(code):
    """个股复权价格序列（daily close/open × adj_factor），含退市股；增量缓存"""
    if code not in _px:
        try:
            d = P._ts_query("daily", ts_code=code, start_date="20181201", end_date="20260630")
            a = P._ts_query("adj_factor", ts_code=code, start_date="20181201", end_date="20260630")
            if d is None or len(d) == 0:
                _px[code] = None
            else:
                d = d.drop_duplicates("trade_date", keep="last").sort_values("trade_date").set_index("trade_date")
                af = None
                if a is not None and len(a):
                    af = (a.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
                          .set_index("trade_date")["adj_factor"].astype(float).reindex(d.index).ffill())
                f = af if af is not None and not af.isna().all() else pd.Series(1.0, index=d.index)
                _px[code] = pd.DataFrame({
                    "aopen": d["open"].astype(float) * f,
                    "aclose": d["close"].astype(float) * f,
                    "pct": d["close"].astype(float) / d["pre_close"].astype(float) - 1
                           if "pre_close" in d else d["close"].astype(float).pct_change()})
            time.sleep(0.12)
        except Exception:
            _px[code] = None
            time.sleep(0.6)
        _px_dirty[0] += 1
        if _px_dirty[0] % 200 == 0:
            pickle.dump(_px, open(PX_PKL, "wb"))
            log("  …价格缓存 %d 只" % len(_px))
    return _px[code]

# ── PIT财务（首次披露版本锁）──
_fina_first = {}
def fina_first(fina, code):
    if code not in _fina_first:
        f = fina.get(code)
        if f is None or len(f) == 0:
            _fina_first[code] = None
        else:
            f = f.dropna(subset=["ann_date", "end_date"])
            first_ann = f.groupby("end_date")["ann_date"].transform("min")
            _fina_first[code] = f[f["ann_date"] == first_ann]   # 同ann_date多版本全保留→判定取保守
    return _fina_first[code]

def _pos_all(rows, col):
    v = pd.to_numeric(rows[col], errors="coerce")
    return len(v) > 0 and v.notna().all() and (v > 0).all()    # 多版本全过才算过（保守）

def pit_pass(fina, code, dec):
    f = fina_first(fina, code)
    if f is None:
        return False
    f = f[f["ann_date"] <= dec]
    if len(f) == 0:
        return False
    latest_ed = f["end_date"].max()
    latest = f[f["end_date"] == latest_ed]
    anns = f[f["end_date"].str.endswith("1231")]
    if len(anns) == 0:
        return False
    ann_ed = anns["end_date"].max()
    ann = anns[anns["end_date"] == ann_ed]
    return (_pos_all(latest, "netprofit_margin") and _pos_all(ann, "netprofit_margin")
            and _pos_all(latest, "profit_dedt") and _pos_all(ann, "profit_dedt")
            and _pos_all(latest, "or_yoy") and _pos_all(ann, "or_yoy")
            and _pos_all(latest, "op_yoy")
            and _pos_all(latest, "netprofit_yoy") and _pos_all(ann, "netprofit_yoy"))

# ── 执行原语 ──
def open_limit_up(code, board, entry_dt):
    p = prices(code)
    if p is None or entry_dt not in p.index:
        return True
    i = p.index.get_loc(entry_dt)
    if i == 0:
        return True
    o, pc = float(p["aopen"].iloc[i]), float(p["aclose"].iloc[i - 1])
    if pd.isna(o) or pd.isna(pc) or pc <= 0:
        return True
    return (o / pc - 1) >= limit_pct(board, entry_dt) * 0.95

def sellable_exit(code, board, cal, want_i, sb_row):
    """卖出可达：跌停日顺延≤20交易日；退市按最后可得价×0.8。返回(实际日, 复权成交价, 标记)"""
    p = prices(code)
    if p is None:
        return None, None, "无行情"
    for k in range(MAX_DEFER + 1):
        i = want_i + k
        if i >= len(cal):
            break
        d_ = cal[i]
        if d_ not in p.index:
            if d_ > p.index.max():    # 已无后续行情：退市/长停路径
                last = p["aclose"].dropna()
                if len(last) == 0:
                    return None, None, "无行情"
                return p.index[-1], float(last.iloc[-1]) * 0.8, "退市折价20%"
            continue                   # 停牌顺延
        row = p.loc[d_]
        thr = limit_pct(board, d_) * 0.95
        if not pd.isna(row["pct"]) and row["pct"] <= -thr:
            continue                   # 跌停封板顺延
        return d_, float(row["aclose"]), ("顺延%d" % k if k else "")
    i = min(want_i + MAX_DEFER, len(cal) - 1)
    d_ = cal[i]
    px_ = p["aclose"].reindex([d_]).ffill()
    v = p[p.index <= d_]["aclose"].dropna()
    if len(v) == 0:
        return None, None, "无行情"
    return d_, float(v.iloc[-1]), "强制20日"

def entry_price(code, entry_dt):
    p = prices(code)
    if p is None or entry_dt not in p.index:
        return None
    o = float(p.loc[entry_dt, "aopen"])
    return None if (pd.isna(o) or o <= 0) else o * (1 + SLIP)

def event_return(code, board, cal, cal_ix, entry_dt, exit_want_i, sell_half=False):
    """费后事件收益；sell_half=翻倍卖半。返回(ret, mdd, flags, 卖半触发?)"""
    e = entry_price(code, entry_dt)
    if e is None:
        return None
    d_exit, xp, flag = sellable_exit(code, board, cal, exit_want_i, None)
    if xp is None:
        return None
    p = prices(code)
    path = p["aclose"][(p.index >= entry_dt) & (p.index <= d_exit)].dropna()
    if len(path) == 0:
        return None
    mdd = float((path / path.cummax() - 1).min())
    tax = stamp_tax(d_exit)
    if not sell_half:
        ret = (xp * (1 - SLIP)) / e * (1 - COMM - tax) * (1 - COMM) - 1
        return ret, mdd, flag, False
    dbl = path[path / e >= 2.0]
    if len(dbl) == 0:
        ret = (xp * (1 - SLIP)) / e * (1 - COMM - tax) * (1 - COMM) - 1
        return ret, mdd, flag, False
    d_dbl = dbl.index[0]
    # 卖半日同样受跌停顺延约束
    d_h, hp, _ = sellable_exit(code, board, cal, cal_ix[d_dbl], None)
    if hp is None:
        d_h, hp = d_dbl, float(path.loc[d_dbl])
    half_out = 0.5 * (hp * (1 - SLIP)) / e * (1 - COMM - stamp_tax(d_h))
    days_left = max(0, cal_ix.get(d_exit, 0) - cal_ix.get(d_h, 0))
    half_cash = half_out * (1 + 0.018 / 244) ** days_left
    half_hold = 0.5 * (xp * (1 - SLIP)) / e * (1 - COMM - tax)
    return (half_cash + half_hold) * (1 - COMM) - 1, mdd, flag, True

# ── 主流程 ──
def run_window(wname, sb, fina, db, idxpk, cal_full):
    m0, m1, settle_end = WINDOWS[wname]
    cal = [d for d in cal_full if "20181201" <= d <= settle_end]
    cal_ix = {d: i for i, d in enumerate(cal)}
    li_full_ix = {d: i for i, d in enumerate(cal_full)}
    sb2 = sb.set_index("ts_code")
    list_date = sb2["list_date"].to_dict()
    board = {c: P.board_of(c.split(".")[0]) for c in sb2.index}
    def age(code, d_):
        ld = list_date.get(code)
        if not ld or ld > d_:
            return -1
        if ld < "20150101":
            return 10 ** 6          # 2015前上市=确定成熟（修复：原-1会把老股逐出对照池）
        return li_full_ix.get(d_, -1) - min(li_full_ix.get(ld, 10 ** 9),
                                            len([x for x in cal_full if x < ld]))
    import 时点数据 as PIT

    month_ends = pd.Series(cal_full).groupby(pd.Series(cal_full).str[:6]).max()
    dec_dates = [d for ym, d in month_ends.items() if m0 <= ym <= m1]
    settle_i = cal_ix[max(d for d in cal if d <= settle_end)]

    # 入场筛选（V0/V1；同股每窗一次，涨停开盘可下月重试）
    entries = {"V0": [], "V1": []}
    held = {"V0": set(), "V1": set()}
    excl = {"pe": 0, "fina": 0, "st": 0, "涨停开盘": 0}
    sens = {"mv100": 0, "mvq20": 0}
    for dec in dec_dates:
        snap = db.get(dec)
        if snap is None or len(snap) == 0:
            continue
        snap = snap[~snap.ts_code.str.endswith(".BJ")].set_index("ts_code")
        mvq20 = snap["total_mv"].quantile(0.20)
        i_dec = cal_ix.get(dec)
        if i_dec is None or i_dec + 1 > settle_i:
            continue
        entry_dt = cal[i_dec + 1] if i_dec + 1 < len(cal) else None
        if entry_dt is None:
            continue
        for code in snap.index:
            a = age(code, dec)
            if not (ENTRY_MIN <= a <= ENTRY_MAX):
                continue
            if PIT.st_at(code, dec):
                excl["st"] += 1
                continue
            mv = snap.loc[code, "total_mv"]
            if pd.isna(mv):
                continue
            if float(mv) <= MV_CAP_S1: sens["mv100"] += 1
            if float(mv) <= mvq20: sens["mvq20"] += 1
            if float(mv) > MV_CAP:
                continue
            base = dict(dec=dec, entry=entry_dt, code=code, age=a, mv=float(mv))
            if code not in held["V0"]:
                if open_limit_up(code, board.get(code), entry_dt):
                    pass
                else:
                    entries["V0"].append(dict(base))
                    held["V0"].add(code)
            pe_v = snap.loc[code, "pe_ttm"]
            if pd.isna(pe_v) or not (0 < float(pe_v) <= PE_CAP):
                excl["pe"] += 1
                continue
            if not pit_pass(fina, code, dec):
                excl["fina"] += 1
                continue
            if code in held["V1"]:
                continue
            if open_limit_up(code, board.get(code), entry_dt):
                excl["涨停开盘"] += 1
                continue
            entries["V1"].append(dict(base, pe=float(pe_v)))
            held["V1"].add(code)
    log(f"\n[{wname}] 决策月{len(dec_dates)} | V1入场{len(entries['V1'])} V0入场{len(entries['V0'])} | "
        f"剔除{excl} | 敏感性计数(≤100亿:{sens['mv100']},≤20分位:{sens['mvq20']})")

    idx_tr = idxpk.get("H00852.CSI", idxpk["000852.SH"]).set_index("trade_date")["close"].astype(float)

    _mature_cache = {}
    def mature_pool(dec):
        """成熟池（同决策日复用）：非BJ、非次新(age>GRAD)、非时点ST，带board/ind/市值。"""
        if dec not in _mature_cache:
            snap = db.get(dec)
            s = snap[~snap.ts_code.str.endswith(".BJ")].dropna(subset=["total_mv"]).copy()
            s = s[s.ts_code.map(lambda c: age(c, dec) > GRAD)]
            s = s[~s.ts_code.map(lambda c: PIT.st_at(c, dec))]
            s["board"] = s.ts_code.map(lambda c: board.get(c))
            s["ind"] = s.ts_code.map(lambda c: PIT.ind_at(c, dec))
            _mature_cache[dec] = s
        return _mature_cache[dec]

    def ctrl_codes(ev):
        s = mature_pool(ev["dec"])
        s = s[s.board == board.get(ev["code"])]
        ind = PIT.ind_at(ev["code"], ev["dec"])
        relaxed = ind is None
        s2 = s[s.ind == ind] if ind else s
        if len(s2) < 10:
            s2, relaxed = s, True
        s2 = s2.copy()
        s2["q"] = pd.qcut(s2.total_mv, 5, labels=False, duplicates="drop")
        try:
            evq = int(pd.cut([ev["mv"]], pd.qcut(s2.total_mv, 5, retbins=True, duplicates="drop")[1],
                             labels=False, include_lowest=True)[0])
        except Exception:
            evq = 0
        pool = sorted(s2[s2.q == evq].ts_code.tolist())
        picks, used = [], set()
        k = 0
        while len(picks) < N_CTRL and k < N_CTRL * 8 and len(used) < len(pool):
            h = int(hashlib.sha256(("%s|%s|%s|%d" % (SEED, ev["dec"], ev["code"], k)).encode()).hexdigest(), 16)
            j = h % len(pool)
            probes = 0
            while pool[j] in used and probes <= len(pool):
                j = (j + 1) % len(pool)
                probes += 1
            if pool[j] in used:
                break                     # 池耗尽（修复：原实现此处死循环）
            c = pool[j]
            used.add(c)
            k += 1
            if open_limit_up(c, board.get(c), ev["entry"]):
                continue
            picks.append(c)
        return picks, relaxed

    def horizon_exit_i(ev, months):
        i0 = cal_ix[ev["entry"]]
        i_grad = i0 + (GRAD - ev["age"])
        return min(i0 + months * 21, i_grad, settle_i)

    rows = []
    for tag in ("V1", "V0"):
        for ev in entries[tag]:
            rec = dict(ev, var=tag)
            i0 = cal_ix[ev["entry"]]
            rec["full12"] = (i0 + 252 <= settle_i)
            ctrls, relaxed = ctrl_codes(ev)
            rec["ctrl_n"], rec["ctrl_relaxed"] = len(ctrls), relaxed
            for m in (1, 3, 6, 12, 24):
                xi = horizon_exit_i(ev, m)
                r = event_return(ev["code"], board.get(ev["code"]), cal, cal_ix, ev["entry"], xi)
                rec["ret_%dm" % m] = None if r is None else round(r[0] * 100, 2)
                if r is not None and ctrls:
                    crs = [event_return(c, board.get(c), cal, cal_ix, ev["entry"], xi) for c in ctrls]
                    crs = [x[0] for x in crs if x is not None]
                    rec["exc_%dm" % m] = round((r[0] - float(np.mean(crs))) * 100, 2) if crs else None
                else:
                    rec["exc_%dm" % m] = None
                if m == 12:
                    d0, d1 = ev["entry"], cal[xi]
                    if d0 in idx_tr.index and d1 in idx_tr.index:
                        rec["exc_idx_12m"] = None if r is None else round(
                            (r[0] - (float(idx_tr.loc[d1]) / float(idx_tr.loc[d0]) - 1)) * 100, 2)
            if tag == "V1":
                gi = horizon_exit_i(ev, 999)
                r1 = event_return(ev["code"], board.get(ev["code"]), cal, cal_ix, ev["entry"], gi, False)
                r2 = event_return(ev["code"], board.get(ev["code"]), cal, cal_ix, ev["entry"], gi, True)
                if r1 and r2:
                    rec["v1_hold"], rec["v1_mdd"] = round(r1[0] * 100, 2), round(r1[1] * 100, 1)
                    rec["v2_hold"], rec["v2_trig"] = round(r2[0] * 100, 2), bool(r2[3])
            rows.append(rec)
    evdf = pd.DataFrame(rows)
    evdf.to_csv("次新策略_事件明细_%s.csv" % wname, index=False, encoding="utf-8-sig")
    pickle.dump(_px, open(PX_PKL, "wb"))

    # ── 披露与判据 ──
    v1 = evdf[(evdf["var"] == "V1")]
    v0 = evdf[(evdf["var"] == "V0")]
    v1f = v1[v1.full12]
    v0f = v0[v0.full12]
    def mstat(df, col):
        x = pd.to_numeric(df.get(col), errors="coerce").dropna()
        return (len(x), x.mean(), x.median()) if len(x) else (0, float("nan"), float("nan"))
    log(f"[{wname}] 完整12月窗口事件占比 V1 {len(v1f)}/{len(v1)}  V0 {len(v0f)}/{len(v0)}")
    for m in (1, 3, 6, 12, 24):
        n, mu, md = mstat(v1, "ret_%dm" % m)
        ne, mue, mde = mstat(v1f if m == 12 else v1, "exc_%dm" % m)
        log("  V1 +%2d月: 绝对 n=%d 均%+.1f%% 中位%+.1f%% | vs匹配 n=%d 均%+.1f%% 中位%+.1f%%"
            % (m, n, mu, md, ne, mue, mde))
    n0, mu0, md0 = mstat(v0f, "exc_12m")
    n1, mu1, md1 = mstat(v1f, "exc_12m")
    _, mui, _ = mstat(v1f, "exc_idx_12m")
    log(f"  判据① V1完整12月对照超额: n={n1} 均值{mu1:+.2f}pp 中位{md1:+.2f}pp")
    log(f"  判据③ V1−V0(12月对照超额均值): {mu1 - mu0:+.2f}pp (V0: n={n0} 均{mu0:+.2f}pp)")
    log(f"  参考 V1 vs 全收益指数12月: 均{mui:+.2f}pp")
    # 判据④ moving-block bootstrap(块长12)
    gm = v1f.dropna(subset=["exc_12m"]).groupby(v1f.dec.str[:6])["exc_12m"].mean()
    if len(gm) >= 6:
        arr = gm.values
        rng = np.random.RandomState(20260804)
        L, n_ = 12, len(arr)
        sims = []
        for _ in range(2000):
            picks = []
            while len(picks) < n_:
                s0 = rng.randint(0, n_)
                picks.extend(arr[(s0 + np.arange(L)) % n_].tolist())
            sims.append(np.mean(picks[:n_]))
        log(f"  判据④ 12月对照超额月均值 MBB(块12)90%CI: [{np.percentile(sims,5):+.2f}, {np.percentile(sims,95):+.2f}]pp 月数={n_}")
    yr = v1f.dropna(subset=["exc_12m"]).groupby(v1f.dec.str[:4])["exc_12m"].sum()
    if len(yr) and yr.abs().sum() > 0:
        log("  判据⑤ 年度贡献: %s" % {k: "%.0f%%" % (v / yr.abs().sum() * 100) for k, v in yr.items()})
    for label, e0, e1 in ERAS:
        seg = v1f[(v1f.dec.str[:6] >= e0) & (v1f.dec.str[:6] <= e1)]
        n, mu, _ = mstat(seg, "exc_12m")
        if n:
            log(f"  判据⑥ 时代[{label}]: n={n} 12月对照超额均值{mu:+.2f}pp")
    for label, cond in (("解禁前入场(age<244)", v1f.age < 244), ("解禁后入场(age≥244)", v1f.age >= 244)):
        n, mu, _ = mstat(v1f[cond], "exc_12m")
        if n:
            log(f"  披露 {label}: n={n} 12月对照超额均值{mu:+.2f}pp")
    # V2
    trig = v1[v1.get("v2_trig") == True] if "v2_trig" in v1 else pd.DataFrame()
    log(f"  V2翻倍卖半: 触发{len(trig)}笔（判据门槛≥20，否则'不可判'）")
    if len(trig):
        d_ = pd.to_numeric(v1.v2_hold, errors="coerce") - pd.to_numeric(v1.v1_hold, errors="coerce")
        log(f"    全体V1事件 V2−V1终值: 均{d_.dropna().mean():+.2f}pp")

    # ── 组合层（判据②）──
    def portfolio(tag):
        evs = entries[tag]
        if not evs:
            return
        by_dec = {}
        for ev in evs:
            by_dec.setdefault(ev["dec"], []).append(ev["code"])
        pos, nav, navs = set(), 1.0, []
        start = min(ev["entry"] for ev in evs)
        for d_ in cal:
            if d_ < start:
                continue
            i = cal_ix[d_]
            if pos:
                rs = []
                for c in list(pos):
                    p = prices(c)
                    if p is None or d_ not in p.index:
                        continue
                    j = p.index.get_loc(d_)
                    if j > 0:
                        pc = float(p["aclose"].iloc[j - 1]); cc = float(p["aclose"].iloc[j])
                        if pc > 0 and not pd.isna(pc) and not pd.isna(cc):
                            rs.append(cc / pc - 1)
                if rs:
                    nav *= 1 + float(np.mean(rs)) - (COMM * 2 + SLIP) / 21
            navs.append((d_, nav))
            if d_ in set(dec_dates):
                drop = set()
                for c in pos:
                    if age(c, d_) > GRAD:
                        p = prices(c)
                        if p is not None and d_ in p.index:
                            thr = limit_pct(board.get(c), d_) * 0.95
                            if not pd.isna(p.loc[d_, "pct"]) and p.loc[d_, "pct"] <= -thr:
                                continue        # 跌停：保留至下月末（评审卖出可达）
                        drop.add(c)
                pos -= drop
                for c in by_dec.get(d_, []):
                    pos.add(c)
        h = pd.DataFrame(navs, columns=["date", "nav"]).set_index("date")
        if len(h) < 40:
            return
        yrs = len(h) / 244
        cagr = h.nav.iloc[-1] ** (1 / yrs) - 1
        mdd = (h.nav / h.nav.cummax() - 1).min()
        d0, d1 = h.index[0], h.index[-1]
        b0 = idx_tr[idx_tr.index >= d0]
        bench = (float(idx_tr.loc[d1]) / float(b0.iloc[0])) ** (1 / yrs) - 1 if len(b0) and d1 in idx_tr.index else float("nan")
        log(f"  判据② 组合[{tag}]: 全期{(h.nav.iloc[-1]-1)*100:+.1f}% 年化{cagr*100:+.1f}% MDD{mdd*100:.1f}% | H00852年化{bench*100:+.1f}%")
    log(f"[{wname}] 组合层:")
    portfolio("V1")
    portfolio("V0")

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    t0 = time.time()
    sb, fina, db, idxpk, cal_full = load_static()
    for w in (["outsample", "bridge", "insample"] if which == "both" else [which]):
        run_window(w, sb, fina, db, idxpk, cal_full)
        pickle.dump(_px, open(PX_PKL, "wb"))
    log("总耗时 %.0f 分钟" % ((time.time() - t0) / 60))
