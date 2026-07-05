# ashare-distill（A股策略蒸馏 · 数据助手）

A股短线策略蒸馏项目的数据与回测代码：tushare/东财数据管线、情绪指数、尾盘信号、席位筛选、组合回测。策略文档与回测报告在上级目录（`01_策略文档`～`04_原始研究材料`，随 OneDrive 同步，不入本仓库）。

## 当前状态（2026-07-05）

- M3 Max cron 工作日 4 条：14:40 `尾盘信号.py`、18:30 `pipeline.py`、18:40 `情绪指数.py`、19:10 `前向_席位筛选.py`（日志 `*.log`，不入库）
- 2026-07 回测结论：样本外时代特异性失效，仅「风控+出场+strong3底仓」存活；判定纪律 = 双窗口同向 + 前向裁判（详见上级目录回测报告）

## 敏感信息与不入库文件

- `config.py` 含个人 TUSHARE_TOKEN，**已 gitignore 不入库**；新机器部署时按 `README_数据接入说明.md` 手动创建并填 token
- `.venv/`、`*.pkl` 回测缓存（~1.1G）、`*.log`、`*.csv` 均不入库
- 本目录在 OneDrive 内，`.git` 也会被 OneDrive 同步——在其他机器上不要直接打开 OneDrive 里的这个 `.git`，用 Mini 远端 clone

## 约定

- 远端：`macmini:repos/ashare-distill.git`（Mini 裸仓库，Tailscale 内网）
- 结束工作前把状态变化写进本文件并 commit/push
