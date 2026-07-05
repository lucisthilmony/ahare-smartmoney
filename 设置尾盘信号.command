#!/bin/bash
# 双击：设置"每个交易日 14:40 自动跑尾盘信号 → 推送 Discord"。
# 前置：① 先双击过「盘后刷新数据」建好 .venv 环境；② 每天 18:30 盘后任务已生成当天候选池(data.js)。
cd "$(dirname "$0")"
DIR="$(pwd)"
LOG="$DIR/signal.log"
NEW="40 14 * * 1-5 cd \"$DIR\" && ./.venv/bin/python 尾盘信号.py >> \"$LOG\" 2>&1 # ashort-signal"

# 删掉旧的 ashort-signal 行，再写入新的（不影响 18:30 的 ashort-refresh）
( crontab -l 2>/dev/null | grep -v "ashort-signal" ; echo "$NEW" ) | crontab -

echo "✅ 已设置：每个交易日 14:40 自动跑尾盘信号，推送到你的 Discord（日志写入 signal.log）。"
echo ""
echo "说明："
echo "  • 需要 Mac 在 14:40 处于唤醒状态（睡眠/关机不会补跑）。"
echo "  • 只发信号、不下单；收到执行卡后，点买前请在券商/同花顺再确认分时。"
echo "  • 若没执行：系统设置 → 隐私与安全性 → 完全磁盘访问权限，给 /usr/sbin/cron 授权后重试。"
echo "  • 取消：终端运行  crontab -e  ，删掉含 ashort-signal 的那一行。"
echo ""
echo "（按任意键关闭本窗口）"
read -n 1
