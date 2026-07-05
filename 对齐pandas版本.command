#!/bin/zsh
# 对齐 pandas 版本（项目锁定 2.3.3）——在任何一台机器上双击运行即可。
# 背景：两台机器经 OneDrive 共享 .pkl 缓存，pandas 3.x 写的 pickle 在 2.3.3 下读不了，
#       曾把回测缓存覆盖损坏（2026-07-03）。requirements.txt 已锁 pandas==2.3.3。
cd "$(dirname "$0")"
echo "== 项目锁定 pandas==2.3.3 =="

PY=""
if [ -x ".venv/bin/python" ] && .venv/bin/python -c "" 2>/dev/null; then
  PY=".venv/bin/python"
  echo "使用项目 venv: $PY"
else
  echo "本机没有可用的项目 venv（.venv 是另一台机器建的，二进制不通用是正常的）。"
  for cand in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v $cand >/dev/null 2>&1; then PY_SYS=$cand; break; fi
  done
  echo "用 $PY_SYS 新建本机专用 venv：.venv-$(hostname -s)"
  $PY_SYS -m venv ".venv-$(hostname -s)"
  PY=".venv-$(hostname -s)/bin/python"
  echo "⚠️ 注意：之后本机请用 $PY 运行脚本（或自行把 .venv 指向它）。"
fi

CUR=$($PY -c "import pandas; print(pandas.__version__)" 2>/dev/null || echo "未安装")
echo "当前 pandas: $CUR"
if [ "$CUR" = "2.3.3" ]; then
  echo "✅ 已一致，无需处理。"
else
  echo "安装锁定版本…"
  $PY -m pip install --quiet "pandas==2.3.3" "numpy>=2.0,<3" || { echo "❌ 安装失败，请手动: $PY -m pip install pandas==2.3.3"; exit 1; }
  echo "✅ 已对齐为 2.3.3。"
  echo ""
  echo "⚠️ 本机之前用 pandas 3.x 写过的 .pkl 缓存现在读不了（格式不兼容），"
  echo "   报 NotImplementedError/StringDtype 时删除对应 .backtest_cache_*/.toplist_cache_* 重拉即可。"
fi
echo ""
echo "（护栏：pipeline.py 会在版本不符时拒绝写共享缓存，防止再次互相污染。）"
read -k 1 "?按任意键退出"
