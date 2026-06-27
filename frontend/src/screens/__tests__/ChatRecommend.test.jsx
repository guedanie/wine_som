// frontend/src/screens/__tests__/ChatRecommend.test.jsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ChatRecommend from '../ChatRecommend.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../lib/api.js', () => ({ streamRecommend: vi.fn() }));
import { streamRecommend } from '../../lib/api.js';

const prefs  = { zip: '78209', budget: 60, styles: ['Bold & Tannic'], occasion: 'Tonight' };
const apiReq = { zip_code: '78209', budget_min: 10, budget_max: 60, style_preferences: ['dark fruit'], wine_type: 'red', message: 'I want something to open tonight.' };

function renderScreen(state = { prefs, apiReq }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/recommend', state }]}>
      <Routes>
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => { mockNavigate.mockClear(); streamRecommend.mockClear(); });

it('redirects to / when there is no prefs state', () => {
  render(
    <MemoryRouter initialEntries={['/recommend']}>
      <Routes>
        <Route path="/recommend" element={<ChatRecommend />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
  expect(screen.getByText('Home')).toBeInTheDocument();
});

it('shows loading bubble while streamRecommend is pending', () => {
  streamRecommend.mockImplementation(async function* () {
    await new Promise(() => {}); // never resolves
  });
  renderScreen();
  expect(screen.getByText(/finding/i)).toBeInTheDocument();
});

it('shows error message when streamRecommend throws', async () => {
  streamRecommend.mockImplementation(async function* () {
    throw new Error('No stores found near your zip code.');
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText(/no stores found/i)).toBeInTheDocument());
});

it('shows narrative and wine cards when streamRecommend succeeds', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are three wines for you.' };
    yield {
      type: 'picks',
      picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }],
      session_id: 'sess-1',
    };
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Here are three wines for you.')).toBeInTheDocument());
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});

it('navigates to /wine/:id with pick state when a WineCard is clicked', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are three wines for you.' };
    yield {
      type: 'picks',
      picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }],
      session_id: 'sess-1',
    };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  await userEvent.click(screen.getByText('Esprit de Tablas'));
  expect(mockNavigate).toHaveBeenCalledWith('/wine/uuid-1', expect.objectContaining({
    state: expect.objectContaining({ pick: expect.objectContaining({ wine_id: 'uuid-1' }) }),
  }));
});

it('does not call streamRecommend when _restored state is provided', async () => {
  const restoredMessages = [
    { role: 'user', text: 'bold · under $60 · tonight' },
    { role: 'sommelier', text: 'Here are my top picks.' },
  ];
  const restoredPicks = [
    { wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's",
      why: 'Great.', tagline: 'PASO ROBLES', coord: null, flavors: [] },
  ];
  renderScreen({
    prefs,
    apiReq,
    _restored: { messages: restoredMessages, picks: restoredPicks },
  });
  await new Promise(r => setTimeout(r, 50));
  expect(streamRecommend).not.toHaveBeenCalled();
  expect(screen.getByText('Here are my top picks.')).toBeInTheDocument();
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});
