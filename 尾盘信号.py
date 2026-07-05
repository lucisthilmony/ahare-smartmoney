# -*- coding: utf-8 -*-
"""
A股尾盘信号（半自动） · 每个交易日约 14:40 由 Mac 本地 cron 运行
  读实时大盘 + 盘后候选池(data.js) → 机械过三道门 → 生成"今日执行卡"或"今日休息" → 推送 Discord。
  只发信号，绝不下单。下单永远由你手动完成。
"""
import os, sys, json, datetime as dt, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
失效判据 = __import__("失效判据")   # 手册提案1：滚动60笔期望，机械执行（2026-07-03接入）
前向筛选 = __import__("前向_席位筛选")   # 复用其 codex_flags（A门判定，v6.3）
底仓引擎 = __import__("底仓引擎")   # strong3底仓提醒（v6.3自动化：每5交易日择强+档位定权重）


def post_discord(text):
    text = text[:1900]
    print(text)
    url = getattr(C, "DISCORD_WEBHOOK", "") or ""
    if not url:
        print("[warn] 未配置 DISCORD_WEBHOOK，仅打印。"); return
    body = json.dumps({"content": text}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 AStockTailSignal/1.0"})   # Discord 需要 UA，否则 403
    try:
        r = urllib.request.urlopen(req, timeout=15); print("[ok] discord", getattr(r, "status", "?"))
    except Exception as e:
        print("[err] discord 推送失败：", e)


def is_trading_day():
    try:
        return dt.date.today().strftime("%Y%m%d") in set(P._recent_trade_dates(8))
    except Exception:
        return True


def gate(hc, amt_yi):
    """同日大盘总闸（与工具口径一致）：沪深300实时涨跌 hc + 两市成交额 amt_yi(亿)。"""
    if hc is None: return ("—", 1.0)
    if hc <= -2 or (amt_yi is not None and amt_yi < 8000):   return ("转坏 ×0", 0.0)
    if hc <= -0.5 or (amt_yi is not None and amt_yi < 10000): return ("走弱 ×0.5", 0.5)
    return ("健康 ×1.0", 1.0)


def main():
    stamp = dt.datetime.now().strftime("%m-%d %H:%M")
    if not is_trading_day():
        print("非交易日，跳过。"); return

    m = P.realtime_market() or {}
    idx = {i.get("name"): i for i in (m.get("indices") or [])}
    hc = (idx.get("沪深300") or {}).get("chg_pct")
    amt_yi = m.get("amt_total_yi")
    regime = (m.get("regime") or {}).get("label", "—")
    gtxt, gmul = gate(hc, amt_yi)
    amt_s = ("%.2f 万亿" % (amt_yi / 10000)) if amt_yi else "—"
    head = ("📈 **A股尾盘信号** · %s\n🚦总闸：**%s** ｜ 🧭研判：%s ｜ 成交额 %s ｜ 涨停%s/跌停%s"
            % (stamp, gtxt, regime, amt_s, m.get("limit_up", "—"), m.get("limit_down", "—")))
    fj = 失效判据.evaluate()
    head += "\n" + fj["text"]
    # 底仓提醒（每天都显示，不受卫星休息/停做影响；档位取昨晚data.js的cap）
    _cap = None
    try:
        _txt = open(C.DATA_JS_PATH, encoding="utf-8").read()
        _cap = (json.loads(_txt[_txt.find("{"):_txt.rfind("}") + 1]).get("state") or {}).get("cap")
    except Exception:
        pass
    head += "\n" + 底仓引擎.line(_cap)
    tail = "\n\n_仅决策支持、非投资建议；下单你手动；短线为负和，先活下来、守纪律第一。_"

    # 失效判据=停做：机械执行，覆盖一切开仓信号（手册提案1）
    if fj["level"] == 2:
        post_discord(head + "\n\n⛔ **今日休息（失效判据停做中）**：滚动期望连续两个检查点为负，"
                            "卫星层不开新仓；持仓仍按§7出场规则管理。转模拟盘复盘，期望回正后自动恢复。" + tail)
        return

    # 读盘后候选池
    try:
        txt = open(C.DATA_JS_PATH, encoding="utf-8").read()
        d = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
    except Exception as e:
        post_discord(head + "\n\n⚠️ 读候选池失败（%s），今天仅给大盘读数。" % e + tail); return

    cands = d.get("candidates") or []
    st = d.get("state") or {}
    cap = st.get("cap")
    if gmul == 0.0 or not cands:
        if gmul == 0.0:
            why = "总闸转坏，今日不开新仓（×0）"
        elif st.get("can_open") is False:
            why = "昨收档位=%s（不产生候选），候选池为空属正常" % (st.get("tier") or "空仓/防守")
        else:
            why = "候选池为空（若昨晚18:30刷新失败请手动跑「盘后刷新数据」）"
        post_discord(head + "\n\n🟠 **今日休息**：%s。空仓也是正确执行。" % why + tail); return

    # 逐票过三道门（用实时价）
    q = P.realtime_sina([c["code"] for c in cands]) or {}
    ok, rej = [], []
    for c in cands:
        nm, ma10 = c.get("name"), c.get("ma10")
        r = q.get(c["code"]) or {}
        px, chg = r.get("price"), r.get("chg_pct")
        if not px or not ma10:
            rej.append("%s：无实时价" % nm); continue
        dev = px / ma10 - 1
        if dev < -0.03:
            rej.append("%s：破位（离MA10 %.1f%%）" % (nm, dev * 100)); continue
        if dev > 0.035:
            rej.append("%s：追高（离MA10 +%.1f%%）" % (nm, dev * 100)); continue
        if chg is not None and chg / 100.0 > c.get("gap_thr", 0.04):
            rej.append("%s：当日大涨追高（%+.1f%%）" % (nm, chg)); continue
        if hc is not None and hc > 0 and chg is not None and chg <= -3:
            rej.append("%s：个股独跌（大盘涨、它 %+.1f%%）" % (nm, chg)); continue
        ok.append(c)

    if not ok:
        body = head + "\n\n🟠 **今日休息**：候选无一过三道门。空仓也是正确执行。"
        if rej: body += "\n· " + "\n· ".join(rej[:8])
        post_discord(body + tail); return

    # 卫星开仓资格门（v6.3 · Codex Alpha复核采纳）：codexA=仅回踩修复型
    if getattr(C, "SATELLITE_GATE", "classic") == "codexA":
        flags = [前向筛选.codex_flags(c) for c in ok]
        if all(f == ("", "") for f in flags):     # data.js 还是旧版（无prior60字段）→ 退回旧门并提示
            head += "\n（⚠️ data.js无prior60字段，A门失效退回旧门；跑一次盘后刷新即恢复）"
        else:
            okA = [c for c, f in zip(ok, flags) if f[0] == "Y"]
            if not okA:
                post_discord(head + "\n\n🟠 **今日休息**：过三道门的候选中无「回踩修复型(A)」标的"
                                    "（A门=主线≤5、RS>0、60日跌、成交2-5亿）。宁缺勿滥。" + tail)
                return
            ok = okA

    # 选最强的 1 只（评分优先；走弱总闸下也只此一只）
    ok.sort(key=lambda c: c.get("score", 0), reverse=True)
    p = ok[0]; r = q.get(p["code"]) or {}
    px = r.get("price") or p.get("close")
    pos = ("半仓（总闸走弱）" if gmul == 0.5 else ("总仓上限 %s%% 内正常" % cap if cap else "见「算仓」"))
    if fj["level"] == 1:
        pos += " ｜ ⚠️失效判据减半：本笔R×0.5、档位降一档"
    body = (head + "\n\n🟢 **今日执行卡（仅此一只）**"
            + "\n买 **%s %s** · %s · 主线%s（第%s强）· 评分%s%s"
              % (p.get("name"), p.get("code"), p.get("board_cn", ""), p.get("sec", ""),
                 p.get("sec_rank", "—"), p.get("score", ""), p.get("grade", ""))
            + "\n现价 **%.2f** ｜ 止损 **%.2f** ｜ 仓位：%s" % (px, p.get("stop_price", 0), pos)
            + "\n⚠️ 这是**机械三道门候选**，买前请你再用研判过一遍（**资金是否在流出、RS 强弱、市值弹性**——这些系统看不到）。"
            + "\n\n👉 **你手动下单**；14:40–14:55 点买前再瞄一眼分时，没尾盘跳水再确认。")
    if len(ok) > 1:
        body += "\n（其余过门备选：%s）" % "、".join(c.get("name", "") for c in ok[1:4])
    post_discord(body + tail)


if __name__ == "__main__":
    main()
