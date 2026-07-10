# -*- coding: utf-8 -*-
"""v6.4 重验驱动（预注册见 02_回测报告/v64-一致性修复与重验-预注册-2026-07-10.md）。20次组合级回测顺序执行。"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B
import portfolio_backtest as PB
import 策略规格 as SPEC

WINDOWS = [("20240618", "20260630", "2024-2026"), ("20190101", "20231231", "2019-2023")]

def run(start, end, tag, **kw):
    t0 = time.time()
    curve, trades, kills, wd, meta = PB.run_portfolio(start, end, tag, **kw)
    PB.report(curve, trades, kills, wd, tag, meta)
    B.log(f"[done] {tag} 用时{time.time()-t0:.0f}s")

for start, end, w in WINDOWS:
    # 波次A：v6.4新基线三件套（锚点相位）
    run(start, end, f"v64_{w}_base",  base_mode="strong3", no_satellite=True)
    run(start, end, f"v64_{w}_satA",  base_mode="strong3", no_satellite=False, gate="codexA")
    run(start, end, f"v64_{w}_satC",  base_mode="strong3", no_satellite=False, gate="classic")
    # 波次B：相位敏感性（纯底仓×5相位）
    for k in range(5):
        run(start, end, f"v64_{w}_base_ph{k}", base_mode="strong3", no_satellite=True, phase=k)
    # 波次C：广度变体（收盘vs昨收）
    SPEC.BREADTH_MODE = "prevclose"
    run(start, end, f"v64_{w}_base_bpc", base_mode="strong3", no_satellite=True)
    run(start, end, f"v64_{w}_satA_bpc", base_mode="strong3", no_satellite=False, gate="codexA")
    SPEC.BREADTH_MODE = "body"
print("V64_RERUN_ALL_DONE")
