#!/bin/bash
# 双击：立刻手动跑一次尾盘信号（读实时大盘+候选池 → 三道门 → 推送 Discord）。
# 用途：① 想临时看一眼信号；② 测试链路是否正常（不依赖 cron/定时任务）。
cd "$(dirname "$0")"
echo "[$(date '+%F %T')] 手动跑尾盘信号（会推送到 Discord）…"
echo ""
if [ -x "./.venv/bin/python" ]; then
  ./.venv/bin/python 尾盘信号.py
else
  echo "(没找到 .venv，用系统 python3)"; python3 尾盘信号.py
fi
echo ""
echo "跑完了。上面若显示 [ok] discord 204 = 已推送成功。"
echo "（按任意键关闭本窗口）"
read -n 1
