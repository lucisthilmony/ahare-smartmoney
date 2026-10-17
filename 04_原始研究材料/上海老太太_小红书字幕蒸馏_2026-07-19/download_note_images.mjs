import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const baseDir = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.join(baseDir, "note_images");
fs.mkdirSync(outputDir, {recursive: true});
const results = fs.readFileSync(path.join(baseDir, "fetch_results.jsonl"), "utf8").trim().split(/\r?\n/).map(JSON.parse);
for (const row of results.filter((item) => item.selectedTrack === "note-text")) {
  for (let i = 0; i < (row.images || []).length; i += 1) {
    const image = row.images[i];
    if (!image.url) continue;
    const response = await fetch(image.url, {headers: {"user-agent": "Mozilla/5.0", referer: row.publicUrl}});
    if (!response.ok) throw new Error(`${row.noteId} image ${i + 1}: HTTP ${response.status}`);
    const filename = `${String(row.index).padStart(3, "0")}_${row.noteId}_${String(i + 1).padStart(2, "0")}.jpg`;
    fs.writeFileSync(path.join(outputDir, filename), Buffer.from(await response.arrayBuffer()));
    process.stdout.write(`${filename}\n`);
  }
}
