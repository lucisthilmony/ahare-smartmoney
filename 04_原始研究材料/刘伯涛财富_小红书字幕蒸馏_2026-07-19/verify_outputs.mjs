import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseDir = path.dirname(fileURLToPath(import.meta.url));
const rows = fs.readFileSync(path.join(baseDir, "fetch_results.jsonl"), "utf8").trim().split(/\r?\n/).map(JSON.parse);

function timestampSeconds(value) {
  const match = value.match(/(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/);
  if (!match) return null;
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(match[4]) / 1000;
}

const checks = [];
for (const row of rows) {
  const prefix = String(row.index).padStart(3, "0");
  const srtPath = path.join(baseDir, "raw_srt", `${prefix}_${row.noteId}_${row.selectedTrack}.srt`);
  const transcriptPath = path.join(baseDir, row.transcriptFile || "");
  const problems = [];

  if (row.status !== "ok") problems.push(`status=${row.status}`);
  if (!fs.existsSync(srtPath)) problems.push("selected SRT missing");
  if (!fs.existsSync(transcriptPath)) problems.push("plain transcript missing");

  let lastSubtitleSecond = null;
  if (fs.existsSync(srtPath)) {
    const srt = fs.readFileSync(srtPath, "utf8");
    const timestamps = [...srt.matchAll(/-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})/g)].map((match) => timestampSeconds(match[1])).filter((value) => value != null);
    lastSubtitleSecond = timestamps.at(-1) ?? null;
    if (!timestamps.length) problems.push("no SRT timestamps");
    if (lastSubtitleSecond != null && row.durationSeconds && row.durationSeconds - lastSubtitleSecond > 20) {
      problems.push(`subtitle ends ${Math.round(row.durationSeconds - lastSubtitleSecond)}s before video`);
    }
  }

  if (fs.existsSync(transcriptPath)) {
    const text = fs.readFileSync(transcriptPath, "utf8");
    if (text.length < 100) problems.push("transcript too short");
  }

  checks.push({ index: row.index, noteId: row.noteId, durationSeconds: row.durationSeconds, lastSubtitleSecond, problems });
}

const rawFiles = fs.readdirSync(path.join(baseDir, "raw_srt")).filter((name) => name.endsWith(".srt"));
const transcriptFiles = fs.readdirSync(path.join(baseDir, "transcripts")).filter((name) => name.endsWith(".txt"));
const problemRows = checks.filter((row) => row.problems.length);
const totalDuration = rows.reduce((sum, row) => sum + (row.durationSeconds || 0), 0);
const totalCharacters = rows.reduce((sum, row) => sum + (row.transcriptCharacters || 0), 0);

const report = [
  "# 字幕完整性核验",
  "",
  `- 清单视频：${rows.length} 条`,
  `- 成功状态：${rows.filter((row) => row.status === "ok").length} 条`,
  `- 原始 SRT：${rawFiles.length} 个（每条 source、zh-CN、en-US 三轨）`,
  `- 纯文本字幕：${transcriptFiles.length} 个`,
  `- 合计时长：${totalDuration} 秒（${Math.floor(totalDuration / 60)} 分 ${totalDuration % 60} 秒）`,
  `- 中文字幕正文：${totalCharacters} 字符`,
  `- 完整性异常：${problemRows.length} 条`,
  "",
  problemRows.length ? "## 异常明细" : "全部30条 source 中文字幕均存在、含有效时间戳，且未发现提前20秒以上结束的明显截断。",
  "",
  ...problemRows.map((row) => `- ${String(row.index).padStart(3, "0")} ${row.noteId}: ${row.problems.join("；")}`),
  "",
];

fs.writeFileSync(path.join(baseDir, "verification_report.md"), report.join("\n"), "utf8");
console.log(report.join("\n"));

if (problemRows.length || rows.length !== 30 || rawFiles.length !== 90 || transcriptFiles.length !== 30) process.exitCode = 1;
