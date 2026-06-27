import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RegionDossier from '../RegionDossier.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../lib/api.js', () => ({ getWine: vi.fn() }));
import { getWine } from '../../lib/api.js';

const pick = {
  wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's",
  why: 'Great structure.', region: 'Paso Robles',
  tagline: 'PASO ROBLES', coord: '35.6°N · 120.7°W',
  store_address: '1000 Austin Hwy, San Antonio, TX 78209',
};

const wineDetail = {
  id: 'uuid-1', name: 'Esprit de Tablas', brand: 'Tablas Creek',
  varietal: 'GSM Blend', region: 'Paso Robles', vintage_year: 2021,
  wine_details: {
    description: 'A classic Paso Robles blend of Grenache, Syrah and Mourvèdre.',
    tasting_notes: 'Dark cherry, garrigue and leather.',
    flavor_profile: ['dark cherry', 'garrigue', 'leather'],
    structure_profile: { body: 8, tannins: 7, acidity: 5, finish: 8 },
    grapeminds_enriched_at: '2026-01-01',
  },
};

function renderScreen(id = 'uuid-1', state = { pick }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: `/wine/${id}`, state }]}>
      <Routes><Route path="/wine/:id" element={<RegionDossier />} /></Routes>
    </MemoryRouter>
  );
}

beforeEach(() => { getWine.mockClear(); mockNavigate.mockClear(); });

it('shows pick name immediately from router state before API resolves', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});

it('shows pick price immediately', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  expect(screen.getByText('$55')).toBeInTheDocument();
});

it('shows tasting notes after getWine resolves', async () => {
  getWine.mockResolvedValue(wineDetail);
  renderScreen();
  await waitFor(() => expect(screen.getByText('Dark cherry, garrigue and leather.')).toBeInTheDocument());
});

it('shows Structure section after getWine resolves', async () => {
  getWine.mockResolvedValue(wineDetail);
  renderScreen();
  await waitFor(() => expect(screen.getByText('Structure')).toBeInTheDocument());
});

it('shows flavor tags after getWine resolves', async () => {
  getWine.mockResolvedValue(wineDetail);
  renderScreen();
  await waitFor(() => expect(screen.getByText('dark cherry')).toBeInTheDocument());
});

it('shows wine description after getWine resolves', async () => {
  getWine.mockResolvedValue(wineDetail);
  renderScreen();
  await waitFor(() =>
    expect(screen.getByText('A classic Paso Robles blend of Grenache, Syrah and Mourvèdre.')).toBeInTheDocument()
  );
});

it('shows store address in the availability section', async () => {
  getWine.mockResolvedValue(wineDetail);
  renderScreen();
  await waitFor(() => screen.getByText('Structure'));
  expect(screen.getByText('1000 Austin Hwy, San Antonio, TX 78209')).toBeInTheDocument();
});

it('back button calls navigate(-1) when no chatState', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  fireEvent.click(screen.getByText(/← back/i));
  expect(mockNavigate).toHaveBeenCalledWith(-1);
});

it('back button navigates to /recommend with _restored when chatState is present', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  const chatState = {
    messages: [{ role: 'user', text: 'bold' }],
    picks: [],
    prefs: { zip: '78209', budget: 60, styles: [], occasion: 'Tonight', wineTypes: [], grapes: [] },
    apiReq: { zip_code: '78209', budget_min: 10, budget_max: 60, style_preferences: [] },
  };
  renderScreen('uuid-1', { pick, chatState });
  fireEvent.click(screen.getByText(/← back/i));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', {
    state: expect.objectContaining({ _restored: chatState }),
  });
});
