import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseDir = path.dirname(fileURLToPath(import.meta.url));
const rows = fs.readFileSync(path.join(baseDir, "fetch_results.jsonl"), "utf8").trim().split(/\r?\n/).map(JSON.parse);
function timestampSeconds(value) {
  const match = value.match(/(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/);
  return match ? Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(match[4]) / 1000 : null;
}
const checks = [];
for (const row of rows) {
  const prefix = String(row.index).padStart(3, "0");
  const srtPath = row.selectedTrack === "note-text" ? null : path.join(baseDir, "raw_srt", `${prefix}_${row.noteId}_${row.selectedTrack}.srt`);
  const transcriptPath = row.transcriptFile ? path.join(baseDir, row.transcriptFile) : null;
  const problems = [];
  if (row.status !== "ok") problems.push(`status=${row.status}`);
  if (srtPath && !fs.existsSync(srtPath)) problems.push("selected SRT missing");
  if (!transcriptPath || !fs.existsSync(transcriptPath)) problems.push("plain transcript missing");
  let lastSubtitleSecond = null;
  if (srtPath && fs.existsSync(srtPath)) {
    const timestamps = [...fs.readFileSync(srtPath, "utf8").matchAll(/-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})/g)].map((match) => timestampSeconds(match[1])).filter((v) => v != null);
    lastSubtitleSecond = timestamps.at(-1) ?? null;
    if (!timestamps.length) problems.push("no SRT timestamps");
    if (lastSubtitleSecond != null && row.durationSeconds && row.durationSeconds - lastSubtitleSecond > 20) problems.push(`subtitle ends ${Math.round(row.durationSeconds - lastSubtitleSecond)}s before video`);
  }
  if (transcriptPath && fs.existsSync(transcriptPath)) {
    const body = fs.readFileSync(transcriptPath, "utf8").split(/\n\n/).slice(1).join("\n\n").replace(/#[^#\n]*\[话题\]#/g, "").replace(/#/g, "").trim();
    if (body.length < 20) problems.push("正文有效内容过短，需检查图片文字");
  }
  checks.push({index: row.index, noteId: row.noteId, durationSeconds: row.durationSeconds, lastSubtitleSecond, problems});
}
const rawFiles = fs.readdirSync(path.join(baseDir, "raw_srt")).filter((name) => name.endsWith(".srt"));
const transcriptFiles = fs.readdirSync(path.join(baseDir, "transcripts")).filter((name) => name.endsWith(".txt"));
const problemRows = checks.filter((row) => row.problems.length);
const totalDuration = rows.reduce((sum, row) => sum + (row.durationSeconds || 0), 0);
const totalCharacters = rows.reduce((sum, row) => sum + (row.transcriptCharacters || 0), 0);
const expectedRawFiles = rows.reduce((sum, row) => sum + (row.downloadedTracks?.length || 0), 0);
const report = ["# 字幕完整性核验", "", `- 主页笔记：${rows.length} 条`, `- 视频：${rows.filter((row) => row.selectedTrack !== "note-text").length} 条`, `- 图文笔记：${rows.filter((row) => row.selectedTrack === "note-text").length} 条`, `- 成功状态：${rows.filter((row) => row.status === "ok").length} 条`, `- 原始 SRT：${rawFiles.length} 个（应为 ${expectedRawFiles} 个）`, `- 纯文本稿：${transcriptFiles.length} 个`, `- 视频合计时长：${totalDuration} 秒（${Math.floor(totalDuration / 60)} 分 ${Math.round(totalDuration % 60)} 秒）`, `- 中文正文：${totalCharacters} 字符`, `- 完整性异常：${problemRows.length} 条`, "", problemRows.length ? "## 异常明细" : `全部${rows.length}条均有可读中文正文；平台字幕均含有效时间戳，且未发现提前20秒以上结束的明显截断。`, "", ...problemRows.map((row) => `- ${String(row.index).padStart(3, "0")} ${row.noteId}: ${row.problems.join("；")}`), ""];
fs.writeFileSync(path.join(baseDir, "verification_report.md"), report.join("\n"), "utf8");
console.log(report.join("\n"));
if (problemRows.length || rawFiles.length !== expectedRawFiles || transcriptFiles.length !== rows.filter((row) => row.status === "ok").length) process.exitCode = 1;
