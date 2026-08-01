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
