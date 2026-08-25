import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});
vi.mock('../../lib/api.js', () => ({ getSubregionCounts: vi.fn() }));
// Leaflet touches the real DOM APIs jsdom lacks — stub the map component.
vi.mock('../../components/RegionMap.jsx', () => ({
  default: () => <div data-testid="region-map" />,
}));

import RegionDetail from '../RegionDetail.jsx';
import { getSubregionCounts } from '../../lib/api.js';
import { saveZip } from '../../lib/useIsMobile.js';

function renderScreen(slug = 'tuscany') {
  return render(
    <MemoryRouter initialEntries={[`/regions/${slug}`]}>
      <Routes>
        <Route path="/regions/:slug" element={<RegionDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

// These specs were written against a hardcoded '78209' default; they test the
// behaviour WITH a known zip, so seed one explicitly now that none is fabricated.
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  saveZip('78209');
  getSubregionCounts.mockResolvedValue({ region: 'Tuscany', counts: {} });
});

test('renders region name, country, and facts grid', async () => {
  renderScreen('tuscany');
  expect(screen.getByRole('heading', { name: 'Tuscany' })).toBeInTheDocument();
  expect(screen.getByText('Warm Mediterranean')).toBeInTheDocument();
  expect(screen.getByText('Galestro & Alberese')).toBeInTheDocument();
  expect(screen.getByText('250 – 600 m')).toBeInTheDocument();
});

test('renders principal varietal chips', () => {
  renderScreen('tuscany');
  expect(screen.getByText('Sangiovese')).toBeInTheDocument();
  expect(screen.getByText('Canaiolo')).toBeInTheDocument();
});

test('renders sub-regions with live wine counts', async () => {
  getSubregionCounts.mockResolvedValue({
    region: 'Tuscany',
    counts: { 'Chianti Classico': 24, 'Brunello di Montalcino': 18 },
  });
  renderScreen('tuscany');
  expect(screen.getByText('Chianti Classico')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('24 nearby')).toBeInTheDocument());
  // "Montalcino" (curated) matches "Brunello di Montalcino" (DB) by containment
  expect(screen.getByText('18 nearby')).toBeInTheDocument();
});

// ---- nullable zip: no location known ----

test('labels counts "in the catalog", not "nearby", when no zip is known', async () => {
  localStorage.clear();
  getSubregionCounts.mockResolvedValue({
    region: 'Tuscany',
    counts: { 'Chianti Classico': 412 },
  });
  renderScreen('tuscany');
  // Without a zip the endpoint counts catalog-wide — calling that "nearby" is a
  // claim we never computed, and a bare integer is unfalsifiable from the UI.
  await waitFor(() => expect(screen.getByText('412 in the catalog')).toBeInTheDocument());
  expect(screen.queryByText(/nearby/i)).not.toBeInTheDocument();
});

test('renders the map', () => {
  renderScreen('tuscany');
  expect(screen.getByTestId('region-map')).toBeInTheDocument();
});

test('CTA navigates to region browse', async () => {
  renderScreen('tuscany');
  await userEvent.click(screen.getByRole('button', { name: /Explore wines from Tuscany/ }));
  expect(mockNavigate).toHaveBeenCalledWith('/region/Tuscany');
});

test('clicking a sub-region deep-links to search pre-filled with it', async () => {
  renderScreen('tuscany');
  const rows = await screen.findAllByRole('link');
  const chianti = rows.find(r => /Chianti Classico/.test(r.textContent));
  expect(chianti).toBeTruthy();
  await userEvent.click(chianti);
  expect(mockNavigate).toHaveBeenCalledWith('/search?q=Chianti%20Classico');
});

test('unknown slug shows not-found message', () => {
  renderScreen('atlantis');
  expect(screen.getByText(/Region not found/)).toBeInTheDocument();
});

test('accented region resolves via slug', () => {
  renderScreen('rhone-valley');
  expect(screen.getByRole('heading', { name: 'Rhône Valley' })).toBeInTheDocument();
});
