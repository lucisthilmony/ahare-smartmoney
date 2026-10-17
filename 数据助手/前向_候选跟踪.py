# -*- coding: utf-8 -*-
"""前向候选跟踪（观察性）：系统候选/执行卡标的"选出后N日"表现 vs 双基准。

回答的问题："系统选出来的股票后来表现如何？"——用统一口径的数字取代印象。
- 数据源①：影子决策快照.jsonl（2026-07-20起，候选池全量 + A/C/R三流queued标的并集）；
- 数据源②：SEED_ROWS（快照上线前的执行卡，自signal.log人工核录；signal.log最早只到
  2026-07-03，之前若有产出已不可考——覆盖边界到此为止）；
- 口径：入场=选出日T收盘（14:40尾盘近似；执行卡卡面价与收盘价有约1%系统差，见note）；
  期限=+1/3/5/10/15个交易日收盘；收益一律用复权价（close×adj_factor，除权除息/送转不失真），
  entry_close/t1_open两个展示列保留未复权原始价；
  超额两列：exc_N=对沪深300；bexc_N=对本板块指数（68→科创50 / 30→创业板指 / 主板→沪深300）——
  "大盘不好时选股抗跌"类主张须看bexc（匹配基准），只看exc会与Beta暴露混淆；
- 已知局限（裁决时须一并解读，见2026-07-26评审）：跟踪按"持有到期"计算，不含止损等执行规则，
  测的是选股方向而非系统实现盈亏；候选=高beta小票且只在risk-on档位产生，条件性beta可推高exc，
  裁决须与R流随机对照共同解读；相邻选出日窗口重叠，行数≠独立样本；
- 输出：前向观察_候选跟踪.csv（幂等：每次全量重算，未成熟期限留空）；
- 纪律：纯观察不门控不交易，只读生产状态；封存令内合规（只产生前向事实记录）。
- 待办：涨停收盘候选的含/不含双口径汇总；t1_open入场敏感性列；周聚类bootstrap分析器。
"""
import os, sys, json
import datetime as dt

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")
import pipeline as P
import pandas as pd

SNAP = "影子决策快照.jsonl"
OUT = "前向观察_候选跟踪.csv"
HORIZONS = (1, 3, 5, 10, 15)
START = "20260601"        # 行情/日历拉取起点（早于最早SEED即可）
STALE_MAX = 5             # 停牌沿价上限（交易日）：超过则该期限置空，防长停/退市整理冻价美化

# 快照上线(2026-07-20)前的系统产出，自signal.log人工核录（无审计字段，靠src列区分）
SEED_ROWS = [
    {"select_date": "20260710", "code": "688049", "name": "炬芯科技", "role": "执行卡",
     "src": "signal.log人工核录", "note": "卡面价45.19/止损39.63，止损20260717触及（跟踪按持有到期，非实现盈亏）"},
    {"select_date": "20260710", "code": "600867", "name": "通化东宝", "role": "备选",
     "src": "signal.log人工核录", "note": "卡面'其余过门备选'口头列举，无评分字段"},
    {"select_date": "20260710", "code": "601555", "name": "东吴证券", "role": "备选",
     "src": "signal.log人工核录", "note": "卡面'其余过门备选'口头列举，无评分字段"},
]


def ts_code(raw):
    raw = str(raw)
    if "." in raw:                      # 自带权威后缀直接沿用，不用前缀猜
        return raw
    if raw.startswith("92"):            # 北交所新段
        return raw + ".BJ"
    if raw.startswith("90"):            # 沪B
        return raw + ".SH"
    if raw.startswith("20"):            # 深B
        return raw + ".SZ"
    if raw.startswith(("4", "8")):      # 老三板/北交所
        return raw + ".BJ"
    if raw.startswith("6"):
        return raw + ".SH"
    if raw.startswith(("0", "3")):
        return raw + ".SZ"
    return raw + ".SH"


def bare(code):
    return str(code).split(".")[0]


def load_snapshot_rows():
    rows, bad = [], 0
    if not os.path.exists(SNAP):
        return rows
    with open(SNAP, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                bad += 1
                continue
            d = str(j.get("date", ""))
            queued = {}                                  # bare -> "AC"等流集合
            for s in ("A", "C", "R"):
                q = ((j.get("decisions") or {}).get(s) or {}).get("actual") or {}
                if q.get("queued_code"):
                    b = bare(q["queued_code"])
                    queued[b] = queued.get(b, "") + s
            seen = set()
            for c in j.get("candidates") or []:
                if not isinstance(c, dict) or not c.get("code"):
                    continue
                b = bare(c["code"])
                seen.add(b)
                role = "queued_" + queued[b] if b in queued else "候选池"
                rows.append({"select_date": d, "code": b, "name": c.get("name", ""),
                             "role": role, "src": "快照",
                             "note": "grade=%s score=%s" % (c.get("grade", "?"), c.get("score", "?"))})
            for b, streams in queued.items():            # 防御：queued不在候选池也成行（并集口径）
                if b not in seen:
                    rows.append({"select_date": d, "code": b, "name": "", "role": "queued_" + streams,
                                 "src": "快照", "note": "⚠️queued不在当日候选池数组（异常，需核对快照）"})
    if bad:
        print("⚠️ 快照坏行跳过 %d 条（若持续出现需核对jsonl完整性）" % bad)
    return rows


def main():
    today = dt.date.today().strftime("%Y%m%d")
    rows = SEED_ROWS + load_snapshot_rows()
    # 去重：同日同码保留角色更具体的一条（执行卡/queued_* > 备选 > 候选池）
    def prio(role):
        return 0 if (role == "执行卡" or role.startswith("queued_")) else (1 if role == "备选" else 2)
    best = {}
    for r in rows:
        k = (r["select_date"], r["code"])
        if k not in best or prio(r["role"]) < prio(best[k]["role"]):
            best[k] = r
    rows = sorted(best.values(), key=lambda r: (r["select_date"], r["code"]))
    if not rows:
        print("无候选记录（快照候选池为空且无SEED）。")
        return

    def fetch_idx(tc):
        d = P._ts_query("index_daily", ts_code=tc, start_date=START, end_date=today)
        d = d.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
        return d.set_index("trade_date")["close"].astype(float)

    hs = fetch_idx("000300.SH")
    cal = list(hs.index)

    BOARD_IDX = {"star": "000688.SH", "chinext": "399006.SZ", "main": "000300.SH"}
    idx_cache = {"000300.SH": hs}
    def board_index(code):
        b = "star" if code.startswith("68") else ("chinext" if code.startswith("30") else "main")
        tc = BOARD_IDX[b]
        if tc not in idx_cache:
            idx_cache[tc] = fetch_idx(tc)
        return tc, idx_cache[tc]

    px_cache = {}
    def closes(code):
        # 返回 (复权close, 原始open, 原始close, 复权备注)；收益只用复权列
        if code not in px_cache:
            tc = ts_code(code)
            d = P._ts_query("daily", ts_code=tc, start_date=START, end_date=today)
            if d is None or len(d) == 0:
                px_cache[code] = None
            else:
                s = d.drop_duplicates("trade_date", keep="last").sort_values("trade_date").set_index("trade_date")
                adj_close = s["close"].astype(float)
                adj_note = " ⚠️无复权因子，收益为未复权口径"
                try:
                    af = P._ts_query("adj_factor", ts_code=tc, start_date=START, end_date=today)
                    if af is not None and len(af):
                        af = (af.drop_duplicates("trade_date", keep="last").sort_values("trade_date")
                                .set_index("trade_date")["adj_factor"].astype(float))
                        af = af.reindex(s.index).ffill()
                        if not af.isna().all():
                            adj_close = s["close"].astype(float) * af
                            adj_note = ""
                except Exception:
                    pass
                px_cache[code] = (adj_close, s["open"].astype(float), s["close"].astype(float), adj_note)
        return px_cache[code]

    out = []
    for r in rows:
        rec = dict(r)
        pc = closes(r["code"])
        d0 = r["select_date"]
        if pc is None or d0 not in cal or d0 not in pc[0].index:
            rec["note"] = (rec.get("note", "") + " ⚠️无行情/选出日缺K线").strip()
            out.append(rec)
            continue
        c0 = float(pc[0].loc[d0])                    # 复权口径，只用于收益
        i0 = cal.index(d0)
        rec["entry_close"] = float(pc[2].loc[d0])    # 展示用未复权收盘
        nxt = cal[i0 + 1] if i0 + 1 < len(cal) else None
        rec["t1_open"] = round(float(pc[1].loc[nxt]), 3) if (nxt and nxt in pc[1].index) else None
        if pc[3]:
            rec["note"] = (rec.get("note", "") + pc[3]).strip()
        stale = []
        bname, bser = board_index(r["code"])
        rec["board_idx"] = bname
        aligned = pc[0].reindex(cal).ffill()         # 停牌沿用最后收盘（有上限，见下）
        have = set(pc[0].index)
        for h in HORIZONS:
            keys = ("ret_%d" % h, "exc_%d" % h, "bexc_%d" % h)
            if i0 + h >= len(cal):
                for k in keys:
                    rec[k] = None
                continue
            dh = cal[i0 + h]
            # 数据滞后防护：期限落在日历最后一天而个股缺该日→按未成熟处理，不沿昨收
            if dh == cal[-1] and dh not in have:
                for k in keys:
                    rec[k] = None
                continue
            ch = aligned.loc[dh]
            # 沿价上限：dh往前STALE_MAX个交易日内无真实成交价→置空
            recent = cal[max(0, i0 + h - STALE_MAX + 1): i0 + h + 1]
            if pd.isna(ch) or not any(x in have for x in recent):
                for k in keys:
                    rec[k] = None
                if not pd.isna(ch):
                    rec["note"] = (rec.get("note", "") + " 停牌逾%d日置空:+%d日" % (STALE_MAX, h)).strip()
                continue
            if dh not in have:
                stale.append(h)
            ret = float(ch) / c0 - 1
            bench = float(hs.loc[dh]) / float(hs.loc[d0]) - 1
            bb = float(bser.loc[dh]) / float(bser.loc[d0]) - 1 if (dh in bser.index and d0 in bser.index) else None
            rec["ret_%d" % h] = round(ret * 100, 2)
            rec["exc_%d" % h] = round((ret - bench) * 100, 2)
            rec["bexc_%d" % h] = round((ret - bb) * 100, 2) if bb is not None else None
        if stale:
            rec["note"] = (rec.get("note", "") + " 停牌沿价:%s" % stale).strip()
        out.append(rec)

    cols = (["select_date", "code", "name", "role", "src", "entry_close", "t1_open", "board_idx"]
            + ["ret_%d" % h for h in HORIZONS] + ["exc_%d" % h for h in HORIZONS]
            + ["bexc_%d" % h for h in HORIZONS] + ["note"])
    df = pd.DataFrame(out)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("已写 %s：%d 行" % (OUT, len(df)))

    # 汇总（仅成熟样本）：R流标的按构造属于池内成员，全量入主表（随机剔除无偏但浪费样本，
    # 2026-07-26评审核实结论）；S vs R的流级裁决用前向影子净值，不用本表。n同时报行数与去重只数
    main_df = df
    r_df = df[df["role"] == "queued_R"]
    n_codes = main_df["code"].nunique()
    tag = "" if n_codes >= 20 else " [样本不足，不可裁决]"
    for h in HORIZONS:
        m = pd.to_numeric(main_df["exc_%d" % h], errors="coerce").dropna()
        bm = pd.to_numeric(main_df["bexc_%d" % h], errors="coerce").dropna()
        if len(m):
            print("  +%2d日：对300超额 均值%+.2f%% 中位%+.2f%%｜对本板指数 均值%+.2f%% 中位%+.2f%%（%d行/%d只）%s"
                  % (h, m.mean(), m.median(),
                     bm.mean() if len(bm) else float("nan"),
                     bm.median() if len(bm) else float("nan"),
                     len(m), main_df.loc[pd.to_numeric(main_df["exc_%d" % h], errors="coerce").notna(), "code"].nunique(),
                     tag))
    if len(r_df):
        m15 = pd.to_numeric(r_df.get("exc_15"), errors="coerce").dropna()
        print("  其中R流随机对照标的：%d行（已含在主表），exc_15均值%s" % (len(r_df), ("%+.2f%%" % m15.mean()) if len(m15) else "未成熟"))
    print("（观察性统计；行数≠独立样本——相邻选出日窗口重叠；'抗跌/优秀'类主张以bexc匹配基准列为准；"
          "候选含条件性高beta，正式裁决须与R流对照共同解读；样本<20只时不构成任何裁决依据）")


if __name__ == "__main__":
    main()
