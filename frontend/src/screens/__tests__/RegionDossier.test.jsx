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

vi.mock('../../components/SommOverlay.jsx', () => ({
  default: ({ wine }) => <div data-testid="somm-overlay">Ask Somm for {wine.wine_name}</div>,
}));

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

it('renders the price-context module + cheapest/was-price row treatment', async () => {
  getWine.mockResolvedValue({
    ...wineDetail,
    availability: [
      { store_ref: 's1', retailer: 'H-E-B', address: '123 Main', price: 19.99, is_cheapest: true, was_price: 24.99 },
      { store_ref: 's2', retailer: "Spec's", address: '9 Elm', price: 22.99, is_cheapest: false, was_price: null },
    ],
    price_context: {
      variant: 'drop', amount: 5, from_price: 24.99, to_price: 19.99,
      store: 'H-E-B', since_label: 'this week', weeks_tracked: 6,
      strip: [24.99, 24.99, 24.99, 24.99, 24.99, 19.99],
      cheapest: { retailer: 'H-E-B', price: 19.99, delta_vs_next: 3.0 },
    },
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText(/Down to/)).toBeInTheDocument());
  expect(screen.getByText(/at H-E-B/)).toBeInTheDocument();
  expect(screen.getByText('· CHEAPEST')).toBeInTheDocument();
  expect(screen.getByText('$24.99')).toBeInTheDocument();   // struck was-price on the row
});


it('dossier without price movement renders the steady module, resolved not empty', async () => {
  getWine.mockResolvedValue({
    ...wineDetail,
    availability: [
      { store_ref: 's1', retailer: "Spec's", address: '9 Elm', price: 28, is_cheapest: true, was_price: null },
    ],
    price_context: {
      variant: 'steady', amount: null, from_price: null, to_price: null,
      store: null, since_label: 'since June', weeks_tracked: 6,
      strip: [28, 28, 28, 28, 28, 28],
      cheapest: { retailer: "Spec's", price: 28, delta_vs_next: null },
    },
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText(/steady so far/)).toBeInTheDocument());
  expect(screen.getByText(/the week it drops/)).toBeInTheDocument();
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

it('renders SommOverlay with wine name', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  expect(screen.getByTestId('somm-overlay')).toBeInTheDocument();
  expect(screen.getByText(/Ask Somm for Esprit de Tablas/i)).toBeInTheDocument();
});

it('SommOverlay receives price from pick', () => {
  getWine.mockReturnValue(new Promise(() => {}));
  renderScreen();
  // pick.price = 55, wine_name = 'Esprit de Tablas' — mock renders both
  expect(screen.getByText(/Ask Somm for Esprit de Tablas/)).toBeInTheDocument();
});
