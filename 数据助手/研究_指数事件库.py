# -*- coding: utf-8 -*-
"""指数样本调整事件库 M1 构建器（研究线：指数调整事件，2026-07-19立项）。

从 tushare index_weight 月末快照重建 沪深300/中证500/中证1000 的调样史：
相邻月末快照差分 → 调入/调出名单；6月/12月的变动标记为定期调样（生效日=第二个
星期五后首个交易日，由规则生成），其余月份标记为临时调整（退市/ST/合并等）。

输出：指数调整事件库.csv（index_code, index_name, change_month, adj_type,
effective_date_rule, announce_date, direction, con_code）
announce_date 留空——中证官网公告日需逐年人工核实后回填，禁止用"生效-2周"估算值冒充。

纪律：本脚本只建事件库，不算任何收益。M2 描述性统计须另写预注册脚本。
"""
import sys, time, datetime as dt
import pandas as pd

sys.path.insert(0, ".")
import pipeline as P

INDEXES = {"000300.SH": "沪深300", "000905.SH": "中证500", "000852.SH": "中证1000"}
START, END = "201812", "202606"   # 快照月范围（差分后事件覆盖2019-01~2026-06）
OUT = "指数调整事件库.csv"


def month_ends(start_ym, end_ym):
    cur = dt.date(int(start_ym[:4]), int(start_ym[4:]), 1)
    stop = dt.date(int(end_ym[:4]), int(end_ym[4:]), 1)
    while cur <= stop:
        yield f"{cur:%Y%m}"
        cur = (cur.replace(day=28) + dt.timedelta(days=8)).replace(day=1)


def snapshot(index_code, ym):
    """该月的月末成分快照（取该月内最后一个快照日）。"""
    df = P._ts_query("index_weight", index_code=index_code,
                     start_date=ym + "01", end_date=ym + "31")
    if df is None or df.empty:
        return None
    last = df["trade_date"].max()
    return set(df.loc[df["trade_date"] == last, "con_code"])


def second_friday_next_trading(ym):
    """定期调样生效日规则：6/12月第二个星期五后的首个交易日（周一；节假日待人工校正）。"""
    y, m = int(ym[:4]), int(ym[4:])
    fridays = [d for d in range(1, 22)
               if dt.date(y, m, d).weekday() == 4]
    return (dt.date(y, m, fridays[1]) + dt.timedelta(days=3)).strftime("%Y%m%d")


def main():
    rows = []
    for code, name in INDEXES.items():
        prev, prev_ym = None, None
        for ym in month_ends(START, END):
            snap = snapshot(code, ym)
            time.sleep(0.35)  # 限流保护
            if snap is None:
                print(f"[warn] {code} {ym} 无快照，跳过", flush=True)
                continue
            if prev is not None:
                added, removed = snap - prev, prev - snap
                if added or removed:
                    regular = ym[4:] in ("06", "12")
                    adj_type = "定期" if regular else "临时"
                    eff = second_friday_next_trading(ym) if regular else ""
                    for c in sorted(added):
                        rows.append([code, name, ym, adj_type, eff, "", "调入", c])
                    for c in sorted(removed):
                        rows.append([code, name, ym, adj_type, eff, "", "调出", c])
                    print(f"{name} {prev_ym}->{ym}: +{len(added)} -{len(removed)} ({adj_type})", flush=True)
            prev, prev_ym = snap, ym
    out = pd.DataFrame(rows, columns=["index_code", "index_name", "change_month", "adj_type",
                                      "effective_date_rule", "announce_date", "direction", "con_code"])
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    n_reg = (out["adj_type"] == "定期").sum()
    print(f"\n事件库已写入 {OUT}：{len(out)}条（定期{n_reg} / 临时{len(out)-n_reg}），"
          f"覆盖 {out['change_month'].min()}~{out['change_month'].max()}")


if __name__ == "__main__":
    main()
