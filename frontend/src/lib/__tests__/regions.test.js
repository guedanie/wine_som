import {
  STYLE_TAG_MAP, STYLE_WINE_TYPE, DISCOVERY_REGIONS, REGION_POSTERS,
  occasionMessage, deriveWineCardMeta, buildApiReq,
} from '../regions.js';

describe('STYLE_TAG_MAP', () => {
  it('has entries for all four style cards', () => {
    expect(STYLE_TAG_MAP['Bold & Tannic']).toContain('dark fruit');
    expect(STYLE_TAG_MAP['Light & Elegant']).toContain('red fruit');
    expect(STYLE_TAG_MAP['Earthy & Savory']).toContain('earthy');
    expect(STYLE_TAG_MAP['Bright & Fruity']).toContain('juicy');
  });
});

describe('STYLE_WINE_TYPE', () => {
  it('maps Bold & Tannic to red', () => {
    expect(STYLE_WINE_TYPE['Bold & Tannic']).toBe('red');
  });
  it('maps Earthy & Savory to null', () => {
    expect(STYLE_WINE_TYPE['Earthy & Savory']).toBeNull();
  });
});

describe('DISCOVERY_REGIONS', () => {
  it('has 18 regions total', () => {
    expect(DISCOVERY_REGIONS).toHaveLength(18);
  });
  it('has 10 tier-1 regions', () => {
    expect(DISCOVERY_REGIONS.filter(r => r.tier === 1)).toHaveLength(10);
  });
  it('tier-1 regions come before tier-2', () => {
    const firstTier2 = DISCOVERY_REGIONS.findIndex(r => r.tier === 2);
    const lastTier1 = DISCOVERY_REGIONS.findLastIndex(r => r.tier === 1);
    expect(lastTier1).toBeLessThan(firstTier2);
  });
});

describe('REGION_POSTERS', () => {
  it('has real poster paths for all 10 Tier 1 regions', () => {
    const tier1Names = DISCOVERY_REGIONS.filter(r => r.tier === 1).map(r => r.name);
    for (const name of tier1Names) {
      expect(REGION_POSTERS[name]).toBeDefined();
      expect(REGION_POSTERS[name]).toMatch(/^\/assets\/poster-/);
    }
  });
  it('Tuscany poster path is correct', () => {
    expect(REGION_POSTERS['Tuscany']).toBe('/assets/poster-tuscany.png');
  });
});

describe('occasionMessage', () => {
  it('maps Tonight', () => {
    expect(occasionMessage('Tonight')).toBe('I want something to open tonight.');
  });
  it('maps This weekend', () => {
    expect(occasionMessage('This weekend')).toBe('I want something for this weekend.');
  });
  it('maps Cellar it', () => {
    expect(occasionMessage('Cellar it')).toBe('I am looking for something to cellar.');
  });
});

describe('deriveWineCardMeta', () => {
  it('sets tagline from region (uppercased)', () => {
    const meta = deriveWineCardMeta({ wine_id: '1', name: 'X', price: 20, retailer: "Spec's", why: 'good', region: 'Tuscany' });
    expect(meta.tagline).toBe('TUSCANY');
  });
  it('looks up coord from DISCOVERY_REGIONS', () => {
    const meta = deriveWineCardMeta({ wine_id: '1', name: 'X', price: 20, retailer: "Spec's", why: 'good', region: 'Tuscany' });
    expect(meta.coord).toBe('43.8°N · 11.2°E');
  });
  it('falls back tagline to varietal when no region', () => {
    const meta = deriveWineCardMeta({ wine_id: '1', name: 'X', price: 20, retailer: "Spec's", why: 'good', varietal: 'Malbec' });
    expect(meta.tagline).toBe('MALBEC');
  });
  it('falls back tagline to AVAILABLE NEAR YOU when no region or varietal', () => {
    const meta = deriveWineCardMeta({ wine_id: '1', name: 'X', price: 20, retailer: "Spec's", why: 'good' });
    expect(meta.tagline).toBe('AVAILABLE NEAR YOU');
  });
});

describe('buildApiReq', () => {
  it('unions tags from multiple styles', () => {
    const req = buildApiReq({ zip: '78209', budget: 50, styles: ['Bold & Tannic', 'Earthy & Savory'], occasion: 'Tonight' });
    expect(req.style_preferences).toContain('dark fruit');
    expect(req.style_preferences).toContain('earthy');
  });
  it('deduplicates overlapping tags', () => {
    const req = buildApiReq({ zip: '78209', budget: 50, styles: ['Bold & Tannic', 'Bold & Tannic'], occasion: 'Tonight' });
    expect(req.style_preferences.filter(t => t === 'dark fruit')).toHaveLength(1);
  });
  it('sets budget_max from prefs.budget, budget_min to 10', () => {
    const req = buildApiReq({ zip: '78209', budget: 75, styles: ['Bold & Tannic'], occasion: 'Tonight' });
    expect(req.budget_max).toBe(75);
    expect(req.budget_min).toBe(10);
  });
  it('falls back wine_types to style-derived type when no chips selected', () => {
    const req = buildApiReq({ zip: '78209', budget: 50, styles: ['Bold & Tannic'], occasion: 'Tonight', wineTypes: [] });
    expect(req.wine_types).toEqual(['red']);
  });
  it('wine_types is empty array when all styles are ambiguous and no chips selected', () => {
    const req = buildApiReq({ zip: '78209', budget: 50, styles: ['Earthy & Savory'], occasion: 'Tonight', wineTypes: [] });
    expect(req.wine_types).toEqual([]);
  });
  it('uses explicit wineTypes chips when provided', () => {
    const req = buildApiReq({ zip: '78209', budget: 50, styles: ['Bold & Tannic'], occasion: 'Tonight', wineTypes: ['white', 'sparkling'] });
    expect(req.wine_types).toEqual(['white', 'sparkling']);
  });
});
