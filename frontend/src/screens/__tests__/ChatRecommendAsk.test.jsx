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
