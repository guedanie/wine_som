import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Force the mobile path: jsdom has no matchMedia, so useIsMobile defaults to
// desktop everywhere else. Here we install a matching mock before render.
beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation(query => ({
    matches: true,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});
afterEach(() => { delete window.matchMedia; });

vi.mock('../lib/api.js', () => ({
  streamRecommend: vi.fn(),
  postFeedback: vi.fn(),
  getWine: vi.fn().mockResolvedValue({}),
  getSubregionCounts: vi.fn().mockResolvedValue({ counts: {} }),
  searchWines: vi.fn().mockResolvedValue({ wines: [] }),
}));
vi.mock('../components/RegionMap.jsx', () => ({
  default: () => <div data-testid="region-map" />,
}));

import App from '../App.jsx';
import ChatRecommend from '../screens/ChatRecommend.jsx';

test('mobile chrome: TopBar brand + bottom tabs render', () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <App />
    </MemoryRouter>
  );
  expect(screen.getByText('Wine Atlas')).toBeInTheDocument();     // TopBar sub
  expect(screen.getByText('Recommend')).toBeInTheDocument();      // tabs
  expect(screen.getByText('Discover')).toBeInTheDocument();
  expect(screen.getByText('Search')).toBeInTheDocument();
  expect(screen.getByText("Tonight's brief")).toBeInTheDocument(); // mobile prefs heading
});

test('mobile chat: picks render in a bottom sheet with a toggle handle', async () => {
  const restored = {
    sessionId: 's1',
    wineVotes: {},
    messageVotes: {},
    messages: [{ id: 'm1', role: 'sommelier', text: 'Two picks for you.' }],
    picks: [
      { wine_id: 'w1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", tagline: 'PASO', coord: null, flavors: [] },
      { wine_id: 'w2', name: 'Brunello di Montalcino', price: 72, retailer: 'H-E-B', tagline: 'TUSCANY', coord: null, flavors: [] },
    ],
  };
  render(
    <MemoryRouter initialEntries={[{
      pathname: '/recommend',
      state: { prefs: { zip: '78209', budget: 60, styles: ['Bold & Tannic'], occasion: 'Tonight' }, apiReq: {}, _restored: restored },
    }]}>
      <Routes><Route path="/recommend" element={<ChatRecommend />} /></Routes>
    </MemoryRouter>
  );
  expect(screen.getByTestId('wine-sheet')).toBeInTheDocument();
  expect(screen.getByText('2 wines for you')).toBeInTheDocument();
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();

  const handle = screen.getByRole('button', { expanded: false });
  await userEvent.click(handle);
  expect(screen.getByRole('button', { expanded: true })).toBeInTheDocument();
});

test('mobile chat: sheet absent when there are no picks', () => {
  const restored = { sessionId: 's1', wineVotes: {}, messageVotes: {}, messages: [], picks: [] };
  render(
    <MemoryRouter initialEntries={[{
      pathname: '/recommend',
      state: { prefs: { zip: '78209', budget: 60, styles: [], occasion: 'Tonight' }, apiReq: {}, _restored: restored },
    }]}>
      <Routes><Route path="/recommend" element={<ChatRecommend />} /></Routes>
    </MemoryRouter>
  );
  expect(screen.queryByTestId('wine-sheet')).not.toBeInTheDocument();
});
