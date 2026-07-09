import { buildProfile, TASTE_QUESTIONS } from '../tasteInterview.js';

test('buildProfile maps answers to a structured profile', () => {
  const p = buildProfile({
    lean: 'bold_red', body: 'full', sweetness: 'dry', adventurous: 'open',
    regions_love: ['Napa', 'Rhône'], avoid: ['Oaky Chardonnay'],
  });
  expect(p).toMatchObject({
    lean: 'bold_red', body: 'full', sweetness: 'dry', adventurous: 'open',
    regions_love: ['Napa', 'Rhône'], avoid: ['Oaky Chardonnay'],
  });
  expect(p.completed_at).toBeTruthy();
});

test('buildProfile drops "no preference" / "nothing" sentinels', () => {
  const p = buildProfile({ regions_love: ['No strong preference'], avoid: ['Nothing, really'] });
  expect(p.regions_love).toEqual([]);
  expect(p.avoid).toEqual([]);
});

test('buildProfile tolerates a single (non-array) multi answer', () => {
  const p = buildProfile({ regions_love: 'Napa' });
  expect(p.regions_love).toEqual(['Napa']);
});

test('the interview is a short, ordered set with single/multi questions', () => {
  expect(TASTE_QUESTIONS.length).toBeGreaterThanOrEqual(5);
  expect(TASTE_QUESTIONS.every(q => q.id && q.prompt && q.options.length)).toBe(true);
  expect(TASTE_QUESTIONS.some(q => q.multi)).toBe(true);
});
