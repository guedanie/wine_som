import { vi } from 'vitest';

vi.mock('../favorites.js', () => ({ listFavorites: vi.fn() }));
vi.mock('../cellar.js', () => ({ listCellar: vi.fn() }));

import { buildTasteContext } from '../taste.js';
import { listFavorites } from '../favorites.js';
import { listCellar } from '../cellar.js';

test('gathers saved + cellar into liked_wines with source tags', async () => {
  listFavorites.mockResolvedValue([
    { wine_id: 'w1', wines: { id: 'w1', name: 'Esprit de Tablas', varietal: 'Grenache', region: 'Paso Robles', grapes: ['Grenache'] } },
  ]);
  listCellar.mockResolvedValue([{ wine_id: 'w2', name: 'Barolo', region: 'Piedmont' }]);
  const t = await buildTasteContext('u1');
  expect(t.liked_wines).toHaveLength(2);
  expect(t.liked_wines.find(l => l.name === 'Esprit de Tablas')).toMatchObject({ source: 'saved', varietal: 'Grenache' });
  expect(t.liked_wines.find(l => l.name === 'Barolo').source).toBe('cellar');
});

test('dedups by wine id (saved + owned same wine)', async () => {
  listFavorites.mockResolvedValue([{ wine_id: 'w1', wines: { id: 'w1', name: 'X' } }]);
  listCellar.mockResolvedValue([{ wine_id: 'w1', name: 'X' }]);
  const t = await buildTasteContext('u1');
  expect(t.liked_wines).toHaveLength(1);
});

test('null userId → null', async () => {
  expect(await buildTasteContext(null)).toBeNull();
});

test('nothing saved/owned → null', async () => {
  listFavorites.mockResolvedValue([]);
  listCellar.mockResolvedValue([]);
  expect(await buildTasteContext('u1')).toBeNull();
});
