import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseDir = path.dirname(fileURLToPath(import.meta.url));
const mediaDir = path.join(baseDir, "fallback_media");
fs.mkdirSync(mediaDir, { recursive: true });
const items = fs.readFileSync(path.join(baseDir, ".source_links_with_ephemeral_tokens.jsonl"), "utf8").trim().split(/\r?\n/).map(JSON.parse);
const results = fs.readFileSync(path.join(baseDir, "fetch_results.jsonl"), "utf8").trim().split(/\r?\n/).map(JSON.parse);
const missingIds = new Set(results.filter((row) => row.status !== "ok").map((row) => row.noteId));
const userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36";

function parseInitialState(html) {
  const match = html.match(/<script[^>]*>window\.__INITIAL_STATE__=([\s\S]*?)<\/script>/);
  if (!match) throw new Error("initial_state_missing");
  return JSON.parse(match[1].replace(/\bundefined\b/g, "null"));
}

for (const item of items.filter((row) => missingIds.has(row.id))) {
  const prefix = String(item.index).padStart(3, "0");
  const publicUrl = `https://www.xiaohongshu.com/explore/${item.id}`;
  const fetchUrl = `${publicUrl}?xsec_token=${encodeURIComponent(item.xsecToken)}&xsec_source=pc_user`;
  const page = await fetch(fetchUrl, {headers: {"user-agent": userAgent, referer: "https://www.xiaohongshu.com/"}});
  if (!page.ok) throw new Error(`${item.id}: page_http_${page.status}`);
  const state = parseInitialState(await page.text());
  const map = state.note?.noteDetailMap || {};
  const note = (map[item.id] || map[Object.keys(map)[0]])?.note;
  if (!note) throw new Error(`${item.id}: note_missing`);
  const mediaV2 = typeof note.video?.mediaV2 === "string" ? JSON.parse(note.video.mediaV2) : (note.video?.mediaV2 || {});
  const streams = mediaV2.stream || note.video?.media?.stream || {};
  const candidates = [...(streams.h264 || []), ...(streams.h265 || []), ...(streams.av1 || [])].filter((stream) => stream.master_url || stream.backup_urls?.[0]);
  const stream = candidates.sort((a, b) => (b.width || 0) * (b.height || 0) - (a.width || 0) * (a.height || 0))[0];
  if (!stream) {
    const shape = {
      noteType: note.type,
      noteVideoKeys: Object.keys(note.video || {}),
      mediaV2Keys: Object.keys(mediaV2 || {}),
      mediaV2VideoKeys: Object.keys(mediaV2.video || {}),
      mediaV2StreamKeys: Object.keys(mediaV2.stream || {}),
      noteMediaKeys: Object.keys(note.video?.media || {}),
      noteMediaStreamKeys: Object.keys(note.video?.media?.stream || {}),
      consumerKeys: Object.keys(note.video?.consumer || {}),
      originVideoKey: note.video?.originVideoKey || note.video?.origin_video_key || null,
    };
    console.error(`${item.id}: video_stream_missing ${JSON.stringify(shape)}`);
    continue;
  }
  const videoResponse = await fetch(stream.master_url || stream.backup_urls[0], {headers: {"user-agent": userAgent, referer: publicUrl}});
  if (!videoResponse.ok) throw new Error(`${item.id}: video_http_${videoResponse.status}`);
  const file = `${prefix}_${item.id}.mp4`;
  if (!fs.existsSync(path.join(mediaDir, file))) fs.writeFileSync(path.join(mediaDir, file), Buffer.from(await videoResponse.arrayBuffer()));
  process.stdout.write(`${file}\t${note.video?.capa?.duration || mediaV2.video?.duration || ""}\n`);
}
