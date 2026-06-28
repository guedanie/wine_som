import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RegionBrowse from '../RegionBrowse.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});
vi.mock('../../lib/api.js', () => ({ getRegionWines: vi.fn() }));
import { getRegionWines } from '../../lib/api.js';

const MOCK_RESP = {
  region: 'Tuscany',
  retailers: [
    {
      retailer: "Spec's",
      wines: [
        { wine_id: 'w1', name: 'Chianti Classico', varietal: 'Sangiovese', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 22, retailer: "Spec's",
          store_address: '123 Main', image_url: null, flavor_profile: ['dark cherry'], grapes: ['Sangiovese'] },
      ],
    },
  ],
};

const MOCK_MULTI = {
  region: 'Tuscany',
  retailers: [
    {
      retailer: "Spec's",
      wines: [
        { wine_id: 'w1', name: 'Chianti Classico', varietal: 'Sangiovese', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 22, retailer: "Spec's",
          store_address: null, image_url: null, flavor_profile: ['dark cherry'], grapes: [] },
        { wine_id: 'w2', name: 'Super Tuscan', varietal: 'Merlot', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 65, retailer: "Spec's",
          store_address: null, image_url: null, flavor_profile: ['dark fruit'], grapes: [] },
      ],
    },
    {
      retailer: 'H-E-B',
      wines: [
        { wine_id: 'w3', name: 'Morellino', varietal: 'Sangiovese', region: 'Tuscany',
          country: 'Italy', wine_type: 'red', price: 18, retailer: 'H-E-B',
          store_address: null, image_url: null, flavor_profile: ['cherry'], grapes: [] },
      ],
    },
  ],
};

function renderScreen(slug = 'Tuscany', state = {}) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: `/region/${slug}`, state }]}>
      <Routes>
        <Route path="/region/:slug" element={<RegionBrowse />} />
        <Route path="/discover" element={<div>Discover</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => { mockNavigate.mockClear(); getRegionWines.mockClear(); });

it('calls getRegionWines with decoded slug and default zip on mount', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(getRegionWines).toHaveBeenCalledWith('Tuscany', '78209'));
});

it('shows region name as heading', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Tuscany' })).toBeInTheDocument());
});

it('shows retailer section heading', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getAllByText(/spec's/i)[0]).toBeInTheDocument());
});

it('renders wine cards', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getByText('Chianti Classico')).toBeInTheDocument());
});

it('shows loading state while fetching', () => {
  getRegionWines.mockImplementation(() => new Promise(() => {}));
  renderScreen('Tuscany');
  expect(screen.getByText(/loading/i)).toBeInTheDocument();
});

it('shows error message on fetch failure', async () => {
  getRegionWines.mockRejectedValueOnce(new Error('No wines found near your zip code.'));
  renderScreen('Tuscany');
  await waitFor(() => expect(screen.getByText(/no wines found/i)).toBeInTheDocument());
});

it('navigates to /wine/:id when a wine card is clicked', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByText('Chianti Classico'));
  expect(mockNavigate).toHaveBeenCalledWith('/wine/w1', expect.objectContaining({
    state: expect.objectContaining({ pick: expect.objectContaining({ wine_id: 'w1' }) }),
  }));
});

it('re-fetches when zip input changes and Enter is pressed', async () => {
  getRegionWines.mockResolvedValue(MOCK_RESP);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  const zipInput = screen.getByDisplayValue('78209');
  await userEvent.clear(zipInput);
  await userEvent.type(zipInput, '78201{Enter}');
  await waitFor(() => expect(getRegionWines).toHaveBeenCalledWith('Tuscany', '78201'));
});

// Filter tests
it('shows grape filter chips derived from loaded wines', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  expect(screen.getByRole('button', { name: 'Sangiovese' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Merlot' })).toBeInTheDocument();
});

it('filters wines by selected grape', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByRole('button', { name: 'Merlot' }));
  expect(screen.queryByText('Chianti Classico')).not.toBeInTheDocument();
  expect(screen.queryByText('Morellino')).not.toBeInTheDocument();
  expect(screen.getByText('Super Tuscan')).toBeInTheDocument();
});

it('filters wines by retailer chip', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByRole('button', { name: 'H-E-B' }));
  expect(screen.getByText('Morellino')).toBeInTheDocument();
  expect(screen.queryByText('Chianti Classico')).not.toBeInTheDocument();
});

it('shows empty-state message when filters yield no results', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByRole('button', { name: 'Merlot' }));
  await userEvent.click(screen.getByRole('button', { name: 'H-E-B' }));
  expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /ask the sommelier/i })).toBeInTheDocument();
});

it('navigates to /recommend with region + filters when "Ask the sommelier" is clicked', async () => {
  getRegionWines.mockResolvedValueOnce(MOCK_MULTI);
  renderScreen('Tuscany');
  await waitFor(() => screen.getByText('Chianti Classico'));
  await userEvent.click(screen.getByRole('button', { name: 'Merlot' }));
  await userEvent.click(screen.getByRole('button', { name: 'H-E-B' }));
  await userEvent.click(screen.getByRole('button', { name: /ask the sommelier/i }));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', expect.objectContaining({
    state: expect.objectContaining({
      apiReq: expect.objectContaining({
        message: expect.stringContaining('Tuscany'),
      }),
    }),
  }));
});
