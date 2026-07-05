#!/bin/bash
# 盘后手动刷新数据（也可被定时任务调用）。生成/更新 data.js。
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  echo "首次运行：创建虚拟环境并安装依赖（约2-5分钟，需联网）…"
  python3 -m venv .venv || { echo "创建虚拟环境失败，请确认已装 Python3"; exit 1; }
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi
echo "[$(date '+%F %T')] 开始拉取并生成候选池..."
./.venv/bin/python pipeline.py
echo "[$(date '+%F %T')] 完成。"
