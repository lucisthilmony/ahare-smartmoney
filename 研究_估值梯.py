# -*- coding: utf-8 -*-
"""估值梯月度刻度（个人再入场协议§2配套）。手动运行：打印沪深300 PE分位与三档锚点。"""
import sys, time
import pandas as pd
sys.path.insert(0, ".")
import pipeline as P

rows = []
for y0, y1 in (("20190101","20201231"),("20210101","20221231"),("20230101","20241231"),("20250101","20991231")):
    rows.append(P._ts_query("index_dailybasic", ts_code="000300.SH", start_date=y0, end_date=y1)); time.sleep(1.2)
df = pd.concat(rows)
df["pe_ttm"] = pd.to_numeric(df["pe_ttm"], errors="coerce")
pe = df.dropna(subset=["pe_ttm"]).sort_values("trade_date")["pe_ttm"]
px = P._ts_query("index_daily", ts_code="000300.SH", start_date="20260101", end_date="20991231").sort_values("trade_date")
level, cur = float(px["close"].iloc[-1]), pe.iloc[-1]
pct = (pe < cur).mean() * 100
print(f"沪深300 @{px['trade_date'].iloc[-1]}: 收盘{level:.0f} PE(TTM){cur:.1f} 分位{pct:.0f}%")
for q, tag, w in ((0.50,"B1",15),(0.30,"B2",30),(0.15,"B3",45)):
    t = pe.quantile(q)
    print(f"  {tag}({int(q*100)}分位) PE{t:.1f} ≈ {level*t/cur:.0f}点 ({(t/cur-1)*100:+.0f}%) → 权益目标{w}%")
if pct <= 50: print("  ⚠️ 梯B已有档位触发，对照协议执行")
