# 刘伯涛财富小红书字幕档案

这是截至2026-07-19主页可见的30条公开视频快照，不包括此后新增、删除、私密或登录后仍不可见的内容。

## 主要文件

- `蒸馏报告.md`：跨视频观点、重复、矛盾、证据风险和可实验规则。
- `all_transcripts.md`：30条中文字幕合并全文。
- `video_manifest.csv`：视频ID、日期、时长、标题、字幕状态和公开链接。
- `transcripts/`：每条视频一份纯文本中文字幕。
- `raw_srt/`：平台原始SRT；每条保存 source、zh-CN、en-US 三轨。
- `metadata/`：每条视频的抓取元数据、字幕轨和视频流信息。
- `fetch_report.md`：抓取成功/失败统计。
- `verification_report.md`：字幕数量、时间戳和截断检查。
- `fetch_results.jsonl`：机器可读的完整结果。
- `fetch_xhs_subtitles.mjs`、`verify_outputs.mjs`：抓取与核验脚本。

## 证据约定

`source` 轨作为中文正文主来源；`zh-CN` 和 `en-US` 轨用于交叉检查。平台字幕可能包含语音识别同音错字，原始SRT保持不动，蒸馏报告只在理解层面按上下文归一。

页面访问令牌属于短期抓取参数，日后重跑可能需要从主页重新取得；公开视频的稳定身份以 `note_id` 和无令牌公开URL记录在 `video_manifest.csv` 中。
