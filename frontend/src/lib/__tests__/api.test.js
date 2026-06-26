import { recommend, getWine } from '../api.js';

beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
afterEach(() => { vi.unstubAllGlobals(); });

describe('recommend', () => {
  it('POSTs to /api/recommend with the request body', async () => {
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ narrative: 'Good picks.', picks: [], session_id: 'abc' }),
    });
    const req = { zip_code: '78209', budget_min: 10, budget_max: 60, style_preferences: ['dark fruit'], wine_type: 'red', message: 'Tonight.' };
    await recommend(req);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/recommend'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify(req) })
    );
  });

  it('returns parsed JSON on success', async () => {
    const payload = { narrative: 'Good picks.', picks: [], session_id: 'abc' };
    fetch.mockResolvedValueOnce({ ok: true, json: async () => payload });
    await expect(recommend({})).resolves.toEqual(payload);
  });

  it('throws with API detail message on non-ok response', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'No stores found near your zip code.' }),
    });
    await expect(recommend({})).rejects.toThrow('No stores found near your zip code.');
  });
});

describe('getWine', () => {
  it('GETs /api/wines/:id', async () => {
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ id: '1', name: 'Test' }) });
    await getWine('abc-123');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/wines/abc-123'));
  });

  it('throws on non-ok response', async () => {
    fetch.mockResolvedValueOnce({ ok: false });
    await expect(getWine('bad-id')).rejects.toThrow('HTTP');
  });
});
