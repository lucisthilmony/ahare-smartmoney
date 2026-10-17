#!/bin/bash
# 双击：设置"每个工作日 18:30 自动刷新候选池"（直接跑 pipeline.py 生成 data.js）。
# 为什么是 18:30：交易所/Tushare 的当日收盘数据通常要到收盘后较晚才发布，
#                15:10 太早 → 只会取到上一交易日，候选池看着"没更新"。
# 直接跑 pipeline（不再依赖数据服务是否开着）；但 Mac 需在 18:30 处于唤醒状态。
cd "$(dirname "$0")"
DIR="$(pwd)"
LOG="$DIR/refresh.log"
NEW="30 18 * * 1-5 cd \"$DIR\" && ./.venv/bin/python pipeline.py >> \"$LOG\" 2>&1 # ashort-refresh"

# 先删掉旧任务（含早先 15:10 的 curl 版、以及任何旧的 ashort-refresh 版），再写入新的
( crontab -l 2>/dev/null | grep -v "ashort-refresh" | grep -v "127.0.0.1:8787/api/refresh" ; echo "$NEW" ) | crontab -

echo "✅ 已设置：每个工作日 18:30 自动刷新候选池（直接生成 data.js，日志写入 refresh.log）。"
echo ""
echo "重要说明："
echo "  • 改到 18:30 的原因：当日收盘数据发布晚，15点刚收盘时拉到的是前一天。"
echo "  • 现在不依赖数据服务是否开着——到点直接拉数、重写 data.js。"
echo "  • Mac 需在 18:30 处于唤醒状态（睡眠/关机不会补跑）。错过了就晚上双击「盘后刷新数据」手动补。"
echo "  • 若没执行：系统设置 → 隐私与安全性 → 完全磁盘访问权限，给 /usr/sbin/cron 授权后重试。"
echo "  • 取消任务：终端运行  crontab -e  删掉含 ashort-refresh 的那一行。"
echo ""
echo "（按任意键关闭本窗口）"
read -n 1
