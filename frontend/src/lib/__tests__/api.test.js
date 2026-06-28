import { streamRecommend, getWine } from '../api.js';

beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
afterEach(() => { vi.unstubAllGlobals(); });

function makeSseResponse(events) {
  const lines = events.map(e => `data: ${JSON.stringify(e)}`).join('\n\n') + '\n\ndata: [DONE]\n\n';
  const bytes = new TextEncoder().encode(lines);
  const reader = {
    read: vi.fn()
      .mockResolvedValueOnce({ done: false, value: bytes })
      .mockResolvedValueOnce({ done: true, value: undefined }),
  };
  return { ok: true, body: { getReader: () => reader } };
}

describe('streamRecommend', () => {
  it('POSTs to /api/recommend with the request body', async () => {
    const req = { zip_code: '78209', budget_min: 10, budget_max: 60 };
    fetch.mockResolvedValueOnce(makeSseResponse([{ type: 'token', text: 'Hi.' }]));
    const gen = streamRecommend(req);
    await gen.next();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/recommend'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify(req) })
    );
  });

  it('yields token and picks events from SSE', async () => {
    const tokenEvent = { type: 'token', text: 'Good picks.' };
    const picksEvent = { type: 'picks', picks: [], session_id: 'abc' };
    fetch.mockResolvedValueOnce(makeSseResponse([tokenEvent, picksEvent]));
    const events = [];
    for await (const e of streamRecommend({})) {
      events.push(e);
    }
    expect(events[0]).toEqual(tokenEvent);
    expect(events[1]).toEqual(picksEvent);
  });

  it('throws with API detail message on non-ok response', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'No stores found near your zip code.' }),
    });
    await expect(async () => {
      for await (const _ of streamRecommend({})) { /* drain */ }
    }).rejects.toThrow('No stores found near your zip code.');
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

describe('getRegionWines', () => {
  it('GETs /api/region/:name with zip query param', async () => {
    const mockResp = { region: 'Tuscany', retailers: [] };
    fetch.mockResolvedValueOnce({ ok: true, json: async () => mockResp });
    const { getRegionWines } = await import('../api.js');
    await getRegionWines('Tuscany', '78209');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/region\/Tuscany\?zip=78209/)
    );
  });

  it('throws on non-ok response', async () => {
    fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Not found' }) });
    const { getRegionWines } = await import('../api.js');
    await expect(getRegionWines('Tuscany', '78209')).rejects.toThrow('Not found');
  });

  it('URL-encodes region names with spaces', async () => {
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ region: 'Napa Valley', retailers: [] }) });
    const { getRegionWines } = await import('../api.js');
    await getRegionWines('Napa Valley', '78209');
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/Napa%20Valley/));
  });
});
