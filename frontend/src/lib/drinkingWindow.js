// Deterministic drinking-window heuristic — "what to open when" for the cellar,
// from varietal + vintage (no LLM, like the structure table). Rough by design;
// the user can override. [peakStart, windowEnd] = years from the vintage.

const GRAPE_AGING = {
  // age-worthy structured reds
  'Cabernet Sauvignon': [4, 15], 'Nebbiolo': [5, 20], 'Syrah': [3, 12],
  'Sangiovese': [3, 12], 'Aglianico': [4, 15], 'Tannat': [4, 15],
  'Tempranillo': [3, 12], 'Touriga Nacional': [4, 15], 'Petite Sirah': [4, 14],
  'Cabernet Franc': [3, 12], 'Bordeaux': [4, 18],
  // medium reds
  'Merlot': [2, 8], 'Malbec': [2, 8], 'Zinfandel': [1, 6], 'Primitivo': [1, 6],
  'Grenache': [2, 8], 'Garnacha': [2, 8], 'Pinot Noir': [2, 8], 'Barbera': [1, 6],
  'Montepulciano': [2, 8], 'Carmenère': [2, 8], "Nero d'Avola": [2, 8],
  'Mourvèdre': [2, 9], 'Monastrell': [2, 9], 'Carignan': [2, 8],
  // light reds — drink young
  'Gamay': [0, 3], 'Dolcetto': [0, 4], 'Cinsault': [0, 3], 'Corvina': [1, 6],
  // age-worthy whites
  'Riesling': [2, 12], 'Chenin Blanc': [2, 12],
  // rich whites
  'Chardonnay': [1, 6], 'Viognier': [1, 4], 'Marsanne': [1, 6], 'Roussanne': [1, 6],
  'Sémillon': [2, 10], 'Fiano': [1, 5],
  // crisp whites — drink young
  'Sauvignon Blanc': [0, 2], 'Pinot Grigio': [0, 2], 'Pinot Gris': [0, 3],
  'Albariño': [0, 2], 'Vermentino': [0, 2], 'Verdejo': [0, 2], 'Grüner Veltliner': [0, 3],
  'Melon de Bourgogne': [0, 3], 'Assyrtiko': [0, 4], 'Torrontés': [0, 2],
  'Gewürztraminer': [1, 5], 'Garganega': [1, 5],
  // sweet / aromatic
  'Moscato': [0, 2], 'Muscat': [0, 3],
};

const TYPE_AGING = {
  red: [2, 8], white: [0, 3], rose: [0, 2], rosé: [0, 2],
  sparkling: [0, 3], dessert: [3, 25], fortified: [3, 30], orange: [1, 6],
};

function _norm(s) {
  return (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').trim().toLowerCase();
}
const _GRAPE_IDX = Object.fromEntries(Object.entries(GRAPE_AGING).map(([k, v]) => [_norm(k), v]));
const _TYPE_IDX = Object.fromEntries(Object.entries(TYPE_AGING).map(([k, v]) => [_norm(k), v]));

export function drinkingWindow(varietal, wineType, vintage) {
  const yr = Number(vintage);
  if (!yr || yr < 1900) return null;
  const span = _GRAPE_IDX[_norm(varietal)] || _TYPE_IDX[_norm(wineType)] || null;
  if (!span) return null;
  return { from: yr + span[0], to: yr + span[1] };
}

// Where "now" sits in the window → phase + label + a 0–100 fill for the bar.
export function windowStatus(window, now = new Date().getFullYear()) {
  if (!window) return null;
  const { from, to } = window;
  const fill = Math.max(0, Math.min(100, Math.round(((now - from) / Math.max(1, to - from)) * 100)));
  let phase, label;
  if (now < from) { phase = 'hold'; label = `Hold to ${from}`; }
  else if (now > to) { phase = 'past'; label = 'Past its peak'; }
  else if (to - now <= 1) { phase = 'soon'; label = 'Drink soon'; }
  else if (now - from <= 1) { phase = 'ready'; label = 'Drink now'; }
  else { phase = 'ready'; label = `Peak ${from}–${to}`; }
  return { phase, label, fill };
}
