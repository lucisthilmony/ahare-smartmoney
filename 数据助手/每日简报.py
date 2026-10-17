# -*- coding: utf-8 -*-
"""每日简报（19:20 cron）：无论有无产出，向Discord发一条当日系统与市场状态摘要。

只读现有产物（data.js/.shadow_state.json/前向影子净值.csv）+两次行情查询，不改任何生产状态。
设计原则：纪律系统的沉默必须与故障的沉默可区分——每天一条回执。
"""
import os, re, json, datetime as dt
import urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, ".")
import config as C
import pipeline as P
import pandas as pd


def post_discord(text):
    text = text[:1900]
    print(text)
    url = getattr(C, "DISCORD_WEBHOOK", "") or ""
    if not url:
        print("[warn] 未配置 DISCORD_WEBHOOK，仅打印。"); return
    body = json.dumps({"content": text}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 AStockDailyBrief/1.0"})
    try:
        r = urllib.request.urlopen(req, timeout=15); print("[ok] discord", getattr(r, "status", "?"))
    except Exception as e:
        print("[err] discord 推送失败：", e)


def is_trading_day():
    try:
        return dt.date.today().strftime("%Y%m%d") in set(P._recent_trade_dates(8))
    except Exception:
        return True


def main():
    if not is_trading_day():
        print("非交易日，跳过"); return
    today = dt.date.today().strftime("%Y%m%d")
    lines = [f"📋 每日简报 {dt.date.today():%Y-%m-%d}"]

    # ── 1. 系统状态（data.js，18:30管线产物）──
    warn = []
    try:
        raw = open("../data.js", encoding="utf-8").read()
        js, _ = json.JSONDecoder().raw_decode(raw[raw.index("{"):])
        st = js.get("state", {})
        dd_norm = str(js.get("data_date", "")).replace("-", "")
        fresh = "✓" if dd_norm == today else f"⚠️数据日={js.get('data_date')}"
        veto = "⛔一票否决" if st.get("veto") else "无否决"
        lines.append(f"档位 **{st.get('tier','?')}**（状态分{st.get('score','?')}/4，{veto}）{fresh}")
        lu, ld = st.get("limit_up"), st.get("limit_down")
        lim_s = f"涨停{lu}/跌停{ld}" if lu is not None else "涨停/跌停:榜单未发布"
        lines.append(f"广度 涨{st.get('up_cnt','?')}/跌{st.get('down_cnt','?')} · {lim_s} · 情绪:{st.get('regime',{}).get('label','?')}")
    except Exception as e:
        warn.append(f"data.js读取失败:{e}")

    # ── 2. 指数与B梯读数 ──
    try:
        px = P._ts_query("index_daily", ts_code="000300.SH",
                         start_date=(dt.date.today()-dt.timedelta(days=500)).strftime("%Y%m%d"),
                         end_date=today).sort_values("trade_date")
        c = px["close"].astype(float)
        last, prev = c.iloc[-1], c.iloc[-2]
        dd = last / c.rolling(250, min_periods=100).max().iloc[-1] - 1
        pe_df = P._ts_query("index_dailybasic", ts_code="000300.SH",
                            start_date=(dt.date.today()-dt.timedelta(days=15)).strftime("%Y%m%d"),
                            end_date=today).sort_values("trade_date")
        pe_now = float(pe_df["pe_ttm"].iloc[-1])
        hist = pd.read_csv(".pe300_full.csv", dtype={"trade_date": str})
        hp = pd.to_numeric(hist["pe_ttm"], errors="coerce").dropna()
        pct = (hp < pe_now).mean() * 100
        b2_pe, b3_pe = hp.quantile(0.30), hp.quantile(0.15)
        lines.append(f"沪深300 {last:.0f}（{(last/prev-1)*100:+.1f}%）· 距250日峰 {dd*100:.1f}%")
        lines.append(f"PE {pe_now:.1f} = **{pct:.0f}%分位**（2005起扩窗）· B2线≈{last*b2_pe/pe_now:.0f}点 B3线≈{last*b3_pe/pe_now:.0f}点")
        floor = 0.45 if pct <= 15 else (0.30 if pct <= 30 else 0.0)
        tgt = max(0.12, floor)
        lines.append(f"协议v1.3参考目标（未签署）：权益 **{tgt*100:.0f}%**" + ("（B梯触发中）" if floor else "（B梯静默，仅核心）"))
    except Exception as e:
        warn.append(f"行情/估值读取失败:{e}")

    # ── 3. 影子系统回执 ──
    try:
        s = json.load(open(".shadow_state.json"))
        ok_run = s.get("last_run") == today
        rec = s.get("recovery_required", False)
        mark = os.path.exists(".shadow_commit_pending.json")
        nav = pd.read_csv("前向影子净值.csv", header=None).iloc[-1]
        if ok_run and not rec and not mark:
            # 持仓在顶层 A/C/R 流的 open 列表（修正2026-08-10：原误读不存在的streams键，恒显示0/0/0）
            npos = "/".join(str(len((s.get(k) or {}).get("open") or [])) for k in ("A", "C", "R"))
            lines.append(f"影子系统 ✅ 已记账（{s.get('last_run')}）· A/C/R持仓 {npos} · 恢复锁无 · 半提交无")
        else:
            flag = []
            if not ok_run: flag.append(f"last_run={s.get('last_run')}≠今日")
            if rec: flag.append("recovery_required=True")
            if mark: flag.append("COMMIT_MARK残留")
            lines.append("影子系统 ⚠️ " + "；".join(flag) + " —— 按CLAUDE.md五类产物核对流程处理")
    except Exception as e:
        warn.append(f"影子状态读取失败:{e}")

    # ── 4. 事件线倒计时 ──
    try:
        y = dt.date.today().year
        for ann in (dt.date(y, 5, 25), dt.date(y, 11, 25), dt.date(y + 1, 5, 25)):
            # 公告≈5月/11月最后周五：从25日向后找周五
            while ann.weekday() != 4:
                ann += dt.timedelta(days=1)
            if ann >= dt.date.today():
                lines.append(f"指数调样公告倒计时 ≈{(ann - dt.date.today()).days}天（{ann:%m-%d}周五盘后，事件卫星待命）")
                break
    except Exception:
        pass

    if warn:
        lines.append("⚠️ " + " | ".join(warn))
    post_discord("\n".join(lines))


if __name__ == "__main__":
    main()
