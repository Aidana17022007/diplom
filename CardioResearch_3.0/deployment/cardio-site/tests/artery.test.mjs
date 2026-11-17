import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

const bundle = await build({entryPoints: ['client/src/arteryGeometry.ts'], bundle: true, format: 'esm', write: false});
const {clampNarrowing, remainingArea, lumenRadius, clampSectionPosition, sectionMetrics} = await import('data:text/javascript;base64,' + Buffer.from(bundle.outputFiles[0].text).toString('base64'));

test('diameter narrowing is distinct from area loss', () => {
  assert.equal(remainingArea(0), 100);
  assert.equal(remainingArea(50), 25);
  assert.ok(Math.abs(remainingArea(80) - 4) < 1e-10);
});
test('the central radius matches the displayed diameter; ends remain open', () => {
  for (const n of [0, 25, 40, 50, 75, 80]) {
    assert.ok(Math.abs(lumenRadius(0, n) - (1 - n / 100)) < 1e-10);
    assert.equal(lumenRadius(-3.6, n), 1);
    assert.equal(lumenRadius(3.6, n), 1);
    for (let x = -3.6; x <= 3.6; x += .05) {
      const radius = lumenRadius(x, n);
      assert.ok(radius >= .199999 && radius <= 1);
      assert.ok(Math.abs(radius - lumenRadius(-x, n)) < 1e-10);
    }
  }
});
test('invalid and out-of-range geometry inputs cannot collapse the lumen', () => {
  assert.equal(clampNarrowing(NaN), 0);
  assert.equal(clampNarrowing(Infinity), 0);
  assert.equal(clampNarrowing(-1), 0);
  assert.equal(clampNarrowing(120), 80);
});

test('movable section reports local diameter and area rather than maximum narrowing', () => {
  const center=sectionMetrics(0,50);
  assert.equal(center.diameterPercent,50);
  assert.equal(center.areaPercent,25);
  assert.equal(center.areaLossPercent,75);
  for(const x of [-3.6,-2.6,2.6,3.6]){
    const end=sectionMetrics(x,50);
    assert.equal(end.diameterPercent,100);
    assert.equal(end.areaPercent,100);
    assert.equal(end.narrowingPercent,0);
  }
  const midway=sectionMetrics(1.3,50);
  assert.equal(midway.diameterPercent,71.875);
  assert.equal(midway.areaPercent,51.66015625);
  assert.deepEqual(sectionMetrics(-1.3,50),{...midway,position:-1.3});
});

test('normal geometry and bounded section positions are stable at every location', () => {
  for(const x of [-99,-3.6,-2.1,0,1.8,3.6,99,NaN,Infinity]){
    const normal=sectionMetrics(x,0);
    assert.equal(normal.diameterPercent,100);
    assert.equal(normal.areaPercent,100);
    assert.equal(normal.areaLossPercent,0);
    assert.ok(normal.position>=-3.6&&normal.position<=3.6);
  }
  assert.equal(clampSectionPosition(-99),-3.6);
  assert.equal(clampSectionPosition(99),3.6);
  assert.equal(clampSectionPosition(NaN),0);
  assert.equal(clampSectionPosition(Infinity),0);
  assert.equal(sectionMetrics(0,120).areaPercent,remainingArea(80));
});
