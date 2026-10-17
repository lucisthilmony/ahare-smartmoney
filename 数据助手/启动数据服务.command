#!/bin/bash
# 双击启动本地数据服务（Mac）。首次需 chmod +x（见 README 第3步）。
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  echo "首次运行：创建虚拟环境并安装依赖（约2-5分钟，需联网）…"
  python3 -m venv .venv || { echo "创建虚拟环境失败，请确认已装 Python3"; exit 1; }
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi
echo "正在启动 A股短线波段 · 数据服务 ..."
# 若已有旧服务占用端口，先停掉，确保用最新代码与 token
lsof -ti tcp:8787 | xargs kill -9 2>/dev/null
sleep 1
( sleep 3 && open "http://127.0.0.1:8787/" ) &
./.venv/bin/python server.py
echo "服务已停止，可关闭本窗口。"
