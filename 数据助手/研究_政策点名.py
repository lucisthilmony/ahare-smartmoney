# -*- coding: utf-8 -*-
"""政策点名行业效应 · 事件研究执行器。

预注册：../02_回测报告/政策点名行业效应-预注册-2026-07-19.md（词典/判线以该文件为准，本脚本逐字复制）。
输入：../04_原始研究材料/中央政策文件库_2026-07-19/*.txt（首行含发布日期）。
主判据唯一：H1 点名组 +60交易日等权超额，两时代同向且合并均值≥+1.0pp → 候选。
"""
import sys, os, re, glob, json
import pandas as pd
import numpy as np

sys.path.insert(0, ".")
import backtest as B
import 时点数据 as PIT

DOCDIR = "../04_原始研究材料/中央政策文件库_2026-07-19"
L2L1 = json.load(open(".sw_l2_to_l1.json"))
EXCLUDED = {"cewc2023", "gwr2024"}          # 预注册：回报窗口落在缓存缺口

DICT = {
    "农林牧渔": ["粮食安全", "种业", "乡村振兴", "耕地", "种源", "农业强国"],
    "基础化工": ["新材料", "精细化工", "化工新"],
    "钢铁": ["钢铁"],
    "有色金属": ["稀土", "战略性矿产", "矿产资源"],
    "电子": ["集成电路", "半导体", "芯片", "电子信息"],
    "汽车": ["新能源汽车", "智能网联", "汽车消费", "以旧换新"],
    "家用电器": ["家电", "以旧换新"],
    "食品饮料": ["食品安全"],
    "医药生物": ["生物医药", "创新药", "中医药", "医疗器械", "疫苗", "生物技术", "集采", "药品"],
    "公用事业": ["核电", "新型电力系统", "能源保供", "电力体制"],
    "交通运输": ["现代物流", "交通强国", "多式联运", "民航"],
    "房地产": ["房地产", "住房", "房住不炒", "保障性住房", "城中村", "保交楼"],
    "银行": ["普惠金融", "信贷投放"],
    "非银金融": ["资本市场", "注册制", "中长期资金"],
    "建筑装饰": ["基础设施", "新基建", "重大工程", "城市更新"],
    "建筑材料": ["水泥", "建材"],
    "电力设备": ["光伏", "风电", "储能", "特高压", "动力电池", "氢能", "新型能源体系", "碳达峰", "碳中和"],
    "机械设备": ["高端装备", "工业母机", "机器人", "装备制造"],
    "国防军工": ["国防", "军工", "强军"],
    "计算机": ["人工智能", "数字经济", "信创", "大数据", "云计算", "数据要素", "算力", "网络安全", "软件", "工业互联网"],
    "传媒": ["文化产业", "数字文化"],
    "通信": ["5G", "6G", "工业互联网", "光网"],
    "煤炭": ["煤炭"],
    "石油石化": ["油气", "页岩", "炼化"],
    "环保": ["污染防治", "碳达峰", "碳中和", "绿色低碳", "生态文明"],
    "商贸零售": ["免税", "电子商务", "县域商业"],
    "社会服务": ["旅游", "文旅", "养老", "托育"],
}

def load_docs():
    docs = {}
    for f in sorted(glob.glob(os.path.join(DOCDIR, "*.txt"))):
        did = os.path.basename(f)[:-4]
        head = open(f, encoding="utf-8").readline()
        m = re.search(r"发布日期:\s*(\d{8})", head)
        if not m:
            print(f"[warn] {did} 头部无日期，跳过"); continue
        docs[did] = dict(pub=m.group(1), text=open(f, encoding="utf-8").read())
    return docs

def hits_matrix(docs):
    rows = {}
    for did, d in docs.items():
        rows[did] = {ind: sum(d["text"].count(k) for k in kws) for ind, kws in DICT.items()}
    return pd.DataFrame(rows).T   # 行=事件, 列=行业(有词典者)

_CACHE = {}
def close_pivot(tag):
    if tag not in _CACHE:
        s, e = ("20240618", "20260630") if tag == "in" else ("20190101", "20231231")
        panel = B.fetch_all(s, e)["panel"]
        _CACHE[tag] = panel.pivot(index="trade_date", columns="ts_code", values="close")
    return _CACHE[tag]

def which_cache(pub):
    if "20190101" <= pub <= "20230601": return "oos"
    if pub >= "20241001": return "in"
    return None

def industry_returns(C, entry_i, horizon):
    """entry_i收盘→entry_i+horizon收盘，31个L1行业等权收益 + 等权基准。"""
    dates = C.index
    if entry_i + horizon >= len(dates): return None
    d0, d1 = dates[entry_i], dates[entry_i + horizon]
    c0, c1 = C.loc[d0], C.loc[d1]
    ok = c0.notna() & c1.notna()
    ret = c1[ok] / c0[ok] - 1
    byind = {}
    for ts, r in ret.items():
        if PIT.st_at(ts, d0): continue
        l2 = PIT.ind_at(ts, d0)
        if l2 is None: continue
        l1 = L2L1.get(l2)
        if l1 is None: continue
        byind.setdefault(l1, []).append(r)
    ser = pd.Series({k: np.mean(v) for k, v in byind.items() if len(v) >= 5})
    return ser

def main():
    docs = load_docs()
    print(f"文件: {len(docs)}份，参与: {sorted(set(docs) - EXCLUDED)}")
    H = hits_matrix(docs)
    ev_rows = []
    for did in sorted(docs):
        if did in EXCLUDED: continue
        pub = docs[did]["pub"]
        tag = which_cache(pub)
        if tag is None:
            print(f"[skip] {did} pub={pub} 无缓存覆盖"); continue
        C = close_pivot(tag)
        dates = list(C.index)
        fut = [i for i, d in enumerate(dates) if d > pub]
        if not fut or fut[0] < 60:
            print(f"[skip] {did} 入场日/前窗不足"); continue
        e = fut[0]
        named = [i for i in H.columns if H.loc[did, i] >= 1]
        row = dict(id=did, pub=pub, era=("A" if tag == "oos" else "B"), n_named=len(named))
        for h, lab in ((20, "f20"), (60, "f60"), (120, "f120")):
            ser = industry_returns(C, e, h)
            if ser is None:
                row[lab] = np.nan; continue
            bench = ser.mean()
            nm = [i for i in named if i in ser.index]
            row[lab] = (ser[nm].mean() - bench) * 100 if nm else np.nan
            if h == 60:
                sub = H.loc[did, [i for i in H.columns if i in ser.index]]
                row["rho60"] = sub.rank().corr(ser[sub.index].rank())
        # H2 前窗：-60td 至入场
        pre = industry_returns(C, e - 60, 60)
        if pre is not None:
            nm = [i for i in named if i in pre.index]
            row["pre60"] = (pre[nm].mean() - pre.mean()) * 100 if nm else np.nan
        ev_rows.append(row)
    df = pd.DataFrame(ev_rows).set_index("id")
    pd.set_option("display.width", 200)
    print("\n=== 逐事件（点名组等权超额，pp）===")
    print(df.round(2).to_string())
    print("\n=== 时代汇总 ===")
    for era in ("A", "B"):
        s = df[df.era == era]
        print(f"时代{era}({len(s)}事件): 前60日 {s.pre60.mean():+.2f}pp | +20日 {s.f20.mean():+.2f}pp | "
              f"+60日(主判据) {s.f60.mean():+.2f}pp | +120日 {s.f120.mean():+.2f}pp | H3秩相关 {s.rho60.mean():+.3f}")
    a, b = df[df.era == "A"].f60.mean(), df[df.era == "B"].f60.mean()
    both = df.f60.mean()
    print(f"\n主判据H1(+60日): 时代A {a:+.2f}pp / 时代B {b:+.2f}pp / 合并 {both:+.2f}pp")
    if a > 0 and b > 0 and both >= 1.0: v = "候选假设 ✅"
    elif a > 0 and b > 0: v = "方向性观察（同向但<+1.0pp）"
    else: v = "否决 ❌（两时代不同向或非正）"
    print("预注册判定:", v)
    df.round(3).to_csv("政策点名_事件结果.csv", encoding="utf-8-sig")

if __name__ == "__main__":
    main()
