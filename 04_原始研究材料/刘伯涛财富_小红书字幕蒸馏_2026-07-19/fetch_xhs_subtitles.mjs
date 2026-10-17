import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseDir = path.dirname(fileURLToPath(import.meta.url));
const inputPath = path.join(baseDir, ".source_links_with_ephemeral_tokens.jsonl");
const rawDir = path.join(baseDir, "raw_srt");
const transcriptDir = path.join(baseDir, "transcripts");
const detailDir = path.join(baseDir, "metadata");

for (const dir of [rawDir, transcriptDir, detailDir]) {
  fs.mkdirSync(dir, { recursive: true });
}

const userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36";
const items = fs.readFileSync(inputPath, "utf8").trim().split(/\r?\n/).map((line) => JSON.parse(line));

function parseInitialState(html) {
  const match = html.match(/<script[^>]*>window\.__INITIAL_STATE__=([\s\S]*?)<\/script>/);
  if (!match) throw new Error("initial_state_missing");
  return JSON.parse(match[1].replace(/\bundefined\b/g, "null"));
}

function csvCell(value) {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function srtToPlain(srt) {
  const blocks = srt.replace(/\r/g, "").trim().split(/\n{2,}/);
  const lines = [];
  for (const block of blocks) {
    const parts = block.split("\n");
    const start = /^\d+$/.test(parts[0]?.trim() || "") ? 2 : 1;
    const text = parts.slice(start).join(" ").replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
    if (text && text !== lines.at(-1)) lines.push(text);
  }
  return lines.join("\n");
}

function displayTitle(note, fallback) {
  if (note.title?.trim()) return note.title.trim();
  const desc = (note.desc || "").replace(/#[^#\n]*\[话题\]#/g, "").replace(/\s+/g, " ").trim();
  return desc || fallback;
}

function localTime(ms) {
  if (!ms) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(ms)).replaceAll("/", "-");
}

const manifest = [];
const combined = ["# 刘伯涛财富：小红书公开视频字幕全集", "", `抓取时间：${new Date().toISOString()}`, "", "说明：正文优先采用平台标记为 source 的中文字幕；保留原始 SRT 便于逐句核查。", ""];
const failures = [];

for (const item of items) {
  const prefix = String(item.index).padStart(3, "0");
  const publicUrl = `https://www.xiaohongshu.com/explore/${item.id}`;
  const fetchUrl = `${publicUrl}?xsec_token=${encodeURIComponent(item.xsecToken)}&xsec_source=pc_user`;
  const result = {
    index: item.index,
    noteId: item.id,
    publicUrl,
    inventoryTitle: item.title,
    fetchedAt: new Date().toISOString(),
  };

  try {
    const pageResponse = await fetch(fetchUrl, { headers: { "user-agent": userAgent, referer: "https://www.xiaohongshu.com/" } });
    if (!pageResponse.ok) throw new Error(`page_http_${pageResponse.status}`);
    const html = await pageResponse.text();
    const state = parseInitialState(html);
    const map = state.note?.noteDetailMap || {};
    const entry = map[item.id] || map[Object.keys(map)[0]];
    if (!entry?.note) throw new Error("note_missing");

    const note = entry.note;
    const mediaV2 = typeof note.video?.mediaV2 === "string" ? JSON.parse(note.video.mediaV2) : (note.video?.mediaV2 || {});
    const tracks = mediaV2.video?.subtitles || mediaV2.subtitles || {};
    const selectedGroup = tracks.source?.length ? "source" : (tracks["zh-CN"]?.length ? "zh-CN" : "");
    const selectedTrack = selectedGroup ? tracks[selectedGroup][0] : null;
    const title = displayTitle(note, item.title);
    const downloadedTracks = [];

    for (const group of ["source", "zh-CN", "en-US"]) {
      for (let trackIndex = 0; trackIndex < (tracks[group] || []).length; trackIndex += 1) {
        const track = tracks[group][trackIndex];
        const subtitleResponse = await fetch(track.url, { headers: { "user-agent": userAgent, referer: publicUrl } });
        if (!subtitleResponse.ok) throw new Error(`subtitle_${group}_http_${subtitleResponse.status}`);
        const subtitleText = await subtitleResponse.text();
        const suffix = trackIndex ? `_${trackIndex + 1}` : "";
        const filename = `${prefix}_${item.id}_${group}${suffix}.srt`;
        fs.writeFileSync(path.join(rawDir, filename), subtitleText, "utf8");
        downloadedTracks.push({ group, language: track.language, format: track.format, type: track.type, filename, url: track.url });
      }
    }

    if (!selectedTrack) throw new Error("chinese_subtitle_missing");
    const selectedFile = downloadedTracks.find((track) => track.group === selectedGroup)?.filename;
    const selectedSrt = fs.readFileSync(path.join(rawDir, selectedFile), "utf8");
    const plainText = srtToPlain(selectedSrt);
    const transcriptFile = `${prefix}_${item.id}.txt`;
    fs.writeFileSync(path.join(transcriptDir, transcriptFile), `${title}\n${publicUrl}\n\n${plainText}\n`, "utf8");

    const streams = mediaV2.stream || note.video?.media?.stream || {};
    const stream = streams.h264?.[0] || streams.h265?.[0] || null;
    Object.assign(result, {
      status: "ok",
      title,
      description: note.desc || "",
      publishedLocal: localTime(note.time),
      publishedEpochMs: note.time || null,
      durationSeconds: note.video?.capa?.duration || mediaV2.video?.duration || null,
      selectedTrack: selectedGroup,
      transcriptFile: path.relative(baseDir, path.join(transcriptDir, transcriptFile)),
      transcriptCharacters: plainText.length,
      downloadedTracks,
      video: stream ? {
        format: stream.format,
        codec: stream.video_codec,
        width: stream.width,
        height: stream.height,
        durationMs: stream.duration,
        sizeBytes: stream.size,
        url: stream.master_url,
      } : null,
    });

    combined.push(`## ${prefix}. ${title}`, "", `- 发布：${result.publishedLocal || "未知"}`, `- 时长：${result.durationSeconds || "未知"} 秒`, `- 来源：${publicUrl}`, `- 字幕：${selectedGroup}`, "", plainText, "");
    manifest.push(result);
    process.stdout.write(`[${prefix}/${items.length}] OK ${title}\n`);
  } catch (error) {
    result.status = "error";
    result.error = String(error?.message || error);
    manifest.push(result);
    failures.push(result);
    process.stdout.write(`[${prefix}/${items.length}] ERROR ${item.id}: ${result.error}\n`);
  }

  fs.writeFileSync(path.join(detailDir, `${prefix}_${item.id}.json`), `${JSON.stringify(result, null, 2)}\n`, "utf8");
}

const csvHeader = ["index", "note_id", "published_local", "duration_seconds", "title", "status", "selected_track", "characters", "public_url"];
const csvRows = manifest.map((row) => [row.index, row.noteId, row.publishedLocal, row.durationSeconds, row.title || row.inventoryTitle, row.status, row.selectedTrack, row.transcriptCharacters, row.publicUrl].map(csvCell).join(","));
fs.writeFileSync(path.join(baseDir, "video_manifest.csv"), `${csvHeader.map(csvCell).join(",")}\n${csvRows.join("\n")}\n`, "utf8");
fs.writeFileSync(path.join(baseDir, "all_transcripts.md"), `${combined.join("\n")}\n`, "utf8");
fs.writeFileSync(path.join(baseDir, "fetch_results.jsonl"), `${manifest.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
fs.writeFileSync(path.join(baseDir, "fetch_report.md"), `# 抓取报告\n\n- 账号：刘伯涛财富\n- 公开视频清单：${items.length} 条\n- 成功：${manifest.length - failures.length} 条\n- 失败：${failures.length} 条\n- 平台原始 SRT：${manifest.reduce((sum, row) => sum + (row.downloadedTracks?.length || 0), 0)} 个\n- 抓取时间：${new Date().toISOString()}\n\n${failures.length ? `## 失败项目\n\n${failures.map((row) => `- ${row.index}. ${row.noteId}: ${row.error}`).join("\n")}\n` : "全部条目均已取得中文字幕。\n"}`,
  "utf8",
);

console.log(`Done: ${manifest.length - failures.length}/${items.length} successful`);
