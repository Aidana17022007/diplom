// Local verification with explicitly synthetic form examples; never uses patient files.
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { buildPdf } from '../deployment/cardio-site/src/pdf.js';

const require = createRequire(new URL('../deployment/cardio-site/package.json', import.meta.url));
const { PDFDocument } = require('pdf-lib');
const origin = process.env.CARDIO_TEST_ORIGIN || 'http://127.0.0.1:8000';
const fixtures = process.env.CARDIO_PDF_FIXTURES ? JSON.parse(await readFile(process.env.CARDIO_PDF_FIXTURES, 'utf8')) : null;
const output = new URL('../tmp/pdfs/web-report/', import.meta.url);
await mkdir(output, { recursive: true });
const fontBytes = new Uint8Array(await readFile(new URL('../assets/DejaVuSans.ttf', import.meta.url)));
const samples = {
  brfss: { age_group: 13, sex: 2, bmi: 27.4, smoking: 4, activity: 1, diabetes: 4,
    hypertension: 4, cholesterol: 1, general_health: 4, physical_days: 2, mental_days: 1 },
  uci: { age: 55, sex: 1, cp: 3, trestbps: 130, chol: 240, fbs: 0, restecg: 2,
    thalach: 150, exang: 0, oldpeak: 1, slope: 2, ca: 0, thal: 7 },
};
const outcomes = [];
for (const dataset of ['brfss', 'uci']) {
  let schema = fixtures?.[dataset]?.schema;
  if (!schema) {
    const schemaResponse = await fetch(`${origin}/api/schema/${dataset}`);
    assert.equal(schemaResponse.status, 200);
    schema = await schemaResponse.json();
  }
  for (const lang of ['ru', 'kk']) {
    const values = { ...samples[dataset] };
    if (dataset === 'brfss' && lang === 'kk') values.bmi = null;
    let result = fixtures?.[dataset]?.[lang];
    if (!result) {
      const response = await fetch(`${origin}/api/predict`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset, values, lang, explain: true }) });
      assert.equal(response.status, 200);
      result = await response.json();
    }
    // Existing Python explanation uses these exact fixed counts.
    result.explanation.permutations = 48; result.explanation.background_size = 30;
    const start = performance.now();
    const bytes = await buildPdf({ dataset, values, lang, result, schema, fontBytes });
    const milliseconds = performance.now() - start;
    assert(bytes instanceof Uint8Array);
    assert.equal(Buffer.from(bytes.subarray(0, 5)).toString(), '%PDF-');
    assert(bytes.byteLength < 500_000, 'Unicode font should be subset');
    const reopened = await PDFDocument.load(bytes);
    assert(reopened.getPageCount() >= 2 && reopened.getPageCount() <= 3);
    assert(reopened.getTitle().startsWith('CardioResearch'));
    const filename = `${dataset}-${lang}-synthetic-example.pdf`;
    await writeFile(new URL(filename, output), bytes);
    outcomes.push({ dataset, lang, filename, pages: reopened.getPageCount(), bytes: bytes.byteLength,
      milliseconds: Math.round(milliseconds), processRssMb: Math.round(process.memoryUsage().rss / 1024 / 1024) });
    await assert.rejects(() => buildPdf({ dataset, values: { ...values, [schema.fields[0].name]: 'bad' },
      lang, result, schema, fontBytes }), /validated numbers/);
  }
}
await writeFile(new URL('verification.json', output), JSON.stringify({ generated: new Date().toISOString(), synthetic: true, outcomes }, null, 2));
console.log(JSON.stringify({ output: fileURLToPath(output), outcomes }, null, 2));
