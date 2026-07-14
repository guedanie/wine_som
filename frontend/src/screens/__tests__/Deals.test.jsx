import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Deals from '../Deals.jsx';
import Discovery from '../Discovery.jsx';
import DealCard from '../../components/DealCard.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../lib/api.js', () => ({ getDeals: vi.fn() }));
import { getDeals } from '../../lib/api.js';

const DEAL = {
  wine_id: 'w1', name: 'Schug Carneros Chardonnay', producer: 'Schug', vintage_year: 2022,
  varietal: 'Chardonnay', region: 'Carneros', wine_type: 'white', image_url: null,
  vivino_rating: 3.9, vivino_ratings_count: 800, tasting_note: 'Orchard fruit and cream.',
  flavor_profile: ['orchard fruit'], price: 14.99, was_price: 17.49, amount: 2.5,
  retailer: 'H-E-B', store_address: '123 Main',
};

beforeEach(() => { getDeals.mockReset(); mockNavigate.mockClear(); });

function renderScreen(el, path = '/deals') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/deals" element={<Deals />} />
        <Route path="/discover" element={<Discovery />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('DealCard', () => {
  it('carries the editorial anatomy: region strip, chip, prices, store pill', () => {
    render(<DealCard deal={DEAL} />);
    expect(screen.getByText('Carneros')).toBeInTheDocument();
    expect(screen.getByText(/\$2\.50 this week/)).toBeInTheDocument();
    expect(screen.getByText('$14.99')).toBeInTheDocument();
    expect(screen.getByText('$17.49')).toBeInTheDocument();     // struck was
    expect(screen.getByText(/◎ H-E-B/)).toBeInTheDocument();
  });
});

describe('Deals screen', () => {
  it('renders the week header and a card per deal', async () => {
    getDeals.mockResolvedValue({ week_of: 'JUL 12', count: 1, deals: [DEAL] });
    renderScreen();
    await waitFor(() => screen.getByText(/Week of JUL 12/));
    expect(screen.getByText('Good wine whose price just moved')).toBeInTheDocument();
    expect(screen.getByText('Schug Carneros Chardonnay')).toBeInTheDocument();
    expect(screen.getByText(/\$2\.50 this week/)).toBeInTheDocument();   // chip on the card
  });

  it('empty week reads as resolved, not broken', async () => {
    getDeals.mockResolvedValue({ week_of: 'JUL 12', count: 0, deals: [] });
    renderScreen();
    await waitFor(() => screen.getByText(/Nothing worth flagging/));
  });
});

describe('Discovery deals rail', () => {
  it('shows the rail with See all count when the week has a cut', async () => {
    getDeals.mockResolvedValue({ week_of: 'JUL 12', count: 7, deals: [DEAL] });
    renderScreen(null, '/discover');
    await waitFor(() => screen.getByText(/Worth grabbing · Week of JUL 12/));
    expect(screen.getByText('See all 7 →')).toBeInTheDocument();
    expect(screen.getByText('Schug Carneros Chardonnay')).toBeInTheDocument();
  });

  it('MOBILE Discovery shows the compact rail too', async () => {
    window.matchMedia = vi.fn().mockImplementation(q => ({
      matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
    }));
    getDeals.mockResolvedValue({ week_of: 'JUL 12', count: 3, deals: [DEAL] });
    renderScreen(null, '/discover');
    await waitFor(() => screen.getByText(/Worth grabbing · Week of JUL 12/));
    expect(screen.getByText('See all 3 →')).toBeInTheDocument();
    window.matchMedia = undefined;
  });

  it('renders nothing when the week has no cut — absence is the design', async () => {
    getDeals.mockResolvedValue({ week_of: 'JUL 12', count: 0, deals: [] });
    renderScreen(null, '/discover');
    await waitFor(() => expect(getDeals).toHaveBeenCalled());
    expect(screen.queryByText(/Worth grabbing/)).toBeNull();
  });
});
