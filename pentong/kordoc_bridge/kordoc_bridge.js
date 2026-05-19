// kordoc_bridge.js — Python ↔ kordoc glue (뚝딱비서 v0.0.25+)
//
// HWP/HWPX 작성·병합·양식채우기·신구대조표를 kordoc 으로 처리.
// (read 는 v0.0.25 시점에는 rhwp_bridge 가 처리, v0.0.26+ 에서 kordoc 으로 통합 예정.)
//
// 사용법:
//   node kordoc_bridge.js <op> [args...]
//
// 응답: stdout 마지막 줄이 JSON. 진행 메시지는 stderr.
//   성공: {"ok": true, "data": {...}}
//   실패: {"ok": false, "error": "...", "code": "..."}

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const args = process.argv.slice(2);
const op = args[0] || '';

function emit(payload) {
  process.stdout.write(JSON.stringify(payload) + '\n');
}

function ok(data) {
  emit({ ok: true, data });
  process.exit(0);
}

function fail(error, code = 'UNKNOWN', extra = {}) {
  emit({ ok: false, error: String(error?.message ?? error), code, ...extra });
  process.exit(1);
}

let kordoc;
try {
  kordoc = await import('kordoc');
} catch (e) {
  fail(e, 'IMPORT_FAILED');
}

const {
  parse,
  markdownToHwpx,
  fillForm,
  fillHwpx,
  compare,
  detectFormat,
  extractFormFields,
  blocksToMarkdown,
} = kordoc;

// ── 작업 폴더 경계 검증 (호스트가 cwd 로 작업 폴더 지정) ──────────
function assertInsideCwd(p) {
  const abs = resolve(p);
  const cwd = resolve(process.cwd());
  // Windows 경로 비교는 case-insensitive 안전성 위해 lower
  if (!abs.toLowerCase().startsWith(cwd.toLowerCase())) {
    throw new Error(`작업 폴더 외부 경로 거부: ${abs}`);
  }
  return abs;
}

// ── 동작 라우팅 ──────────────────────────────────────────
const ops = {
  // parse_document <filepath> [--pages 1-3]
  async parse_document() {
    const filepath = args[1];
    if (!filepath) fail('filepath required', 'BAD_ARGS');
    const abs = assertInsideCwd(filepath);
    const buffer = readFileSync(abs);
    const result = await parse(buffer.buffer);
    if (!result.success) {
      fail(result.error || 'parse failed', result.code || 'PARSE_FAILED');
    }
    ok({
      markdown: result.markdown,
      metadata: result.metadata,
      block_count: (result.blocks || []).length,
      // 토큰 경제를 위해 blocks 는 요약만
      block_summary: (result.blocks || []).slice(0, 3),
    });
  },

  // markdown_to_hwpx <md_path_or_inline> <output_path>
  // - md_path 가 .md 로 끝나면 파일 읽기, 아니면 inline 마크다운 문자열
  async markdown_to_hwpx() {
    const mdInput = args[1];
    const outputPath = args[2];
    if (!mdInput || !outputPath) fail('args: <md_path|inline> <output>', 'BAD_ARGS');

    let markdown;
    if (mdInput.endsWith('.md') || mdInput.endsWith('.markdown')) {
      const abs = assertInsideCwd(mdInput);
      markdown = readFileSync(abs, 'utf-8');
    } else {
      markdown = mdInput;
    }

    const outAbs = assertInsideCwd(outputPath);
    const hwpxBuffer = await markdownToHwpx(markdown);
    writeFileSync(outAbs, Buffer.from(hwpxBuffer));
    ok({ output_path: outAbs, byte_size: hwpxBuffer.byteLength || hwpxBuffer.length });
  },

  // hwp_merge_via_md <inputs_json_array> <output_path> [--headings json_array]
  // 각 입력 파일을 parse → 마크다운 → 헤더로 구분해 합성 → markdownToHwpx
  async hwp_merge_via_md() {
    const inputsJson = args[1];
    const outputPath = args[2];
    const headingsJson = args[3]; // optional

    if (!inputsJson || !outputPath) fail('args: <inputs_json> <output> [headings_json]', 'BAD_ARGS');

    let inputs, headings;
    try {
      inputs = JSON.parse(inputsJson);
    } catch (e) {
      fail('inputs must be JSON array', 'BAD_ARGS');
    }
    if (!Array.isArray(inputs) || inputs.length === 0) {
      fail('inputs must be non-empty array', 'BAD_ARGS');
    }
    if (headingsJson) {
      try {
        headings = JSON.parse(headingsJson);
      } catch {
        headings = null;
      }
    }

    const parts = [];
    for (let i = 0; i < inputs.length; i++) {
      const fp = assertInsideCwd(inputs[i]);
      const buf = readFileSync(fp);
      const r = await parse(buf.buffer);
      if (!r.success) {
        fail(`parse failed for ${inputs[i]}: ${r.error}`, r.code || 'PARSE_FAILED', { input: inputs[i] });
      }
      const heading = (headings && headings[i]) || `섹션 ${i + 1}`;
      parts.push(`## ${heading}\n\n${r.markdown}\n`);
    }

    const combined = `# 취합본\n\n${parts.join('\n\n---\n\n')}`;
    const outAbs = assertInsideCwd(outputPath);
    const hwpxBuffer = await markdownToHwpx(combined);
    writeFileSync(outAbs, Buffer.from(hwpxBuffer));
    ok({
      output_path: outAbs,
      byte_size: hwpxBuffer.byteLength || hwpxBuffer.length,
      merged_count: inputs.length,
      combined_md_length: combined.length,
    });
  },

  // fill_form <template_path> <values_json> <output_path> [--mode hwpx-preserve|markdown|hwpx]
  async fill_form() {
    const templatePath = args[1];
    const valuesJson = args[2];
    const outputPath = args[3];
    const mode = args[4] || 'hwpx-preserve';

    if (!templatePath || !valuesJson || !outputPath) {
      fail('args: <template> <values_json> <output> [mode]', 'BAD_ARGS');
    }
    let values;
    try {
      values = JSON.parse(valuesJson);
    } catch {
      fail('values must be JSON object', 'BAD_ARGS');
    }

    const tplAbs = assertInsideCwd(templatePath);
    const outAbs = assertInsideCwd(outputPath);
    const tplBuf = readFileSync(tplAbs);
    const result = await fillForm(tplBuf.buffer, values, { format: mode });
    if (!result.success) {
      fail(result.error || 'fillForm failed', result.code || 'FILL_FAILED');
    }
    if (result.buffer) {
      writeFileSync(outAbs, Buffer.from(result.buffer));
    }
    ok({
      output_path: outAbs,
      filled: result.filled || [],
      unmatched: result.unmatched || [],
    });
  },

  // compare_documents <pathA> <pathB>
  async compare_documents() {
    const a = args[1];
    const b = args[2];
    if (!a || !b) fail('args: <pathA> <pathB>', 'BAD_ARGS');
    const aAbs = assertInsideCwd(a);
    const bAbs = assertInsideCwd(b);
    const aBuf = readFileSync(aAbs);
    const bBuf = readFileSync(bAbs);
    const diff = await compare(aBuf.buffer, bBuf.buffer);
    ok({
      stats: diff.stats,
      diffs_preview: (diff.diffs || []).slice(0, 20),
      total_diff_count: (diff.diffs || []).length,
    });
  },

  // detect_format <filepath>
  async detect_format() {
    const filepath = args[1];
    if (!filepath) fail('filepath required', 'BAD_ARGS');
    const abs = assertInsideCwd(filepath);
    const buf = readFileSync(abs);
    const fmt = detectFormat(buf.buffer);
    ok({ format: fmt });
  },

  // self_test — 환경 sanity (kordoc 버전 + 작은 markdownToHwpx)
  async self_test() {
    const md = '# 테스트\n\n안녕하세요.\n\n| 항목 | 값 |\n| --- | --- |\n| 하나 | 1 |\n';
    const buf = await markdownToHwpx(md);
    ok({
      kordoc_loaded: true,
      sample_hwpx_size: buf.byteLength || buf.length,
    });
  },

  async help() {
    ok({
      ops: [
        'parse_document <filepath>',
        'markdown_to_hwpx <md_path|inline> <output_path>',
        'hwp_merge_via_md <inputs_json> <output_path> [headings_json]',
        'fill_form <template> <values_json> <output> [mode]',
        'compare_documents <pathA> <pathB>',
        'detect_format <filepath>',
        'self_test',
      ],
    });
  },
};

if (!ops[op]) {
  fail(`unknown operation: ${op}. Try 'help'.`, 'BAD_OP');
}

try {
  await ops[op]();
} catch (e) {
  fail(e, e?.code || 'EXEC_FAILED');
}
