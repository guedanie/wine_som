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

// Two DISCOVERY_REGIONS names differ from what the extractor wrote to wines.region.
// The backend handles the mapping; this export documents it for reference.
export const REGION_DB_ALIASES = {
  'Rhône Valley': 'Rhône',
  'Douro Valley': 'Douro',
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
  { name: 'Tuscany',           coord: '43.8°N · 11.2°E',   country: 'Italy',       subregion: 'Chianti & Brunello',          flavors: ['dark cherry', 'leather', 'tobacco'],        tier: 1 },
  { name: 'Paso Robles',       coord: '35.6°N · 120.7°W',  country: 'California',  subregion: 'Westside & Eastside',          flavors: ['dark fruit', 'garrigue', 'structure'],      tier: 1 },
  { name: 'Napa Valley',       coord: '38.5°N · 122.4°W',  country: 'California',  subregion: 'Oakville & Stags Leap',        flavors: ['blackcurrant', 'cedar', 'full body'],       tier: 1 },
  { name: 'Sonoma',            coord: '38.3°N · 122.5°W',  country: 'California',  subregion: 'Russian River & Dry Creek',    flavors: ['red fruit', 'bright acidity', 'coastal'],   tier: 1 },
  { name: 'Mendoza',           coord: '32.9°S · 68.8°W',   country: 'Argentina',   subregion: 'Luján de Cuyo & Valle de Uco', flavors: ['dark plum', 'chocolate', 'spice'],          tier: 1 },
  { name: 'Willamette Valley', coord: '45.5°N · 123.0°W',  country: 'Oregon',      subregion: 'Dundee Hills & Eola-Amity',    flavors: ['cherry', 'earthy', 'bright acidity'],       tier: 1 },
  { name: 'Bordeaux',          coord: '44.8°N · 0.6°W',    country: 'France',      subregion: 'Left Bank & Right Bank',       flavors: ['blackcurrant', 'cedar', 'graphite'],        tier: 1 },
  { name: 'Rioja',             coord: '42.3°N · 2.5°W',    country: 'Spain',       subregion: 'Rioja Alta & Alavesa',         flavors: ['cherry', 'vanilla', 'leather'],             tier: 1 },
  { name: 'Marlborough',       coord: '41.5°S · 173.9°E',  country: 'New Zealand', subregion: 'Wairau & Awatere',             flavors: ['citrus', 'passionfruit', 'bright acidity'], tier: 1 },
  { name: 'Barossa Valley',    coord: '34.5°S · 138.9°E',  country: 'Australia',   subregion: 'Eden Valley & Greenock',       flavors: ['dark fruit', 'chocolate', 'spice'],         tier: 1 },
  // Tier 2 — add posters to REGION_POSTERS as designed
  { name: 'Burgundy',          coord: '47.0°N · 4.8°E',    country: 'France',      subregion: 'Côte d\'Or & Chablis',         flavors: ['red fruit', 'earthy', 'silky'],             tier: 2 },
  { name: 'Rhône Valley',      coord: '45.0°N · 4.8°E',    country: 'France',      subregion: 'Northern & Southern',          flavors: ['dark fruit', 'garrigue', 'pepper'],         tier: 2 },
  { name: 'Champagne',         coord: '49.1°N · 4.0°E',    country: 'France',      subregion: 'Grand Crus & Premier Crus',    flavors: ['brioche', 'citrus', 'mineral'],             tier: 2 },
  { name: 'Piedmont',          coord: '44.7°N · 8.0°E',    country: 'Italy',       subregion: 'Barolo & Barbaresco',          flavors: ['dark cherry', 'tar', 'roses'],              tier: 2 },
  { name: 'Douro Valley',      coord: '41.1°N · 7.6°W',    country: 'Portugal',    subregion: 'Cima Corgo & Douro Superior',  flavors: ['dark fruit', 'spice', 'structure'],         tier: 2 },
  { name: 'Columbia Valley',   coord: '46.2°N · 119.9°W',  country: 'Washington',  subregion: 'Red Mountain & Walla Walla',   flavors: ['dark cherry', 'spice', 'balance'],          tier: 2 },
  { name: 'Maipo Valley',      coord: '33.5°S · 70.6°W',   country: 'Chile',       subregion: 'Alto Maipo & Isla de Maipo',   flavors: ['blackcurrant', 'tobacco', 'structure'],     tier: 2 },
  { name: 'Mosel',             coord: '49.9°N · 7.0°E',    country: 'Germany',     subregion: 'Middle Mosel & Saar',          flavors: ['citrus', 'slate', 'off-dry'],               tier: 2 },
];

export const REGION_META = Object.fromEntries(
  DISCOVERY_REGIONS.map(r => [r.name, r])
);

// URL slug ↔ region name (accent-stripped kebab-case)
export function regionSlug(name) {
  return name.normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

export const SLUG_TO_REGION = Object.fromEntries(
  DISCOVERY_REGIONS.map(r => [regionSlug(r.name), r.name])
);

// Curated region dossier content — climate/soil/altitude facts, principal
// varietals, sub-regions with coordinates, and map center/zoom.
// Sub-region wine counts come live from /api/region/:name/subregions.
export const REGION_DETAILS = {
  'Tuscany': {
    climate: 'Warm Mediterranean', climateSub: 'Hot dry summers, mild wet winters',
    soil: 'Galestro & Alberese', soilSub: 'Schist-limestone & clay-marl mix',
    altitude: '250 – 600 m', altitudeSub: 'Hillside vineyards above the fog line',
    parallelNote: 'southern Oregon',
    latlng: [43.4, 11.2], zoom: 8,
    varietals: ['Sangiovese', 'Canaiolo', 'Vernaccia', 'Cabernet Sauvignon', 'Merlot'],
    subregions: [
      { name: 'Chianti Classico', coord: '43.5° N · 11.3° E' },
      { name: 'Montalcino', coord: '43.0° N · 11.5° E' },
      { name: 'Montepulciano', coord: '43.1° N · 11.8° E' },
      { name: 'Bolgheri', coord: '43.2° N · 10.6° E' },
      { name: 'San Gimignano', coord: '43.5° N · 11.0° E' },
    ],
  },
  'Paso Robles': {
    climate: 'Hot Mediterranean', climateSub: 'Largest day-night temperature swing in CA (up to 30°C)',
    soil: 'Calcareous shale', soilSub: 'Limestone-rich hillsides, rare for California',
    altitude: '210 – 730 m', altitudeSub: 'Templeton Gap funnels Pacific air inland',
    parallelNote: 'southern Spain',
    latlng: [35.63, -120.69], zoom: 9,
    varietals: ['Cabernet Sauvignon', 'Syrah', 'Grenache', 'Mourvèdre', 'Zinfandel'],
    subregions: [
      { name: 'Willow Creek', coord: '35.6° N · 120.8° W' },
      { name: 'Adelaida', coord: '35.7° N · 120.9° W' },
      { name: 'Templeton Gap', coord: '35.5° N · 120.7° W' },
      { name: 'El Pomar', coord: '35.5° N · 120.6° W' },
    ],
  },
  'Napa Valley': {
    climate: 'Dry Mediterranean', climateSub: 'Morning fog off San Pablo Bay, hot afternoons',
    soil: 'Volcanic & alluvial', soilSub: 'Over 30 distinct soil series in one valley',
    altitude: '5 – 800 m', altitudeSub: 'Valley floor to Howell Mountain benches',
    parallelNote: 'southern Italy',
    latlng: [38.5, -122.4], zoom: 10,
    varietals: ['Cabernet Sauvignon', 'Merlot', 'Chardonnay', 'Sauvignon Blanc', 'Zinfandel'],
    subregions: [
      { name: 'Oakville', coord: '38.4° N · 122.4° W' },
      { name: 'Rutherford', coord: '38.5° N · 122.4° W' },
      { name: 'Stags Leap District', coord: '38.4° N · 122.3° W' },
      { name: 'Howell Mountain', coord: '38.6° N · 122.4° W' },
      { name: 'Carneros', coord: '38.3° N · 122.3° W' },
    ],
  },
  'Sonoma': {
    climate: 'Cool coastal', climateSub: 'Pacific fog and wind moderate ripening',
    soil: 'Sandy loam & volcanic', soilSub: 'Goldridge loam in Russian River',
    altitude: '0 – 750 m', altitudeSub: 'Coastal ridges to inland valleys',
    parallelNote: 'southern Italy',
    latlng: [38.4, -122.7], zoom: 9,
    varietals: ['Pinot Noir', 'Chardonnay', 'Zinfandel', 'Cabernet Sauvignon', 'Sauvignon Blanc'],
    subregions: [
      { name: 'Russian River Valley', coord: '38.5° N · 122.9° W' },
      { name: 'Dry Creek Valley', coord: '38.7° N · 122.9° W' },
      { name: 'Alexander Valley', coord: '38.7° N · 122.8° W' },
      { name: 'Sonoma Coast', coord: '38.4° N · 123.1° W' },
    ],
  },
  'Mendoza': {
    climate: 'High desert', climateSub: 'Sunny, arid — irrigated by Andean snowmelt',
    soil: 'Alluvial sand over clay', soilSub: 'Poor rocky soils force deep roots',
    altitude: '800 – 1,500 m', altitudeSub: 'Altitude replaces latitude for coolness',
    parallelNote: 'southern California (mirrored)',
    latlng: [-32.9, -68.8], zoom: 9,
    varietals: ['Malbec', 'Cabernet Sauvignon', 'Bonarda', 'Torrontés', 'Chardonnay'],
    subregions: [
      { name: 'Luján de Cuyo', coord: '33.0° S · 68.9° W' },
      { name: 'Valle de Uco', coord: '33.4° S · 69.2° W' },
      { name: 'Maipú', coord: '33.0° S · 68.7° W' },
    ],
  },
  'Willamette Valley': {
    climate: 'Cool maritime', climateSub: 'Wet winters, dry warm summers, long autumn',
    soil: 'Jory volcanic & marine sediment', soilSub: 'Red basalt hills vs uplifted seabed',
    altitude: '60 – 300 m', altitudeSub: 'Best sites above the valley frost line',
    parallelNote: 'Burgundy',
    latlng: [45.2, -123.1], zoom: 9,
    varietals: ['Pinot Noir', 'Pinot Gris', 'Chardonnay', 'Riesling'],
    subregions: [
      { name: 'Dundee Hills', coord: '45.3° N · 123.0° W' },
      { name: 'Eola-Amity Hills', coord: '45.0° N · 123.1° W' },
      { name: 'Yamhill-Carlton', coord: '45.3° N · 123.2° W' },
      { name: 'Ribbon Ridge', coord: '45.4° N · 123.0° W' },
    ],
  },
  'Bordeaux': {
    climate: 'Moderate maritime', climateSub: 'Gulf Stream warmth, Atlantic humidity',
    soil: 'Gravel & clay-limestone', soilSub: 'Gravel left bank, clay-limestone right',
    altitude: '0 – 100 m', altitudeSub: 'Low riverside plateaus, drainage is king',
    parallelNote: 'Oregon coast',
    latlng: [44.85, -0.58], zoom: 9,
    varietals: ['Cabernet Sauvignon', 'Merlot', 'Cabernet Franc', 'Sauvignon Blanc', 'Sémillon'],
    subregions: [
      { name: 'Médoc', coord: '45.2° N · 0.9° W' },
      { name: 'Saint-Émilion', coord: '44.9° N · 0.2° W' },
      { name: 'Pomerol', coord: '44.9° N · 0.2° W' },
      { name: 'Graves', coord: '44.6° N · 0.5° W' },
      { name: 'Sauternes', coord: '44.5° N · 0.3° W' },
    ],
  },
  'Rioja': {
    climate: 'Continental-Atlantic', climateSub: 'Sierra de Cantabria shields Atlantic storms',
    soil: 'Clay-limestone & ferrous clay', soilSub: 'Calcareous clay in Alta & Alavesa',
    altitude: '300 – 700 m', altitudeSub: 'Higher sites yield fresher Tempranillo',
    parallelNote: 'central Oregon',
    latlng: [42.4, -2.5], zoom: 9,
    varietals: ['Tempranillo', 'Garnacha', 'Graciano', 'Mazuelo', 'Viura'],
    subregions: [
      { name: 'Rioja Alta', coord: '42.5° N · 2.8° W' },
      { name: 'Rioja Alavesa', coord: '42.6° N · 2.6° W' },
      { name: 'Rioja Oriental', coord: '42.2° N · 2.0° W' },
    ],
  },
  'Marlborough': {
    climate: 'Cool maritime', climateSub: 'NZ’s sunniest region, cool nights',
    soil: 'Stony alluvial loam', soilSub: 'Free-draining Wairau riverbed gravels',
    altitude: '0 – 250 m', altitudeSub: 'Valley floor plains and southern clay hills',
    parallelNote: 'central Oregon (mirrored)',
    latlng: [-41.5, 173.9], zoom: 9,
    varietals: ['Sauvignon Blanc', 'Pinot Noir', 'Pinot Gris', 'Chardonnay', 'Riesling'],
    subregions: [
      { name: 'Wairau Valley', coord: '41.5° S · 173.9° E' },
      { name: 'Awatere Valley', coord: '41.7° S · 174.0° E' },
      { name: 'Southern Valleys', coord: '41.6° S · 173.8° E' },
    ],
  },
  'Barossa Valley': {
    climate: 'Warm continental', climateSub: 'Hot dry summers, some of the world’s oldest vines',
    soil: 'Clay loam & ironstone', soilSub: 'Red-brown earth over limestone',
    altitude: '230 – 550 m', altitudeSub: 'Eden Valley sits high and cool to the east',
    parallelNote: 'San Diego (mirrored)',
    latlng: [-34.53, 138.95], zoom: 10,
    varietals: ['Shiraz', 'Grenache', 'Mataro', 'Cabernet Sauvignon', 'Riesling'],
    subregions: [
      { name: 'Eden Valley', coord: '34.6° S · 139.1° E' },
      { name: 'Greenock', coord: '34.5° S · 138.9° E' },
      { name: 'Marananga', coord: '34.5° S · 138.9° E' },
    ],
  },
  'Burgundy': {
    climate: 'Cool continental', climateSub: 'Marginal ripening — vintage matters enormously',
    soil: 'Jurassic limestone & marl', soilSub: 'The original terroir mosaic — climat by climat',
    altitude: '200 – 400 m', altitudeSub: 'Mid-slope is the golden band',
    parallelNote: 'Seattle',
    latlng: [47.0, 4.8], zoom: 8,
    varietals: ['Pinot Noir', 'Chardonnay', 'Aligoté', 'Gamay'],
    subregions: [
      { name: 'Côte de Nuits', coord: '47.2° N · 4.9° E' },
      { name: 'Côte de Beaune', coord: '47.0° N · 4.8° E' },
      { name: 'Chablis', coord: '47.8° N · 3.8° E' },
      { name: 'Mâconnais', coord: '46.3° N · 4.7° E' },
    ],
  },
  'Rhône Valley': {
    climate: 'Continental north, Mediterranean south', climateSub: 'Mistral wind dries and concentrates',
    soil: 'Granite north, galets south', soilSub: 'Rolled stones store daytime heat',
    altitude: '100 – 400 m', altitudeSub: 'Steep terraced north, broad plains south',
    parallelNote: 'Willamette Valley',
    latlng: [44.9, 4.85], zoom: 8,
    varietals: ['Syrah', 'Grenache', 'Mourvèdre', 'Viognier', 'Marsanne'],
    subregions: [
      { name: 'Côte-Rôtie', coord: '45.5° N · 4.8° E' },
      { name: 'Hermitage', coord: '45.1° N · 4.8° E' },
      { name: 'Châteauneuf-du-Pape', coord: '44.1° N · 4.8° E' },
      { name: 'Gigondas', coord: '44.2° N · 5.0° E' },
    ],
  },
  'Champagne': {
    climate: 'Cold continental', climateSub: 'At the edge of ripening — acid is the asset',
    soil: 'Belemnite chalk', soilSub: 'Pure chalk stores water, reflects light',
    altitude: '90 – 300 m', altitudeSub: 'Gentle slopes above the Marne',
    parallelNote: 'Vancouver Island',
    latlng: [49.05, 4.0], zoom: 9,
    varietals: ['Chardonnay', 'Pinot Noir', 'Pinot Meunier'],
    subregions: [
      { name: 'Montagne de Reims', coord: '49.2° N · 4.0° E' },
      { name: 'Côte des Blancs', coord: '48.9° N · 4.0° E' },
      { name: 'Vallée de la Marne', coord: '49.1° N · 3.7° E' },
    ],
  },
  'Piedmont': {
    climate: 'Continental with fog', climateSub: 'La nebbia — autumn fog names the grape',
    soil: 'Calcareous marl', soilSub: 'Tortonian vs Serravallian marls split Barolo',
    altitude: '150 – 500 m', altitudeSub: 'Hilltop villages, south-facing crus',
    parallelNote: 'Willamette Valley',
    latlng: [44.6, 8.0], zoom: 9,
    varietals: ['Nebbiolo', 'Barbera', 'Dolcetto', 'Moscato', 'Arneis'],
    subregions: [
      { name: 'Barolo', coord: '44.6° N · 7.9° E' },
      { name: 'Barbaresco', coord: '44.7° N · 8.1° E' },
      { name: 'Asti', coord: '44.9° N · 8.2° E' },
      { name: 'Gavi', coord: '44.7° N · 8.8° E' },
    ],
  },
  'Douro Valley': {
    climate: 'Hot continental', climateSub: 'Schist traps heat; brutal summers',
    soil: 'Layered schist', soilSub: 'Vines root metres deep through rock seams',
    altitude: '100 – 700 m', altitudeSub: 'Hand-built terraces above the river',
    parallelNote: 'northern California',
    latlng: [41.15, -7.6], zoom: 9,
    varietals: ['Touriga Nacional', 'Touriga Franca', 'Tinta Roriz', 'Tinta Barroca'],
    subregions: [
      { name: 'Cima Corgo', coord: '41.2° N · 7.5° W' },
      { name: 'Douro Superior', coord: '41.1° N · 7.1° W' },
      { name: 'Baixo Corgo', coord: '41.2° N · 7.8° W' },
    ],
  },
  'Columbia Valley': {
    climate: 'Arid continental', climateSub: 'Rain shadow of the Cascades — 200 mm/year',
    soil: 'Missoula flood sediment', soilSub: 'Loess over basalt, phylloxera-free sands',
    altitude: '120 – 600 m', altitudeSub: 'Long summer daylight at 46°N',
    parallelNote: 'Bordeaux',
    latlng: [46.3, -119.5], zoom: 8,
    varietals: ['Cabernet Sauvignon', 'Merlot', 'Syrah', 'Riesling', 'Chardonnay'],
    subregions: [
      { name: 'Red Mountain', coord: '46.3° N · 119.4° W' },
      { name: 'Walla Walla Valley', coord: '46.0° N · 118.3° W' },
      { name: 'Horse Heaven Hills', coord: '46.0° N · 119.8° W' },
      { name: 'Yakima Valley', coord: '46.3° N · 120.0° W' },
    ],
  },
  'Maipo Valley': {
    climate: 'Mediterranean', climateSub: 'Andes air drains cool into the valley at night',
    soil: 'Alluvial gravel', soilSub: 'Stony free-draining terraces near the river',
    altitude: '400 – 1,000 m', altitudeSub: 'Alto Maipo climbs the Andean foothills',
    parallelNote: 'Los Angeles (mirrored)',
    latlng: [-33.6, -70.7], zoom: 9,
    varietals: ['Cabernet Sauvignon', 'Carmenère', 'Merlot', 'Syrah'],
    subregions: [
      { name: 'Alto Maipo', coord: '33.6° S · 70.5° W' },
      { name: 'Isla de Maipo', coord: '33.8° S · 70.9° W' },
    ],
  },
  'Mosel': {
    climate: 'Cool continental', climateSub: 'Steep slate slopes catch every ray',
    soil: 'Blue & red Devonian slate', soilSub: 'Heat-retaining shards on 60° inclines',
    altitude: '100 – 350 m', altitudeSub: 'Europe’s steepest vineyards',
    parallelNote: 'Newfoundland',
    latlng: [49.95, 7.1], zoom: 9,
    varietals: ['Riesling', 'Müller-Thurgau', 'Elbling', 'Pinot Blanc'],
    subregions: [
      { name: 'Middle Mosel', coord: '49.9° N · 7.0° E' },
      { name: 'Saar', coord: '49.6° N · 6.5° E' },
      { name: 'Ruwer', coord: '49.8° N · 6.7° E' },
    ],
  },
};

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
