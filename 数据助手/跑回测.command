#!/bin/bash
# 双击跑回测。首次会拉历史数据(数分钟,缓存后再跑很快)。报告生成在上级目录。
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  echo "首次运行：建虚拟环境并装依赖…"
  python3 -m venv .venv && ./.venv/bin/pip install --upgrade pip && ./.venv/bin/pip install -r requirements.txt
fi
./.venv/bin/python -c "import matplotlib" 2>/dev/null || ./.venv/bin/pip install matplotlib
echo "开始回测（首次拉数据较慢，请耐心等待）…"
./.venv/bin/python backtest.py
echo ""
echo "完成！报告：backtest_report.md ｜ 逐笔：backtest_trades.csv ｜ 曲线：backtest_equity.png（均在上级文件夹）"
echo "（按任意键关闭）"
