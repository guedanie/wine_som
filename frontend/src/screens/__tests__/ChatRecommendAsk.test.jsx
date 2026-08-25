// frontend/src/screens/__tests__/ChatRecommendAsk.test.jsx
// The Ask face (aisle mode): empty state, intent pills, wide-budget sends,
// lazy zip, store picker, comparison frame, closer, failure states.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ChatRecommend from '../ChatRecommend.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});
vi.mock('../../lib/api.js', () => ({
  streamRecommend: vi.fn(), postFeedback: vi.fn(), getNearbyStores: vi.fn(),
}));
import { streamRecommend } from '../../lib/api.js';

function renderAsk(state = { mode: 'ask' }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/recommend', state }]}>
      <Routes>
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
}

// jsdom's opaque origin makes localStorage null — in-memory stub (repo pattern).
const _store = {};
beforeEach(() => {
  mockNavigate.mockClear();
  streamRecommend.mockClear();
  for (const k in _store) delete _store[k];
  vi.stubGlobal('localStorage', {
    getItem: k => (k in _store ? _store[k] : null),
    setItem: (k, v) => { _store[k] = String(v); },
    removeItem: k => { delete _store[k]; },
  });
  localStorage.setItem('somm_zip', '78209');   // stored zip: lazy-zip flow stays out of these tests
});
afterEach(() => vi.unstubAllGlobals());

it('renders the ask empty state instead of redirecting or auto-firing', async () => {
  renderAsk();
  expect(screen.getByText('What can I help you with?')).toBeInTheDocument();
  expect(screen.getByText('Compare two')).toBeInTheDocument();
  await new Promise(r => setTimeout(r, 30));
  expect(streamRecommend).not.toHaveBeenCalled();
});

it('arriving at /recommend with no state at all is the ask face too', () => {
  render(
    <MemoryRouter initialEntries={['/recommend']}>
      <Routes>
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
  expect(screen.getByText('What can I help you with?')).toBeInTheDocument();
  expect(screen.queryByText('Home')).toBeNull();
});

it('an intent pill fills the composer', async () => {
  renderAsk();
  await userEvent.click(screen.getByText('Compare two'));
  expect(screen.getAllByRole('textbox')[0].value).toBe('Which is better: ');
});

it('sending asks with the wide-budget sentinel and stored zip', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Both are solid.' };
  });
  renderAsk();
  const input = screen.getAllByRole('textbox')[0];
  await userEvent.type(input, 'caymus or bonanza?{Enter}');
  await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(1));
  expect(streamRecommend.mock.calls[0][0]).toMatchObject({
    zip_code: '78209', budget_min: 0, budget_max: 10000, message: 'caymus or bonanza?',
  });
  await screen.findByText('Both are solid.');
});

describe('lazy zip', () => {
  beforeEach(() => localStorage.removeItem('somm_zip'));

  it('holds the question and asks for zip when none is stored', async () => {
    renderAsk();
    const input = screen.getAllByRole('textbox')[0];
    await userEvent.type(input, 'a good red for tonight{Enter}');
    expect(streamRecommend).not.toHaveBeenCalled();
    expect(screen.getByText(/tell me roughly where you are/)).toBeInTheDocument();
    expect(screen.getByText(/Asked once — I'll remember it/)).toBeInTheDocument();
  });

  it('Set saves the zip and fires the held question', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'Here you go.' };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a good red{Enter}');
    await userEvent.type(screen.getByLabelText('Your zip'), '78230');
    await userEvent.click(screen.getByText('Set'));
    await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(1));
    expect(streamRecommend.mock.calls[0][0]).toMatchObject({ zip_code: '78230', message: 'a good red' });
    expect(localStorage.getItem('somm_zip')).toBe('78230');
  });
});

describe('store picker', () => {
  it('opens from openStorePicker state, lists stores, selection scopes requests', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '78209', stores: [
      { id: 's1', retailer_name: 'H-E-B', name: 'H-E-B Lincoln Heights', address: 'x', distance_miles: 0.8 },
      { id: 's2', retailer_name: "Spec's", name: "Spec's Broadway", address: 'y', distance_miles: 2.1 },
    ] });
    streamRecommend.mockImplementation(async function* () { yield { type: 'token', text: 'ok' }; });
    renderAsk({ mode: 'ask', openStorePicker: true });
    expect(await screen.findByText(/Which one are you standing in/)).toBeInTheDocument();
    await screen.findByText('H-E-B Lincoln Heights');
    expect(screen.getByText('closest')).toBeInTheDocument();
    await userEvent.click(screen.getByText('H-E-B Lincoln Heights'));
    // picker closes, pill shows
    expect(screen.queryByText(/Which one are you standing in/)).toBeNull();
    expect(screen.getByText(/H-E-B Lincoln Heights · change/)).toBeInTheDocument();
    // requests now carry store_ref
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a bold red{Enter}');
    await waitFor(() => expect(streamRecommend).toHaveBeenCalled());
    expect(streamRecommend.mock.calls[0][0]).toMatchObject({ store_ref: 's1' });
  });

  it('asks for a zip BEFORE opening the store picker when none is stored', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '37210', stores: [
      { id: 's1', retailer_name: 'Kroger', name: 'Kroger Nashville', address: 'x', distance_miles: 0.9 },
    ] });
    getNearbyStores.mockClear();   // shared mock: earlier tests in this file call it
    localStorage.removeItem('somm_zip');
    renderAsk({ mode: 'ask', openStorePicker: true });
    expect(await screen.findByText(/tell me roughly where you are/)).toBeInTheDocument();
    expect(screen.queryByText(/Which one are you standing in/)).toBeNull();
    expect(getNearbyStores).not.toHaveBeenCalled();
  });

  it('does not re-ask for a zip after a store has been picked', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '37210', stores: [
      { id: 's1', retailer_name: 'Kroger', name: 'Kroger Nashville', address: 'x', distance_miles: 0.9 },
    ] });
    streamRecommend.mockImplementation(async function* () { yield { type: 'token', text: 'ok' }; });
    getNearbyStores.mockClear();
    localStorage.removeItem('somm_zip');
    renderAsk({ mode: 'ask', openStorePicker: true });
    await userEvent.type(await screen.findByLabelText('Your zip'), '37210');
    await userEvent.click(screen.getByText('Set'));
    // the picker opens with the zip we just learned — and uses it
    await userEvent.click(await screen.findByText('Kroger Nashville'));
    expect(getNearbyStores).toHaveBeenCalledWith('37210');
    expect(streamRecommend).not.toHaveBeenCalled();   // nothing was queued to send
    await userEvent.type(screen.getAllByRole('textbox')[0], 'something bold{Enter}');
    await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/tell me roughly where you are/)).toBeNull();
    expect(streamRecommend.mock.calls[0][0]).toMatchObject({ zip_code: '37210', store_ref: 's1' });
  });

  it('the escape hatch clears the store', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '78209', stores: [
      { id: 's1', retailer_name: 'H-E-B', name: 'H-E-B Lincoln Heights', address: 'x', distance_miles: 0.8 },
    ] });
    renderAsk({ mode: 'ask', openStorePicker: true });
    await screen.findByText('H-E-B Lincoln Heights');
    await userEvent.click(screen.getByText(/Somewhere else — just use my zip/));
    expect(screen.queryByText(/H-E-B Lincoln Heights · change/)).toBeNull();
  });
});

it('renders the comparison frame when the picks event carries comparison', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Caymus, if I am honest.' };
    yield { type: 'picks', comparison: ['Caymus', 'Bonanza'], picks: [
      { wine_id: 'a', name: 'Caymus Cabernet', price: 89, retailer: 'H-E-B', why: 'Plush.', structure_profile: { body: 10, tannins: 8 } },
      { wine_id: 'b', name: 'Bonanza Cabernet', price: 21, retailer: 'H-E-B', why: 'Value.', structure_profile: { body: 9, tannins: 5 } },
    ], session_id: 's' };
  });
  renderAsk();
  await userEvent.type(screen.getAllByRole('textbox')[0], 'caymus or bonanza?{Enter}');
  await screen.findByText('MINE');
  // price renders in the frame's PRICE row AND the pick message below it
  expect(screen.getAllByText('$89')).toHaveLength(2);
  window.matchMedia = undefined;
});

describe('no-card closer', () => {
  it('offers to find a bottle after a no-pick answer; Yes re-asks', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'Nebbiolo is lighter in color but grippier.' };
      yield { type: 'picks', picks: [] };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'is nebbiolo like pinot?{Enter}');
    expect(await screen.findByText('Want me to find you a good one here?')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Yes, find one'));
    await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(2));
    expect(streamRecommend.mock.calls[1][0].message).toMatch(/find me a good one/);
  });

  it('no offer when picks arrived', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'One pick.' };
      yield { type: 'picks', picks: [{ wine_id: 'a', name: 'Caymus', price: 89, retailer: 'H-E-B', why: 'x' }], session_id: 's' };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a bold red{Enter}');
    await screen.findByText('Caymus');
    expect(screen.queryByText('Want me to find you a good one here?')).toBeNull();
  });
});

describe('failure states', () => {
  it('dropped request: somm apology + Ask again resends the same request', async () => {
    streamRecommend
      .mockImplementationOnce(async function* () { throw new Error('network'); })
      .mockImplementationOnce(async function* () { yield { type: 'token', text: 'Back with you.' }; });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a good red{Enter}');
    expect(await screen.findByText(/Lost you for a second/)).toBeInTheDocument();
    expect(screen.getByText('a good red')).toBeInTheDocument();      // question preserved
    await userEvent.click(screen.getByText('Ask again'));
    await screen.findByText('Back with you.');
    expect(streamRecommend.mock.calls[1][0].message).toBe('a good red');
  });

  it('half-arrived answer keeps what arrived and offers Finish the answer', async () => {
    streamRecommend.mockImplementationOnce(async function* () {
      yield { type: 'token', text: 'The Caymus is plush and' };
      throw new Error('network');
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'caymus?{Enter}');
    expect(await screen.findByText(/Lost you for a second/)).toBeInTheDocument();
    expect(screen.getByText(/The Caymus is plush and/)).toBeInTheDocument();  // partial stays
    expect(screen.getByText('Finish the answer')).toBeInTheDocument();
  });
});

it('follow-up history carries the prior picks (item 41 — referent carry)', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Two I like.' };
    yield { type: 'picks', picks: [
      { wine_id: 'w1', name: 'Avaline Sauvignon Blanc', price: 22, retailer: 'Kroger', why: 'Crisp.' },
      { wine_id: 'w2', name: 'Starborough Sauvignon Blanc', price: 13, retailer: 'Kroger', why: 'Value.' },
    ], session_id: 's' };
  });
  renderAsk();
  await userEvent.type(screen.getAllByRole('textbox')[0], 'a sancerre-style sauvignon blanc?{Enter}');
  await screen.findByText('Avaline Sauvignon Blanc');
  await userEvent.type(screen.getAllByRole('textbox')[0], 'compare these two?{Enter}');
  await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(2));
  const history = streamRecommend.mock.calls[1][0].conversation_history;
  const sommTurn = history.find(t => t.role === 'sommelier');
  expect(sommTurn.picks).toEqual([
    { wine_id: 'w1', name: 'Avaline Sauvignon Blanc' },
    { wine_id: 'w2', name: 'Starborough Sauvignon Blanc' },
  ]);
});

describe('hard store filter — check nearby (item 44)', () => {
  it('offers Check nearby stores on a store-scoped answer and widens on tap', async () => {
    const { getNearbyStores } = await import('../../lib/api.js');
    getNearbyStores.mockResolvedValue({ zip: '78209', stores: [
      { id: 's1', retailer_name: "Geraldine's", name: "Geraldine's Natural Wines", address: 'x', distance_miles: 0 },
    ] });
    streamRecommend
      .mockImplementationOnce(async function* () {
        yield { type: 'token', text: "Here's the best on Geraldine's shelves." };
        yield { type: 'picks', picks: [{ wine_id: 'w1', name: 'COS Cerasuolo', price: 30, retailer: "Geraldine's", why: 'In store.' }], session_id: 's' };
      })
      .mockImplementationOnce(async function* () {
        yield { type: 'token', text: 'Looking wider.' };
        yield { type: 'picks', picks: [{ wine_id: 'w2', name: 'Torbreck Shiraz', price: 40, retailer: 'Twin Liquors', why: 'Nearby.' }], session_id: 's2' };
      });
    renderAsk({ mode: 'ask', openStorePicker: true });
    await screen.findByText("Geraldine's Natural Wines");
    await userEvent.click(screen.getByText("Geraldine's Natural Wines"));   // pick the store
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a red for pizza{Enter}');
    await screen.findByText('COS Cerasuolo');
    expect(streamRecommend.mock.calls[0][0].store_ref).toBe('s1');          // scoped
    await userEvent.click(screen.getByText('Check nearby stores'));
    await screen.findByText('Torbreck Shiraz');
    const widened = streamRecommend.mock.calls[1][0];
    expect(widened.store_ref).toBeUndefined();                              // widened
    expect(widened.message).toBe('a red for pizza');
  });

  it('does not show Check nearby stores when no store is picked', async () => {
    streamRecommend.mockImplementation(async function* () {
      yield { type: 'token', text: 'Ok.' };
      yield { type: 'picks', picks: [{ wine_id: 'w1', name: 'Some Red', price: 20, retailer: 'H-E-B', why: 'x' }], session_id: 's' };
    });
    renderAsk();
    await userEvent.type(screen.getAllByRole('textbox')[0], 'a red for pizza{Enter}');
    await screen.findByText('Some Red');
    expect(screen.queryByText('Check nearby stores')).toBeNull();
  });
});
