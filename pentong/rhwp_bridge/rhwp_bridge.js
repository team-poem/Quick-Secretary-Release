// rhwp_bridge.js — Python ↔ @rhwp/core glue
//
// 사용법:
//   node rhwp_bridge.js <operation> <filepath> [json_args]
//
// 결과는 stdout 에 JSON 으로 출력 (항상 {ok, data?, error?} 형태).
// 에러는 rc != 0 + JSON error 형태.

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ESM 으로 @rhwp/core 로드. wasm 파일 경로를 명시.
const coreModule = await import('@rhwp/core');
const { HwpDocument } = coreModule;

// Node 환경에서는 init() 를 Uint8Array 로 호출하거나 default-init 에 맡김.
// 최신 @rhwp/core 0.7.3 는 ESM import 시 WASM 자동 초기화 지원.
if (typeof coreModule.default === 'function') {
  const wasmPath = join(__dirname, 'node_modules', '@rhwp', 'core', 'rhwp_bg.wasm');
  const wasmBytes = readFileSync(wasmPath);
  await coreModule.default({ module_or_path: wasmBytes });
}

// WASM renderer 가 브라우저 API(measureTextWidth) 를 전역으로 기대할 수 있음.
// 텍스트 추출 단계에선 호출 안 되지만 방어적으로 noop 주입.
if (typeof globalThis.measureTextWidth !== 'function') {
  globalThis.measureTextWidth = (_font, text) => (text || '').length * 7;
}

function loadDoc(filepath) {
  const bytes = readFileSync(filepath);
  return new HwpDocument(new Uint8Array(bytes));
}

// ── 공통 헬퍼 ──────────────────────────────────────────────

// 문서 전체를 (sec, para, text) 튜플 목록으로 풀어냄
function collectParagraphs(doc) {
  const sections = doc.getSectionCount();
  const items = [];
  for (let s = 0; s < sections; s++) {
    const pc = doc.getParagraphCount(s);
    for (let p = 0; p < pc; p++) {
      const len = doc.getParagraphLength(s, p);
      let text = '';
      if (len > 0) {
        try { text = doc.getTextRange(s, p, 0, len); } catch { text = ''; }
      }
      items.push({ section: s, paragraph: p, length: len, text });
    }
  }
  return items;
}

function saveDocument(doc, savePath) {
  // 확장자에 따라 exportHwp / exportHwpx 선택. HWP 저장이 미완(#197) 이라
  // HWPX 가 권장.
  const ext = (savePath.match(/\.(hwp|hwpx)$/i) || [])[1]?.toLowerCase();
  let bytes;
  try {
    if (ext === 'hwpx') {
      bytes = doc.exportHwpx();
    } else {
      bytes = doc.exportHwp();
    }
  } catch (e) {
    // HWP export 실패 시 HWPX 로 폴백 + 경로 확장자 교체
    const altPath = savePath.replace(/\.hwp$/i, '.hwpx');
    bytes = doc.exportHwpx();
    writeFileSync(altPath, Buffer.from(bytes));
    return { saved_to: altPath, fallback: 'hwpx', reason: String(e?.message || e) };
  }
  writeFileSync(savePath, Buffer.from(bytes));
  return { saved_to: savePath };
}

const operations = {
  read_full_text(filepath, _args) {
    const doc = loadDoc(filepath);
    const sections = doc.getSectionCount();
    const parts = [];
    for (let s = 0; s < sections; s++) {
      const paraCount = doc.getParagraphCount(s);
      for (let p = 0; p < paraCount; p++) {
        const len = doc.getParagraphLength(s, p);
        if (len > 0) {
          try {
            parts.push(doc.getTextRange(s, p, 0, len));
          } catch (e) {
            parts.push('');
          }
        } else {
          parts.push('');
        }
      }
    }
    doc.free();
    return parts.join('\n');
  },

  read_all_paragraphs(filepath, _args) {
    const doc = loadDoc(filepath);
    const sections = doc.getSectionCount();
    const rows = [];
    for (let s = 0; s < sections; s++) {
      const paraCount = doc.getParagraphCount(s);
      for (let p = 0; p < paraCount; p++) {
        const len = doc.getParagraphLength(s, p);
        let text = '';
        if (len > 0) {
          try { text = doc.getTextRange(s, p, 0, len); } catch { text = ''; }
        }
        rows.push({ section: s, paragraph: p, text });
      }
    }
    doc.free();
    return rows;
  },

  get_document_info(filepath, _args) {
    const doc = loadDoc(filepath);
    const sections = doc.getSectionCount();
    const perSectionCounts = [];
    let totalParagraphs = 0;
    for (let s = 0; s < sections; s++) {
      const pc = doc.getParagraphCount(s);
      perSectionCounts.push(pc);
      totalParagraphs += pc;
    }
    let pageCount = null;
    try { pageCount = doc.pageCount(); } catch {}
    doc.free();
    return {
      sections,
      paragraphs_per_section: perSectionCounts,
      total_paragraphs: totalParagraphs,
      page_count: pageCount,
    };
  },

  find_text(filepath, args) {
    // args: { pattern: string, ignore_case?: bool }
    const pattern = String(args?.pattern || '');
    const flags = args?.ignore_case ? 'gi' : 'g';
    const re = new RegExp(pattern, flags);
    const doc = loadDoc(filepath);
    const matches = [];
    const items = collectParagraphs(doc);
    for (const it of items) {
      let m;
      while ((m = re.exec(it.text)) !== null) {
        matches.push({
          section: it.section,
          paragraph: it.paragraph,
          char_offset: m.index,
          length: m[0].length,
          matched_text: m[0],
          para_text: it.text,
        });
        if (m.index === re.lastIndex) re.lastIndex++;
      }
    }
    doc.free();
    return matches;
  },

  find_and_replace(filepath, args) {
    // args: { find: string, replace: string, save_path: string, ignore_case?: bool }
    const find = String(args?.find || '');
    const replace = String(args?.replace || '');
    const savePath = String(args?.save_path || '');
    if (!savePath) throw new Error('save_path 필수');
    if (!find) throw new Error('find 문자열 필수');

    const doc = loadDoc(filepath);
    let replacedCount = 0;
    const sections = doc.getSectionCount();
    // 각 문단을 순회하며 발견된 지점들을 "뒤에서부터" 치환 (offset 밀림 방지).
    for (let s = 0; s < sections; s++) {
      const pc = doc.getParagraphCount(s);
      for (let p = 0; p < pc; p++) {
        const len = doc.getParagraphLength(s, p);
        if (len === 0) continue;
        let text;
        try { text = doc.getTextRange(s, p, 0, len); } catch { continue; }
        if (!text || !text.includes(find)) continue;
        // 뒤에서부터 치환
        const positions = [];
        let startIdx = 0;
        while (true) {
          const idx = text.indexOf(find, startIdx);
          if (idx < 0) break;
          positions.push(idx);
          startIdx = idx + find.length;
        }
        for (let i = positions.length - 1; i >= 0; i--) {
          try {
            doc.replaceText(s, p, positions[i], find.length, replace);
            replacedCount++;
          } catch (e) {
            // 특정 위치 치환 실패는 전체 실패로 번지지 않게 계속
          }
        }
      }
    }
    const saveResult = saveDocument(doc, savePath);
    doc.free();
    return { replaced_count: replacedCount, ...saveResult };
  },

  batch_replace(filepath, args) {
    // args: { pairs: [[find, replace], ...], save_path: string }
    const pairs = args?.pairs || [];
    const savePath = String(args?.save_path || '');
    if (!savePath) throw new Error('save_path 필수');

    const doc = loadDoc(filepath);
    let totalReplaced = 0;
    const perPair = [];
    for (const [find, replace] of pairs) {
      let count = 0;
      const sections = doc.getSectionCount();
      for (let s = 0; s < sections; s++) {
        const pc = doc.getParagraphCount(s);
        for (let p = 0; p < pc; p++) {
          const len = doc.getParagraphLength(s, p);
          if (len === 0) continue;
          let text;
          try { text = doc.getTextRange(s, p, 0, len); } catch { continue; }
          if (!text || !text.includes(find)) continue;
          const positions = [];
          let startIdx = 0;
          while (true) {
            const idx = text.indexOf(find, startIdx);
            if (idx < 0) break;
            positions.push(idx);
            startIdx = idx + find.length;
          }
          for (let i = positions.length - 1; i >= 0; i--) {
            try {
              doc.replaceText(s, p, positions[i], find.length, replace);
              count++;
            } catch {}
          }
        }
      }
      perPair.push({ find, replace, count });
      totalReplaced += count;
    }
    const saveResult = saveDocument(doc, savePath);
    doc.free();
    return { total_replaced: totalReplaced, per_pair: perPair, ...saveResult };
  },

  insert_text_at_end(filepath, args) {
    // args: { text: string, save_path: string }
    const text = String(args?.text || '');
    const savePath = String(args?.save_path || '');
    if (!savePath) throw new Error('save_path 필수');
    const doc = loadDoc(filepath);
    const sections = doc.getSectionCount();
    const lastSec = sections - 1;
    const pc = doc.getParagraphCount(lastSec);
    const lastPara = pc - 1;
    const lastLen = doc.getParagraphLength(lastSec, lastPara);
    doc.insertText(lastSec, lastPara, lastLen, text);
    const saveResult = saveDocument(doc, savePath);
    doc.free();
    return { inserted_at: { section: lastSec, paragraph: lastPara, offset: lastLen }, ...saveResult };
  },

  insert_text_at_beginning(filepath, args) {
    // args: { text: string, save_path: string }
    const text = String(args?.text || '');
    const savePath = String(args?.save_path || '');
    if (!savePath) throw new Error('save_path 필수');
    const doc = loadDoc(filepath);
    doc.insertText(0, 0, 0, text);
    const saveResult = saveDocument(doc, savePath);
    doc.free();
    return { inserted_at: { section: 0, paragraph: 0, offset: 0 }, ...saveResult };
  },

  list_tables(filepath, _args) {
    // 모든 표의 위치/크기 목록. Claude 가 표 어디에 있는지 빠르게 파악.
    const doc = loadDoc(filepath);
    const tables = [];
    const sections = doc.getSectionCount();
    for (let s = 0; s < sections; s++) {
      const pc = doc.getParagraphCount(s);
      for (let p = 0; p < pc; p++) {
        let posRaw;
        try { posRaw = doc.getControlTextPositions(s, p); } catch { continue; }
        if (!posRaw) continue;
        let positions;
        try { positions = JSON.parse(posRaw); } catch { continue; }
        if (!Array.isArray(positions) || positions.length === 0) continue;
        for (let ctrl = 0; ctrl < positions.length; ctrl++) {
          let dimRaw;
          try { dimRaw = doc.getTableDimensions(s, p, ctrl); } catch { continue; }
          if (!dimRaw) continue;
          let dim;
          try { dim = JSON.parse(dimRaw); } catch { continue; }
          if (!dim.rowCount) continue;
          tables.push({
            index: tables.length,
            section: s,
            paragraph: p,
            control: ctrl,
            rows: dim.rowCount,
            cols: dim.colCount,
            cells: dim.cellCount,
          });
        }
      }
    }
    doc.free();
    return tables;
  },

  extract_table(filepath, args) {
    // 특정 표 1개를 2D 리스트로. args: { section, paragraph, control }
    // 또는 args: { index } — list_tables 의 index 로 지정
    const doc = loadDoc(filepath);
    let sec = args?.section;
    let para = args?.paragraph;
    let ctrl = args?.control;
    if (sec === undefined || para === undefined || ctrl === undefined) {
      const idx = args?.index ?? 0;
      // list_tables 와 동일한 순회로 index 찾기
      const sections = doc.getSectionCount();
      let found = null;
      let counter = 0;
      outer:
      for (let s = 0; s < sections; s++) {
        const pc = doc.getParagraphCount(s);
        for (let p = 0; p < pc; p++) {
          let posRaw;
          try { posRaw = doc.getControlTextPositions(s, p); } catch { continue; }
          if (!posRaw) continue;
          let positions;
          try { positions = JSON.parse(posRaw); } catch { continue; }
          if (!Array.isArray(positions) || positions.length === 0) continue;
          for (let c = 0; c < positions.length; c++) {
            let dimRaw;
            try { dimRaw = doc.getTableDimensions(s, p, c); } catch { continue; }
            if (!dimRaw) continue;
            let dim;
            try { dim = JSON.parse(dimRaw); } catch { continue; }
            if (!dim.rowCount) continue;
            if (counter === idx) {
              found = { s, p, c, dim };
              break outer;
            }
            counter++;
          }
        }
      }
      if (!found) {
        doc.free();
        throw new Error(`표 index ${idx} 를 찾을 수 없습니다.`);
      }
      sec = found.s;
      para = found.p;
      ctrl = found.c;
    }

    let dimRaw;
    try { dimRaw = doc.getTableDimensions(sec, para, ctrl); }
    catch (e) { doc.free(); throw new Error(`표가 아님: sec=${sec} para=${para} ctrl=${ctrl}`); }
    const dim = JSON.parse(dimRaw);
    const rows = dim.rowCount;
    const cols = dim.colCount;
    const cellCount = dim.cellCount;

    // 2D 배열 초기화 (빈 문자열로)
    const grid = Array.from({ length: rows }, () => Array(cols).fill(""));
    const cellList = [];
    for (let cellIdx = 0; cellIdx < cellCount; cellIdx++) {
      let infoRaw;
      try { infoRaw = doc.getCellInfo(sec, para, ctrl, cellIdx); } catch { continue; }
      if (!infoRaw) continue;
      const info = JSON.parse(infoRaw);
      const cpc = doc.getCellParagraphCount(sec, para, ctrl, cellIdx);
      let text = "";
      for (let cp = 0; cp < cpc; cp++) {
        const len = doc.getCellParagraphLength(sec, para, ctrl, cellIdx, cp);
        if (len > 0) {
          try { text += doc.getTextInCell(sec, para, ctrl, cellIdx, cp, 0, len); } catch {}
        }
        if (cp < cpc - 1) text += "\n";
      }
      const cell = {
        row: info.row,
        col: info.col,
        rowSpan: info.rowSpan,
        colSpan: info.colSpan,
        text: text,
      };
      cellList.push(cell);
      // grid 에는 병합된 영역 전체에 같은 텍스트 (첫 셀에만 넣는 방식도 가능)
      if (info.row < rows && info.col < cols) {
        grid[info.row][info.col] = text;
      }
    }
    doc.free();
    return {
      section: sec,
      paragraph: para,
      control: ctrl,
      rows,
      cols,
      data: grid,
      cells: cellList,
    };
  },

  read_tables(filepath, _args) {
    // 모든 표의 내용을 한 번에 반환. 큰 파일에선 느릴 수 있음.
    const doc = loadDoc(filepath);
    const tablesOut = [];
    const sections = doc.getSectionCount();
    for (let s = 0; s < sections; s++) {
      const pc = doc.getParagraphCount(s);
      for (let p = 0; p < pc; p++) {
        let posRaw;
        try { posRaw = doc.getControlTextPositions(s, p); } catch { continue; }
        if (!posRaw) continue;
        let positions;
        try { positions = JSON.parse(posRaw); } catch { continue; }
        if (!Array.isArray(positions) || positions.length === 0) continue;
        for (let ctrl = 0; ctrl < positions.length; ctrl++) {
          let dimRaw;
          try { dimRaw = doc.getTableDimensions(s, p, ctrl); } catch { continue; }
          if (!dimRaw) continue;
          let dim;
          try { dim = JSON.parse(dimRaw); } catch { continue; }
          if (!dim.rowCount) continue;
          const rows = dim.rowCount;
          const cols = dim.colCount;
          const grid = Array.from({ length: rows }, () => Array(cols).fill(""));
          for (let cellIdx = 0; cellIdx < dim.cellCount; cellIdx++) {
            let infoRaw;
            try { infoRaw = doc.getCellInfo(s, p, ctrl, cellIdx); } catch { continue; }
            if (!infoRaw) continue;
            const info = JSON.parse(infoRaw);
            const cpc = doc.getCellParagraphCount(s, p, ctrl, cellIdx);
            let text = "";
            for (let cp = 0; cp < cpc; cp++) {
              const len = doc.getCellParagraphLength(s, p, ctrl, cellIdx, cp);
              if (len > 0) {
                try { text += doc.getTextInCell(s, p, ctrl, cellIdx, cp, 0, len); } catch {}
              }
              if (cp < cpc - 1) text += "\n";
            }
            if (info.row < rows && info.col < cols) {
              grid[info.row][info.col] = text;
            }
          }
          tablesOut.push({
            index: tablesOut.length,
            section: s,
            paragraph: p,
            control: ctrl,
            rows,
            cols,
            data: grid,
          });
        }
      }
    }
    doc.free();
    return tablesOut;
  },

  insert_paragraphs(filepath, args) {
    // args: { paragraphs: [string, ...], position: "end"|"beginning", save_path: string }
    const paragraphs = args?.paragraphs || [];
    const position = String(args?.position || 'end');
    const savePath = String(args?.save_path || '');
    if (!savePath) throw new Error('save_path 필수');
    // 여러 문단을 줄바꿈으로 연결해서 한 번에 삽입. rhwp 가 \n 을 문단 분리로
    // 해석하지 않을 수도 있어서 "문단 분리 컨트롤 문자" 대신 그냥 \n 사용.
    const joined = paragraphs.join('\n');
    const doc = loadDoc(filepath);
    if (position === 'beginning') {
      doc.insertText(0, 0, 0, joined);
    } else {
      const sections = doc.getSectionCount();
      const lastSec = sections - 1;
      const pc = doc.getParagraphCount(lastSec);
      const lastPara = pc - 1;
      const lastLen = doc.getParagraphLength(lastSec, lastPara);
      doc.insertText(lastSec, lastPara, lastLen, joined);
    }
    const saveResult = saveDocument(doc, savePath);
    doc.free();
    return { count: paragraphs.length, position, ...saveResult };
  },
};

async function main() {
  const [, , operation, filepath, argsJson] = process.argv;
  if (!operation || !filepath) {
    console.log(JSON.stringify({
      ok: false,
      error: 'Usage: node rhwp_bridge.js <operation> <filepath> [json_args]',
      available_operations: Object.keys(operations),
    }));
    process.exit(2);
  }
  const args = argsJson ? JSON.parse(argsJson) : {};
  if (!(operation in operations)) {
    console.log(JSON.stringify({
      ok: false,
      error: `Unknown operation: ${operation}`,
      available_operations: Object.keys(operations),
    }));
    process.exit(2);
  }
  try {
    const data = operations[operation](filepath, args);
    console.log(JSON.stringify({ ok: true, data }));
  } catch (e) {
    console.log(JSON.stringify({
      ok: false,
      error: String(e?.message || e),
      stack: e?.stack,
    }));
    process.exit(1);
  }
}

main().catch(e => {
  console.error(JSON.stringify({ ok: false, error: String(e?.message || e) }));
  process.exit(1);
});
