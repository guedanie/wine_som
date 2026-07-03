import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});
vi.mock('../../lib/api.js', () => ({ searchWines: vi.fn() }));

import SearchScreen from '../SearchScreen.jsx';
import { searchWines } from '../../lib/api.js';

const MOCK_RESULTS = {
  query: 'tuscany',
  wines: [
    { wine_id: 'w1', name: 'Brunello di Montalcino', brand: 'Altesino',
      vintage_year: 2018, varietal: 'Sangiovese', region: 'Tuscany', country: 'Italy',
      wine_type: 'red', price: 72, retailer: "Spec's", distance_miles: 4.2,
      image_url: null, vivino_rating: 4.3, vivino_ratings_count: 12000 },
    { wine_id: 'w2', name: 'Vermentino Bianco', brand: 'Fattoria X',
      vintage_year: 2022, varietal: 'Vermentino', region: 'Tuscany', country: 'Italy',
      wine_type: 'white', price: 19, retailer: 'H-E-B', distance_miles: 2.1,
      image_url: null, vivino_rating: null, vivino_ratings_count: null },
  ],
};

function renderScreen(initial = '/search') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/search" element={<SearchScreen />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  searchWines.mockResolvedValue(MOCK_RESULTS);
});

test('submitting a query calls the search API and lists wines', async () => {
  renderScreen();
  await userEvent.type(screen.getByLabelText('Search wines and regions'), 'tuscany');
  await userEvent.click(screen.getByLabelText('Submit search'));
  await waitFor(() => expect(screen.getByText('Brunello di Montalcino')).toBeInTheDocument());
  expect(searchWines).toHaveBeenCalledWith(expect.objectContaining({ q: 'tuscany' }));
  expect(screen.getByText(/2 wines for/)).toBeInTheDocument();
  expect(screen.getByText('$72')).toBeInTheDocument();
  expect(screen.getByText(/Spec's · 4.2 mi/)).toBeInTheDocument();
});

test('query from URL runs on mount', async () => {
  renderScreen('/search?q=tuscany');
  await waitFor(() => expect(searchWines).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByText('Brunello di Montalcino')).toBeInTheDocument());
});

test('style chip filters by wine type client-side', async () => {
  renderScreen('/search?q=tuscany');
  await waitFor(() => expect(screen.getByText('Vermentino Bianco')).toBeInTheDocument());
  await userEvent.click(screen.getByRole('button', { name: 'Bold & Tannic' }));
  expect(screen.getByText('Brunello di Montalcino')).toBeInTheDocument();
  expect(screen.queryByText('Vermentino Bianco')).not.toBeInTheDocument();
});

test('places section lists matching region with explore link', async () => {
  renderScreen('/search?q=tuscany');
  await waitFor(() => expect(screen.getByText('Places')).toBeInTheDocument());
  expect(screen.getByText('Tuscany')).toBeInTheDocument();
  await userEvent.click(screen.getByText('Explore →'));
  expect(mockNavigate).toHaveBeenCalledWith('/regions/tuscany');
});

test('wine row click navigates to dossier with pick state', async () => {
  renderScreen('/search?q=tuscany');
  await waitFor(() => expect(screen.getByText('Brunello di Montalcino')).toBeInTheDocument());
  await userEvent.click(screen.getByText('Brunello di Montalcino'));
  expect(mockNavigate).toHaveBeenCalledWith('/wine/w1', expect.objectContaining({
    state: expect.objectContaining({
      pick: expect.objectContaining({ name: 'Brunello di Montalcino', price: 72 }),
    }),
  }));
});

test('empty results show a friendly message', async () => {
  searchWines.mockResolvedValue({ query: 'zzz', wines: [] });
  renderScreen('/search?q=zzz');
  await waitFor(() => expect(screen.getByText(/Nothing found/)).toBeInTheDocument());
});
