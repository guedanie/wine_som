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
import { TopBar } from '../components/MobileChrome.jsx';

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

test('mobile chat: picks render as conversational messages (Option C)', async () => {
  const cards = [
    { wine_id: 'w1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Dark cherry, garrigue.' },
    { wine_id: 'w2', name: 'Brunello di Montalcino', price: 72, retailer: 'H-E-B', why: 'Structured and age-worthy.' },
  ];
  const restored = {
    sessionId: 's1',
    wineVotes: {},
    messageVotes: {},
    // Option C: picks attached to the message that produced them; rendered as messages
    messages: [{ id: 'm1', role: 'sommelier', text: 'Two bottles near you.', picks: cards }],
    picks: cards,
  };
  render(
    <MemoryRouter initialEntries={[{
      pathname: '/recommend',
      state: { prefs: { zip: '78209', budget: 60, styles: ['Bold & Tannic'], occasion: 'Tonight' }, apiReq: {}, _restored: restored },
    }]}>
      <Routes><Route path="/recommend" element={<ChatRecommend />} /></Routes>
    </MemoryRouter>
  );
  expect(screen.queryByTestId('wine-sheet')).not.toBeInTheDocument();
  expect(screen.queryByText(/picks near you/)).not.toBeInTheDocument();  // no card-block label
  // wine names render as links, with their tasting notes and prices
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
  expect(screen.getByText('Brunello di Montalcino')).toBeInTheDocument();
  expect(screen.getByText(/Dark cherry/)).toBeInTheDocument();
  expect(screen.getByText('$55')).toBeInTheDocument();
});

test('mobile chat: no inline cards when the message has no picks', () => {
  const restored = {
    sessionId: 's1', wineVotes: {}, messageVotes: {},
    messages: [{ id: 'm1', role: 'sommelier', text: 'Tell me a bit more about the occasion.' }],
    picks: [],
  };
  render(
    <MemoryRouter initialEntries={[{
      pathname: '/recommend',
      state: { prefs: { zip: '78209', budget: 60, styles: [], occasion: 'Tonight' }, apiReq: {}, _restored: restored },
    }]}>
      <Routes><Route path="/recommend" element={<ChatRecommend />} /></Routes>
    </MemoryRouter>
  );
  expect(screen.queryByTestId('wine-sheet')).not.toBeInTheDocument();
  expect(screen.queryByText(/picks near you/)).not.toBeInTheDocument();
});


test('mobile dossier back restores the chat session (no re-run)', async () => {
  const { useLocation } = await import('react-router-dom');
  let restoredState = null;
  function RecommendProbe() {
    const loc = useLocation();
    restoredState = loc.state;
    return <div>recommend-screen</div>;
  }
  const chatState = {
    prefs: { zip: '78209' }, apiReq: { zip_code: '78209' },
    messages: [{ id: 'm1', role: 'user', text: 'bold red' }],
    picks: [{ wine_id: 'w1', name: 'X' }], sessionId: 's1',
    wineVotes: {}, messageVotes: {},
  };
  render(
    <MemoryRouter initialEntries={[{ pathname: '/wine/w1', state: { pick: { name: 'Brunello' }, chatState } }]}>
      <TopBar />
      <Routes>
        <Route path="/wine/:id" element={<div>dossier</div>} />
        <Route path="/recommend" element={<RecommendProbe />} />
      </Routes>
    </MemoryRouter>
  );
  await userEvent.click(screen.getByLabelText('Back'));
  expect(screen.getByText('recommend-screen')).toBeInTheDocument();
  expect(restoredState._restored).toEqual(chatState);
});
