import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';

const bundle = await build({entryPoints: ['client/src/thresholdComparison.ts'], bundle: true, format: 'esm', write: false});
const {thresholdPoint, buildThresholdLab, displayedCounts, compareThresholds, thresholdComparisonCsv, formatSignedDelta} = await import('data:text/javascript;base64,' + Buffer.from(bundle.outputFiles[0].text).toString('base64'));
const reports = JSON.parse(await readFile(new URL('../data/reports.json', import.meta.url), 'utf8'));
const research = reports.research.brfss;
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-12, `${a} != ${b}`);

test('the initial and reset reference is the exact saved validation result, not its nearest grid point', () => {
  const before = JSON.stringify(research);
  const {points, baseline, baselineIndex, gridCount} = buildThresholdLab(research);
  assert.equal(gridCount, 35);
  assert.equal(points.length, 36);
  assert.equal(points[baselineIndex], baseline);
  assert.equal(baseline.threshold, 0.19042448230963954);
  assert.deepEqual(baseline.confusion, [[42328, 4763], [2203, 2155]]);
  assert.equal(baseline.n, 51449);
  assert.equal(baseline.positive, 4358);
  assert.equal(baseline.negative, 47091);
  const model = research.full.find(row => row.name === research.selection.deployed_model);
  for (const key of ['accuracy', 'precision', 'recall', 'specificity', 'f1']) close(baseline.metrics[key], model.validation[key]);
  const nearest = points.filter(p => p.source === 'grid').sort((a, b) => Math.abs(a.threshold-baseline.threshold)-Math.abs(b.threshold-baseline.threshold))[0];
  assert.notEqual(nearest.threshold, baseline.threshold);
  assert.deepEqual(compareThresholds(baseline, nearest).countDelta, {tn:1, fp:-1, fn:5, tp:-5});
  assert.equal(JSON.stringify(research), before);
  baseline.confusion[0][0] = 0;
  assert.equal(JSON.stringify(research), before);
});

test('all saved grid points are comparable and preserve class totals, monotonic counts and metric formulas', () => {
  const {points, baseline} = buildThresholdLab(research);
  for (const [index, point] of points.entries()) {
    assert.equal(point.n, baseline.n);
    assert.equal(point.positive, baseline.positive);
    assert.equal(point.negative, baseline.negative);
    assert.ok(Object.values(point.metrics).every(v => v === null || (v >= -1 && v <= 1)));
    const {tn,fp,fn,tp} = point.counts;
    close(point.metrics.balanced_accuracy, (tp/(tp+fn)+tn/(tn+fp))/2);
    close(point.metrics.npv, tn/(tn+fn));
    close(point.metrics.mcc, (tp*tn-fp*fn)/Math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)));
    const delta = compareThresholds(baseline, point);
    assert.equal(delta.countDelta.tp + delta.countDelta.fn, 0);
    assert.equal(delta.countDelta.tn + delta.countDelta.fp, 0);
    if (index) {
      assert.ok(point.threshold > points[index-1].threshold);
      assert.ok(point.counts.tp <= points[index-1].counts.tp);
      assert.ok(point.counts.fp <= points[index-1].counts.fp);
    }
  }
});

test('counts per 1000 preserve proportions and do not change metrics or treat validation as new patients', () => {
  const {points, baseline} = buildThresholdLab(research);
  const alternative = points[0];
  const raw = compareThresholds(baseline, alternative);
  const scaled = compareThresholds(baseline, alternative, 'per1000');
  close(Object.values(displayedCounts(alternative, 'per1000')).reduce((a,b)=>a+b,0), 1000);
  for (const key of ['tn', 'fp', 'fn', 'tp']) {
    close(scaled.counts[key], alternative.counts[key]/alternative.n*1000);
    close(scaled.countDelta[key], raw.countDelta[key]/alternative.n*1000);
  }
  assert.deepEqual(scaled.metricDelta, raw.metricDelta);
  assert.deepEqual(compareThresholds(baseline, baseline).countDelta, {tn:0,fp:0,fn:0,tp:0});
});

test('small nonzero deltas keep their sign instead of displaying misleading signed zero', () => {
  const {points, baseline} = buildThresholdLab(research);
  const nearest = points.filter(p=>p.source==='grid').sort((a,b)=>Math.abs(a.threshold-baseline.threshold)-Math.abs(b.threshold-baseline.threshold))[0];
  const raw = compareThresholds(baseline,nearest);
  const scaled = compareThresholds(baseline,nearest,'per1000');
  for (const locale of ['ru-RU','kk-KZ']) {
    assert.equal(formatSignedDelta(scaled.countDelta.fp,1,locale),'−<0,1');
    assert.equal(formatSignedDelta(scaled.countDelta.tn,1,locale),'+<0,1');
    assert.equal(formatSignedDelta(scaled.countDelta.fn,1,locale),'+0,1');
    assert.equal(formatSignedDelta(raw.countDelta.fp,0,locale),'−1');
    assert.equal(formatSignedDelta(0,1,locale),'0,0');
    assert.equal(formatSignedDelta(-0,1,locale),'0,0');
    assert.equal(formatSignedDelta(.05,1,locale),'+0,1');
  }
  assert.equal(formatSignedDelta(.000002,4,'en-US'),'+<0.0001');
  assert.equal(formatSignedDelta(-.000002,4,'en-US'),'−<0.0001');
  assert.equal(formatSignedDelta(0,4,'en-US'),'0.0000');
  assert.equal(formatSignedDelta(null,4,'en-US'),'—');
  assert.equal(formatSignedDelta(NaN,4,'en-US'),'—');
  assert.equal(formatSignedDelta(Infinity,4,'en-US'),'—');
  // Formatting is presentation only: the underlying differences remain exact.
  assert.equal(raw.countDelta.fp,-1);
  close(scaled.countDelta.fp,-1000/baseline.n);
});

test('undefined ratios stay null and invalid matrices cannot create misleading statistics', () => {
  const noPredictedPositive = thresholdPoint(.5, [[90,0],[10,0]]);
  assert.equal(noPredictedPositive.metrics.precision, null);
  assert.equal(noPredictedPositive.metrics.mcc, null);
  assert.equal(noPredictedPositive.metrics.f1, 0);
  const onlyNegative = thresholdPoint(.5, [[100,0],[0,0]]);
  assert.equal(onlyNegative.metrics.recall, null);
  assert.equal(onlyNegative.metrics.balanced_accuracy, null);
  assert.equal(onlyNegative.metrics.f1, null);
  assert.equal(onlyNegative.metrics.npv, 1);
  const onlyPositive = thresholdPoint(.5, [[0,0],[0,100]]);
  assert.equal(onlyPositive.metrics.npv, null);
  for (const matrix of [null, [], [[0,0],[0,0]], [[1,-1],[2,3]], [[1,.5],[2,3]], [[1,NaN],[2,3]], [[1,2,3],[4,5,6]], [['1',2],[3,4]]]) assert.equal(thresholdPoint(.5,matrix), null);
  for (const threshold of [null, '0.5', NaN, Infinity, -.1, 1.1]) assert.equal(thresholdPoint(threshold,[[1,2],[3,4]]), null);
  assert.throws(()=>compareThresholds(noPredictedPositive, onlyNegative), /same validation/);
});

test('duplicate thresholds are replaced with the exact working point and mismatched validation rows are excluded', () => {
  const modified = structuredClone(research);
  modified.threshold_curve.push({...modified.threshold_curve[0]}, {threshold:research.selection.threshold,confusion:[[1,1],[1,1]]});
  const lab = buildThresholdLab(modified);
  assert.equal(lab.points.length,36);
  assert.equal(lab.points.filter(p=>p.source==='working').length,1);
  const wrongModel = structuredClone(research);
  wrongModel.full.find(row=>row.name===wrongModel.selection.deployed_model).threshold = .5;
  assert.equal(buildThresholdLab(wrongModel).baseline,null);
  const wrongN = structuredClone(research);
  wrongN.protocol.validation += 1;
  assert.equal(buildThresholdLab(wrongN).baseline,null);
  assert.deepEqual(buildThresholdLab(null).points,[]);
});

test('CSV preserves exact thresholds, validation context, raw and scaled counts, and scenario deltas', () => {
  const {points, baseline} = buildThresholdLab(research);
  const alternative = points[0];
  const csv = thresholdComparisonCsv(baseline, alternative, research.selection.deployed_model);
  const [header,...rows] = csv.trim().split('\r\n').map(line=>line.split(','));
  assert.equal(rows.length,2);
  const records = rows.map(row=>Object.fromEntries(header.map((key,index)=>[key,row[index]])));
  for (const row of records) {
    assert.equal(row.evaluation,'validation');
    assert.equal(row.weighting,'unweighted');
    assert.equal(row.decision_rule,'probability >= threshold');
    assert.equal(Number(row.n),51449);
    assert.equal(Number(row.reference_threshold),baseline.threshold);
  }
  assert.equal(records[0].role,'working_reference');
  assert.equal(Number(records[0].threshold),baseline.threshold);
  assert.equal(Number(records[1].threshold),alternative.threshold);
  assert.equal(Number(records[1].delta_fn),alternative.counts.fn-baseline.counts.fn);
  close(Number(records[1].fn_per_1000),alternative.counts.fn/alternative.n*1000);
  assert.ok(!header.includes('roc_auc') && !header.includes('average_precision'));
  const undefinedMetric = thresholdPoint(.5,[[90,0],[10,0]]);
  const undefinedCsv = thresholdComparisonCsv(undefinedMetric,undefinedMetric,'=metadata');
  assert.ok(undefinedCsv.includes("'=metadata"));
  assert.ok(!undefinedCsv.includes('NaN') && !undefinedCsv.includes('null'));
});
