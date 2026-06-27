// frontend/src/lib/regions.js

export const STYLE_TAG_MAP = {
  'Bold & Tannic':   ['dark fruit', 'grip', 'structure', 'full body'],
  'Light & Elegant': ['red fruit', 'silky', 'bright acidity', 'light body'],
  'Earthy & Savory': ['earthy', 'herbal', 'leather', 'mineral'],
  'Bright & Fruity': ['juicy', 'fresh fruit', 'easy drinking'],
};

export const STYLE_WINE_TYPE = {
  'Bold & Tannic':   'red',
  'Light & Elegant': 'red',
  'Earthy & Savory': null,
  'Bright & Fruity': null,
};

export const VARIETAL_OPTS = [
  'Cabernet Sauvignon', 'Merlot', 'Pinot Noir', 'Malbec', 'Syrah',
  'Zinfandel', 'Sangiovese', 'Chardonnay', 'Sauvignon Blanc',
  'Riesling', 'Pinot Grigio', 'Albariño',
];

// All 10 Tier 1 region posters are live. Tier 2 regions fall back to the
// striped placeholder in the Poster component until posters are designed.
export const REGION_POSTERS = {
  'Tuscany':           '/assets/poster-tuscany.png',
  'Paso Robles':       '/assets/poster-paso-robles.png',
  'Napa Valley':       '/assets/poster-napa.png',
  'Sonoma':            '/assets/poster-sonoma.png',
  'Mendoza':           '/assets/poster-mendoza.png',
  'Willamette Valley': '/assets/poster-willamette.png',
  'Bordeaux':          '/assets/poster-bordeaux.png',
  'Rioja':             '/assets/poster-rioja.png',
  'Marlborough':       '/assets/poster-marlborough.png',
  'Barossa Valley':    '/assets/poster-barossa.png',
};

export const DISCOVERY_REGIONS = [
  // Tier 1 — high priority (common at SA retailers)
  { name: 'Tuscany',           coord: '43.8°N · 11.2°E',   flavors: ['dark cherry', 'leather', 'tobacco'],        tier: 1 },
  { name: 'Paso Robles',       coord: '35.6°N · 120.7°W',  flavors: ['dark fruit', 'garrigue', 'structure'],      tier: 1 },
  { name: 'Napa Valley',       coord: '38.5°N · 122.4°W',  flavors: ['blackcurrant', 'cedar', 'full body'],       tier: 1 },
  { name: 'Sonoma',            coord: '38.3°N · 122.5°W',  flavors: ['red fruit', 'bright acidity', 'coastal'],   tier: 1 },
  { name: 'Mendoza',           coord: '32.9°S · 68.8°W',   flavors: ['dark plum', 'chocolate', 'spice'],          tier: 1 },
  { name: 'Willamette Valley', coord: '45.5°N · 123.0°W',  flavors: ['cherry', 'earthy', 'bright acidity'],       tier: 1 },
  { name: 'Bordeaux',          coord: '44.8°N · 0.6°W',    flavors: ['blackcurrant', 'cedar', 'graphite'],        tier: 1 },
  { name: 'Rioja',             coord: '42.3°N · 2.5°W',    flavors: ['cherry', 'vanilla', 'leather'],             tier: 1 },
  { name: 'Marlborough',       coord: '41.5°S · 173.9°E',  flavors: ['citrus', 'passionfruit', 'bright acidity'], tier: 1 },
  { name: 'Barossa Valley',    coord: '34.5°S · 138.9°E',  flavors: ['dark fruit', 'chocolate', 'spice'],         tier: 1 },
  // Tier 2 — add posters to REGION_POSTERS as designed
  { name: 'Burgundy',          coord: '47.0°N · 4.8°E',    flavors: ['red fruit', 'earthy', 'silky'],             tier: 2 },
  { name: 'Rhône Valley',      coord: '45.0°N · 4.8°E',    flavors: ['dark fruit', 'garrigue', 'pepper'],         tier: 2 },
  { name: 'Champagne',         coord: '49.1°N · 4.0°E',    flavors: ['brioche', 'citrus', 'mineral'],             tier: 2 },
  { name: 'Piedmont',          coord: '44.7°N · 8.0°E',    flavors: ['dark cherry', 'tar', 'roses'],              tier: 2 },
  { name: 'Douro Valley',      coord: '41.1°N · 7.6°W',    flavors: ['dark fruit', 'spice', 'structure'],         tier: 2 },
  { name: 'Columbia Valley',   coord: '46.2°N · 119.9°W',  flavors: ['dark cherry', 'spice', 'balance'],          tier: 2 },
  { name: 'Maipo Valley',      coord: '33.5°S · 70.6°W',   flavors: ['blackcurrant', 'tobacco', 'structure'],     tier: 2 },
  { name: 'Mosel',             coord: '49.9°N · 7.0°E',    flavors: ['citrus', 'slate', 'off-dry'],               tier: 2 },
];

export function occasionMessage(occasion) {
  const map = {
    'Tonight':      'I want something to open tonight.',
    'This weekend': 'I want something for this weekend.',
    'Cellar it':    'I am looking for something to cellar.',
  };
  return map[occasion] ?? 'Recommend wines based on my preferences.';
}

export function deriveWineCardMeta(pick) {
  const regionData = DISCOVERY_REGIONS.find(
    r => r.name.toLowerCase() === (pick.region ?? '').toLowerCase()
  );
  return {
    ...pick,
    tagline: pick.region?.toUpperCase() ?? pick.varietal?.toUpperCase() ?? 'AVAILABLE NEAR YOU',
    coord:   regionData?.coord ?? null,
    flavors: pick.flavor_profile ?? regionData?.flavors ?? [],
  };
}

export function buildApiReq(prefs) {
  const tags = [...new Set(prefs.styles.flatMap(s => STYLE_TAG_MAP[s] ?? []))];
  // wine_types from explicit chip selection; fall back to style-derived type if none selected
  const wineTypes = (prefs.wineTypes ?? []).length > 0
    ? prefs.wineTypes
    : [prefs.styles.map(s => STYLE_WINE_TYPE[s]).find(Boolean)].filter(Boolean);
  return {
    zip_code:          prefs.zip,
    budget_min:        10,
    budget_max:        prefs.budget,
    style_preferences: tags,
    wine_types:        wineTypes,
    grapes:            prefs.grapes ?? [],
    message:           prefs.freeText?.trim() || occasionMessage(prefs.occasion),
  };
}
