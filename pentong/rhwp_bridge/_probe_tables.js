// 표 추출 API POC — 실제 HWP 에서 어떤 데이터가 나오는지 확인
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const coreModule = await import('@rhwp/core');
const { HwpDocument } = coreModule;
const wasmPath = join(__dirname, 'node_modules', '@rhwp', 'core', 'rhwp_bg.wasm');
await coreModule.default({ module_or_path: readFileSync(wasmPath) });

globalThis.measureTextWidth = (_f, t) => (t || '').length * 7;

const filepath = process.argv[2];
const bytes = readFileSync(filepath);
const doc = new HwpDocument(new Uint8Array(bytes));

console.log(`=== 파일: ${filepath} ===`);
console.log(`섹션 수: ${doc.getSectionCount()}`);

const tables = [];
for (let s = 0; s < doc.getSectionCount(); s++) {
  const pc = doc.getParagraphCount(s);
  for (let p = 0; p < pc; p++) {
    let posRaw;
    try {
      posRaw = doc.getControlTextPositions(s, p);
    } catch {
      continue;
    }
    if (!posRaw || posRaw === '[]' || posRaw === '') continue;
    let positions;
    try {
      positions = JSON.parse(posRaw);
    } catch {
      continue;
    }
    if (!Array.isArray(positions) || positions.length === 0) continue;

    for (let ctrl = 0; ctrl < positions.length; ctrl++) {
      let dimRaw;
      try {
        dimRaw = doc.getTableDimensions(s, p, ctrl);
      } catch {
        continue;  // 표 아님
      }
      if (!dimRaw) continue;
      let dim;
      try { dim = JSON.parse(dimRaw); } catch { continue; }
      if (!dim.rowCount) continue;

      tables.push({ section: s, paragraph: p, control: ctrl, rows: dim.rowCount, cols: dim.colCount, cells: dim.cellCount });
    }
  }
}

console.log(`\n발견된 표 ${tables.length}개:`);
for (const t of tables.slice(0, 10)) {
  console.log(`  sec=${t.section} para=${t.paragraph} ctrl=${t.control} ${t.rows}x${t.cols} (${t.cells} cells)`);
}

// 첫 표의 내용 상세 덤프
if (tables.length > 0) {
  const t = tables[0];
  console.log(`\n첫 표 내용:`);
  for (let cellIdx = 0; cellIdx < Math.min(t.cells, 20); cellIdx++) {
    let cellInfoRaw;
    try { cellInfoRaw = doc.getCellInfo(t.section, t.paragraph, t.control, cellIdx); } catch { continue; }
    const info = JSON.parse(cellInfoRaw);
    const cpc = doc.getCellParagraphCount(t.section, t.paragraph, t.control, cellIdx);
    let cellText = '';
    for (let cp = 0; cp < cpc; cp++) {
      const len = doc.getCellParagraphLength(t.section, t.paragraph, t.control, cellIdx, cp);
      if (len > 0) {
        try {
          cellText += doc.getTextInCell(t.section, t.paragraph, t.control, cellIdx, cp, 0, len);
        } catch {}
      }
      cellText += '\n';
    }
    console.log(`  cell ${cellIdx} [r${info.row},c${info.col} span(${info.rowSpan}x${info.colSpan})]: ${JSON.stringify(cellText.trim().slice(0, 60))}`);
  }
}

doc.free();
