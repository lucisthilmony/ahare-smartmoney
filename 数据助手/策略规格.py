# -*- coding: utf-8 -*-
"""
策略规格（v6.4 · 2026-07-10）——实盘与回测共用的唯一决策参数/函数源。
背景：外部审查指出实盘与回测存在四处不同源（A门实现、每日开仓数、换仓相位、成本口径）。
本模块是唯一权威；尾盘信号.py / 底仓引擎.py / portfolio_backtest.py / 前向_席位筛选.py 一律从这里取，禁止各自实现。
任何参数改动 = 规则变更，须走双窗口+前向纪律并更新总档案。
"""

# ---- 底仓 strong3 ----
ANCHOR = "20240618"          # 换仓相位锚点（=样本内回测窗口首日）；检查点=自锚点起交易日计数 mod 5 == 0
BASE_TARGET = {60: 50, 40: 30, 20: 10, 0: 0}   # 档位上限% → 底仓目标权重%

def checkpoint_offset(win_dates, ts_query):
    """给定回测窗口交易日列表，返回 offset：win_dates[i] 是检查点 ⟺ i % 5 == offset（锚点相位对齐）。
    ts_query = P._ts_query（避免循环导入）。窗口首日=锚点时 offset=0（与历史回测/实盘一致）。"""
    lo, hi = min(win_dates[0], ANCHOR), max(win_dates[-1], ANCHOR)
    cal = ts_query("trade_cal", exchange="SSE", start_date=lo, end_date=hi, is_open="1")
    days = sorted(cal["cal_date"].tolist())
    pos = {d: i for i, d in enumerate(days)}
    return (pos[ANCHOR] - pos[win_dates[0]]) % 5

# ---- 卫星层 ----
MAX_OPEN_DAY = 1             # v6.4：每日最多开仓数（与实盘执行卡一致；此前回测=2、实盘=1不同源）
MAX_POS = 3                  # 最多同时持仓

def _n(v, d=0.0):
    try:
        return float(v) if v is not None else d
    except Exception:
        return d

def gate_codexA(c):
    """A门（回踩修复型）四条件。兼容回测候选(amt20)与实盘候选(amt20_yi)字段名。
    字段缺失（旧数据）返回 None=无法判定；调用方自行决定降级行为。"""
    amt = c.get("amt20_yi", c.get("amt20"))
    prior = c.get("prior60")
    if amt is None or prior is None:
        return None
    return (_n(c.get("sec_rank"), 999) <= 5 and _n(c.get("rs")) > 0
            and _n(prior) < 0 and 2 <= _n(amt) < 5)

def satellite_gate(c, mode):
    """mode: 'classic'=不加门 / 'codexA'=仅回踩修复型。返回 True/False/None(无法判定)。"""
    if mode != "codexA":
        return True
    return gate_codexA(c)

# ---- 成本 ----
def stamp_rate(date):
    """卖出印花税：2023-08-28减半（此前0.1%，之后0.05%）。date: YYYYMMDD字符串。"""
    return 0.0005 if str(date) >= "20230828" else 0.001

COMM_RATE, COMM_MIN = 0.00025, 5.0
SLIP = {"main": 0.001, "chinext": 0.002, "star": 0.002}   # 每边滑点
ETF_COST = 0.0003

# ---- 市场广度口径（v6.4 澄清）----
# 现行实现 = 阳线家数（收盘>开盘），Tushare回测与实盘同口径、两窗口结论在此口径下成立。
# "收盘>昨收"为待验变体（见 v64重验预注册），未通过双窗口对照前不得替换。
BREADTH_MODE = "body"        # body=收盘vs开盘（现行）/ prevclose=收盘vs昨收（变体，仅回测实验用）
