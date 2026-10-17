import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseDir = path.dirname(fileURLToPath(import.meta.url));
const inputPath = path.join(baseDir, ".source_links_with_ephemeral_tokens.jsonl");
const rawDir = path.join(baseDir, "raw_srt");
const transcriptDir = path.join(baseDir, "transcripts");
const detailDir = path.join(baseDir, "metadata");
for (const dir of [rawDir, transcriptDir, detailDir]) fs.mkdirSync(dir, { recursive: true });

const userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36";
const items = fs.readFileSync(inputPath, "utf8").trim().split(/\r?\n/).map(JSON.parse);

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
  return new Intl.DateTimeFormat("zh-CN", {timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false}).format(new Date(ms)).replaceAll("/", "-");
}

const manifest = [];
const combined = ["# 上海老太太：小红书公开视频字幕全集", "", `抓取时间：${new Date().toISOString()}`, "", "说明：正文优先采用平台标记为 source 的中文字幕；保留原始 SRT 便于逐句核查。", ""];
const failures = [];

for (const item of items) {
  const prefix = String(item.index).padStart(3, "0");
  const publicUrl = `https://www.xiaohongshu.com/explore/${item.id}`;
  const fetchUrl = `${publicUrl}?xsec_token=${encodeURIComponent(item.xsecToken)}&xsec_source=pc_user`;
  const result = {index: item.index, noteId: item.id, publicUrl, inventoryTitle: item.title, fetchedAt: new Date().toISOString()};
  try {
    const pageResponse = await fetch(fetchUrl, {headers: {"user-agent": userAgent, referer: "https://www.xiaohongshu.com/"}});
    if (!pageResponse.ok) throw new Error(`page_http_${pageResponse.status}`);
    const state = parseInitialState(await pageResponse.text());
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
        const subtitleResponse = await fetch(track.url, {headers: {"user-agent": userAgent, referer: publicUrl}});
        if (!subtitleResponse.ok) throw new Error(`subtitle_${group}_http_${subtitleResponse.status}`);
        const suffix = trackIndex ? `_${trackIndex + 1}` : "";
        const filename = `${prefix}_${item.id}_${group}${suffix}.srt`;
        fs.writeFileSync(path.join(rawDir, filename), await subtitleResponse.text(), "utf8");
        downloadedTracks.push({group, language: track.language, format: track.format, type: track.type, filename, url: track.url});
      }
    }
    const fallbackSrtPath = path.join(rawDir, `${prefix}_${item.id}_local-frame.srt`);
    if (!selectedTrack && fs.existsSync(fallbackSrtPath)) {
      const plainText = srtToPlain(fs.readFileSync(fallbackSrtPath, "utf8"));
      const transcriptFile = `${prefix}_${item.id}.txt`;
      fs.writeFileSync(path.join(transcriptDir, transcriptFile), `${title}\n${publicUrl}\n\n${plainText}\n`, "utf8");
      Object.assign(result, {status: "ok", title, description: note.desc || "", publishedLocal: localTime(note.time), publishedEpochMs: note.time || null, durationSeconds: note.video?.capa?.duration || mediaV2.video?.duration || 30, selectedTrack: "local-frame", sourceType: "画面内嵌字幕逐帧核对", transcriptFile: path.relative(baseDir, path.join(transcriptDir, transcriptFile)), transcriptCharacters: plainText.length, downloadedTracks: [{group: "local-frame", language: "zh-CN", format: "srt", type: "manual-frame-verification", filename: path.basename(fallbackSrtPath)}]});
      combined.push(`## ${prefix}. ${title}`, "", `- 发布：${result.publishedLocal || "未知"}`, `- 时长：${result.durationSeconds} 秒`, `- 来源：${publicUrl}`, `- 字幕：画面内嵌字幕逐帧核对（非平台字幕轨）`, "", plainText, "");
      manifest.push(result);
      process.stdout.write(`[${prefix}/${items.length}] OK-FRAME ${title}\n`);
      fs.writeFileSync(path.join(detailDir, `${prefix}_${item.id}.json`), `${JSON.stringify(result, null, 2)}\n`, "utf8");
      continue;
    }
    if (!selectedTrack && Object.keys(note.video || {}).length === 0 && note.desc?.trim()) {
      const imageTextPath = path.join(baseDir, "note_image_text", `${prefix}_${item.id}.txt`);
      const hasImageText = fs.existsSync(imageTextPath);
      const plainText = hasImageText ? fs.readFileSync(imageTextPath, "utf8").trim() : note.desc.replace(/\s+/g, " ").trim();
      const transcriptFile = `${prefix}_${item.id}.txt`;
      fs.writeFileSync(path.join(transcriptDir, transcriptFile), `${title}\n${publicUrl}\n\n${plainText}\n`, "utf8");
      Object.assign(result, {status: "ok", title, description: note.desc, publishedLocal: localTime(note.time), publishedEpochMs: note.time || null, durationSeconds: 0, selectedTrack: "note-text", sourceType: hasImageText ? "图片文字人工核对（重复分页合并）" : "图文笔记正文", transcriptFile: path.relative(baseDir, path.join(transcriptDir, transcriptFile)), transcriptCharacters: plainText.length, downloadedTracks, images: (note.imageList || []).map((image) => ({width: image.width, height: image.height, url: image.urlDefault || image.urlPre || image.url || image.infoList?.[0]?.url}))});
      combined.push(`## ${prefix}. ${title}`, "", `- 发布：${result.publishedLocal || "未知"}`, `- 类型：${result.sourceType}（非视频字幕）`, `- 来源：${publicUrl}`, "", plainText, "");
      manifest.push(result);
      process.stdout.write(`[${prefix}/${items.length}] OK-TEXT ${title}\n`);
      fs.writeFileSync(path.join(detailDir, `${prefix}_${item.id}.json`), `${JSON.stringify(result, null, 2)}\n`, "utf8");
      continue;
    }
    if (!selectedTrack) throw new Error("chinese_subtitle_missing");
    const selectedFile = downloadedTracks.find((track) => track.group === selectedGroup)?.filename;
    const plainText = srtToPlain(fs.readFileSync(path.join(rawDir, selectedFile), "utf8"));
    const transcriptFile = `${prefix}_${item.id}.txt`;
    fs.writeFileSync(path.join(transcriptDir, transcriptFile), `${title}\n${publicUrl}\n\n${plainText}\n`, "utf8");
    const streams = mediaV2.stream || note.video?.media?.stream || {};
    const stream = streams.h264?.[0] || streams.h265?.[0] || null;
    Object.assign(result, {status: "ok", title, description: note.desc || "", publishedLocal: localTime(note.time), publishedEpochMs: note.time || null, durationSeconds: note.video?.capa?.duration || mediaV2.video?.duration || null, selectedTrack: selectedGroup, transcriptFile: path.relative(baseDir, path.join(transcriptDir, transcriptFile)), transcriptCharacters: plainText.length, downloadedTracks, video: stream ? {format: stream.format, codec: stream.video_codec, width: stream.width, height: stream.height, durationMs: stream.duration, sizeBytes: stream.size, url: stream.master_url} : null});
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
fs.writeFileSync(path.join(baseDir, "fetch_results.jsonl"), `${manifest.map(JSON.stringify).join("\n")}\n`, "utf8");
const platformSrtCount = manifest.reduce((sum, row) => sum + (row.downloadedTracks || []).filter((track) => track.group !== "local-frame").length, 0);
const localFrameCount = manifest.reduce((sum, row) => sum + (row.downloadedTracks || []).filter((track) => track.group === "local-frame").length, 0);
fs.writeFileSync(path.join(baseDir, "fetch_report.md"), `# 抓取报告\n\n- 账号：上海老太太\n- 小红书号：5444795125\n- 主页可见笔记：${items.length} 条（视频 ${manifest.filter((row) => row.selectedTrack !== "note-text").length}，图文 ${manifest.filter((row) => row.selectedTrack === "note-text").length}）\n- 成功：${manifest.length - failures.length} 条\n- 失败：${failures.length} 条\n- 平台原始 SRT：${platformSrtCount} 个\n- 画面字幕人工核对 SRT：${localFrameCount} 个\n- 抓取时间：${new Date().toISOString()}\n\n${failures.length ? `## 失败项目\n\n${failures.map((row) => `- ${row.index}. ${row.noteId}: ${row.error}`).join("\n")}\n` : "全部可见笔记均已取得可读中文正文。\n"}`, "utf8");
console.log(`Done: ${manifest.length - failures.length}/${items.length} successful`);
