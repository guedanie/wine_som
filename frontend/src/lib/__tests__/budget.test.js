import { readFileSync, readdirSync } from 'fs';
import { join } from 'path';
import { BUDGET_SLIDER } from '../budget.js';

// 2026-09-10: PreferenceCapture's two layouts disagreed. Mobile ran
// min15/max200/step5, desktop min15/max150 with no step — so the SAME user got
// a different ceiling depending on device, and desktop produced odd values like
// $137 while mobile snapped to fives. Nothing caught it because the number was
// typed inline in four places across two files.
//
// Scanning source rather than rendering, because the risk is a hardcoded literal
// drifting back in — a render test of today's components would pass while a new
// screen quietly introduced a fifth ceiling.
const SCREENS = join(__dirname, '..', '..', 'screens');

function priceSliders() {
  const found = [];
  for (const file of readdirSync(SCREENS).filter(f => f.endsWith('.jsx'))) {
    const src = readFileSync(join(SCREENS, file), 'utf8');
    src.split('\n').forEach((line, i) => {
      if (!line.includes('type="range"')) return;
      // Only price/budget sliders — other ranges (e.g. structure axes) are free
      // to use their own scale.
      if (!/budget|maxPrice/i.test(line)) return;
      found.push({ file, line: i + 1, text: line });
    });
  }
  return found;
}

describe('budget slider bounds', () => {
  it('finds the price sliders it is meant to guard', () => {
    // If this drops to zero the guard has silently stopped guarding — e.g. the
    // markup changed shape and the matcher no longer sees anything.
    expect(priceSliders().length).toBeGreaterThanOrEqual(4);
  });

  it('has no hardcoded min/max/step left in any price slider', () => {
    const offenders = priceSliders()
      .filter(s => /\b(min|max|step)=\{\d/.test(s.text))
      .map(s => `${s.file}:${s.line}`);
    expect(offenders).toEqual([]);
  });

  it('exposes one shared set of bounds', () => {
    expect(BUDGET_SLIDER).toEqual({ min: 15, max: 200, step: 5 });
  });
});
