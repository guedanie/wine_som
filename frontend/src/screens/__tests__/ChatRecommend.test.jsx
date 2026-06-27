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

vi.mock('../../lib/api.js', () => ({ recommend: vi.fn() }));
import { recommend } from '../../lib/api.js';

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

beforeEach(() => { mockNavigate.mockClear(); recommend.mockClear(); });

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

it('shows loading bubble while recommend is pending', () => {
  recommend.mockReturnValue(new Promise(() => {}));
  renderScreen();
  expect(screen.getByText(/finding/i)).toBeInTheDocument();
});

it('shows error message when recommend fails', async () => {
  recommend.mockRejectedValue(new Error('No stores found near your zip code.'));
  renderScreen();
  await waitFor(() => expect(screen.getByText(/no stores found/i)).toBeInTheDocument());
});

it('shows narrative and wine cards when recommend succeeds', async () => {
  recommend.mockResolvedValue({
    narrative: 'Here are three wines for you.',
    picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }],
    session_id: 'sess-1',
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Here are three wines for you.')).toBeInTheDocument());
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});

it('navigates to /wine/:id with pick state when a WineCard is clicked', async () => {
  recommend.mockResolvedValue({
    narrative: 'Here are three wines for you.',
    picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }],
    session_id: 'sess-1',
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  await userEvent.click(screen.getByText('Esprit de Tablas'));
  expect(mockNavigate).toHaveBeenCalledWith('/wine/uuid-1', expect.objectContaining({
    state: expect.objectContaining({ pick: expect.objectContaining({ wine_id: 'uuid-1' }) }),
  }));
});

it('does not call recommend when _restored state is provided', async () => {
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
  // API should never be called — state is restored
  await new Promise(r => setTimeout(r, 50));
  expect(recommend).not.toHaveBeenCalled();
  expect(screen.getByText('Here are my top picks.')).toBeInTheDocument();
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});
