# -*- coding: utf-8 -*-
"""
监管异动 · 事件研究（观察性，2026-07-02 预注册）

假设来源：蒸馏资料两条线索——①"10天100%或30天200%异动进入监管期，提前减速离场"；
②"强监管标的能否扛住雷劫（点名后是否有承接）决定后续走向，扛不住则一路砸"。

**定位：纯观察，不做采纳决策。** 若两窗口出现同向稳健模式，下一轮再预注册成策略实验。

事件定义（预注册，跑前写定）：
  E10：收盘价较10个交易日前收盘涨幅 ≥ +100%，取首次穿越日（前一日<100%）；同一股票20个交易日内不重复计事件。
  E30：同理，30个交易日累计 ≥ +200%（次要事件集）。
  以 qfq 收盘价计算；事件日必须在回测窗口内（预热段只用于计算不出事件）。
  排除：北交所（board=None）、ST（当前名回溯，已知近似）、次新（上市<约60交易日）。
  近似声明：交易所口径是"涨跌幅偏离值"（相对指数）且各板细则不同，此处用绝对涨幅统一近似——
  本研究关心的是"短期翻倍标的的后续行为"，不是精确复刻监管触发。

观察量（预注册）：
  ① 事件日T收盘起的前瞻收益 fwd 1/3/5/10/20 日（均值/中位数/胜率）。
  ② "扛住"分组：T+1收盘涨幅>0 = 扛住；分组后从 T+1 收盘起算前瞻 1/3/5/10/20 日（可执行视角：T+1收盘观察到分组归属后入场）。
  ③ 按板（10cm vs 20cm）分列①。
  两窗口（2024-06~2026-06 / 2019-2023）分别输出，不合并。

用法：./.venv/bin/python experiment_regulation_event.py
输出：02_回测报告/监管异动事件研究-2026-07-02.md
"""
import os, sys, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
import pipeline as P
import backtest as B

WINDOWS = [("20240618", "20260630", "2024-2026样本内"), ("20190101", "20231231", "2019-2023样本外")]
FWD = (1, 3, 5, 10, 20)
DEDUP = 20

def events_for(start, end):
    data = B.fetch_all(start, end)
    basic = data["basic"]
    st_set = set(basic.loc[basic["name"].apply(P.is_st), "ts_code"])
    board_map = dict(zip(basic["ts_code"], basic["board"]))
    list_map = dict(zip(basic["ts_code"], basic["list_date"].fillna("19900101")))
    win = set(data["win_dates"])
    panel = data["panel"].sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    out = []
    for code, sub in panel.groupby("ts_code", sort=False):
        board = board_map.get(code)
        if board is None or code in st_set:
            continue
        c = sub["close"].values; dates = sub["trade_date"].values
        n = len(c)
        if n < 35:
            continue
        ld = str(list_map.get(code, "19900101"))[:8]
        try:
            ld_dt = dt.datetime.strptime(ld, "%Y%m%d").date()
        except ValueError:
            ld_dt = dt.date(1990, 1, 1)
        r10 = np.full(n, np.nan); r30 = np.full(n, np.nan)
        r10[10:] = c[10:] / c[:-10] - 1
        r30[30:] = c[30:] / c[:-30] - 1
        for etype, r, thr in (("E10", r10, 1.0), ("E30", r30, 2.0)):
            last_ev = -10**9
            for i in range(1, n):
                if not (r[i] == r[i]) or r[i] < thr or (r[i-1] == r[i-1] and r[i-1] >= thr):
                    continue
                if i - last_ev < DEDUP:
                    continue
                d = dates[i]
                if d not in win:
                    continue
                d_dt = dt.datetime.strptime(d, "%Y%m%d").date()
                if (d_dt - ld_dt).days < int(C.MIN_LIST_DAYS * 1.6):
                    continue
                last_ev = i
                rec = dict(etype=etype, ts=code, date=d, board=board)
                for k in FWD:
                    rec[f"fwd{k}"] = c[i+k] / c[i] - 1 if i + k < n else np.nan
                rec["surv"] = (c[i+1] / c[i] - 1 > 0) if i + 1 < n else None   # 扛住=T+1收涨
                for k in FWD:
                    rec[f"f1_{k}"] = c[i+1+k] / c[i+1] - 1 if i + 1 + k < n else np.nan
                out.append(rec)
    return pd.DataFrame(out)

def fmt_row(df, label):
    n = len(df)
    cells = [label, str(n)]
    for k in FWD:
        s = df[f"fwd{k}"].dropna()
        cells.append(f"{s.mean()*100:+.1f}% / {(s>0).mean()*100:.0f}%" if len(s) else "-")
    return "| " + " | ".join(cells) + " |"

def fmt_row_f1(df, label):
    n = len(df)
    cells = [label, str(n)]
    for k in FWD:
        s = df[f"f1_{k}"].dropna()
        cells.append(f"{s.mean()*100:+.1f}% / {(s>0).mean()*100:.0f}%" if len(s) else "-")
    return "| " + " | ".join(cells) + " |"

if __name__ == "__main__":
    L = ["# 监管异动 · 事件研究（2026-07-02，新股票池口径）\n",
         "> 观察性研究，预注册协议见 experiment_regulation_event.py 头注释。单元格=平均收益/胜率。",
         "> 事件：E10=10日累计≥+100%首穿越；E30=30日≥+200%。排除北交所/ST/次新。qfq收盘价。\n"]
    for start, end, wname in WINDOWS:
        ev = events_for(start, end)
        L.append(f"\n## 窗口 {wname}（{start}~{end}）\n")
        for etype in ("E10", "E30"):
            e = ev[ev["etype"] == etype]
            if not len(e):
                L.append(f"### {etype}：无事件\n"); continue
            L.append(f"### {etype}（{len(e)} 起）\n")
            hdr = "| 分组 | n | " + " | ".join(f"{k}日" for k in FWD) + " |"
            sep = "|---|---|" + "---|" * len(FWD)
            L.append("**事件日T收盘起的前瞻（无条件）**\n\n" + hdr + "\n" + sep)
            L.append(fmt_row(e, "全部"))
            L.append(fmt_row(e[e["board"] == "main"], "10cm主板"))
            L.append(fmt_row(e[e["board"].isin(["chinext", "star"])], "20cm"))
            L.append("\n**扛住分组（T+1收涨=扛住；从T+1收盘起算，可执行视角）**\n\n" + hdr + "\n" + sep)
            sv = e[e["surv"] == True]; dn = e[e["surv"] == False]
            L.append(fmt_row_f1(sv, "扛住"))
            L.append(fmt_row_f1(dn, "没扛住"))
            L.append("")
    L.append("\n## 诚实限制\n- 绝对涨幅近似监管\"偏离值\"口径；各板细则未复刻。ST用当前名回溯。")
    L.append("- 前瞻收益为qfq收盘对收盘，无成本无滑点；涨停无法买入的可达性未建模（翻倍股常一字，**均值会高估可实现收益**）。")
    L.append("- 观察性研究：任何策略化使用需另行预注册。")
    out = os.path.join(C.BASE_DIR, "02_回测报告", "监管异动事件研究-2026-07-02.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    B.log(f"已生成 {out}")
