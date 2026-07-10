# -*- coding: utf-8 -*-
"""v6.4.1 时点口径基线重跑（PIT行业+PIT ST；数据正确性修复，直接替换基线，报告相对v6.4的漂移）。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as B
import portfolio_backtest as PB
for start, end, w in [("20240618", "20260630", "2024-2026"), ("20190101", "20231231", "2019-2023")]:
    for tag, kw in [("base", dict(no_satellite=True)),
                    ("satA", dict(no_satellite=False, gate="codexA")),
                    ("satC", dict(no_satellite=False, gate="classic"))]:
        t0 = time.time()
        curve, trades, kills, wd, meta = PB.run_portfolio(start, end, f"v641_{w}_{tag}", base_mode="strong3", **kw)
        PB.report(curve, trades, kills, wd, f"v641_{w}_{tag}", meta)
        B.log(f"[done] v641_{w}_{tag} {time.time()-t0:.0f}s")
print("V641_ALL_DONE")
