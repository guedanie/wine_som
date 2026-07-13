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

vi.mock('../../lib/api.js', () => ({ streamRecommend: vi.fn(), postFeedback: vi.fn() }));
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

it('shows the wine glass loader while streamRecommend is pending', () => {
  streamRecommend.mockImplementation(async function* () {
    await new Promise(() => {}); // never resolves
  });
  renderScreen();
  expect(screen.getByTestId('wine-glass-loader')).toBeInTheDocument();
});

it('shows a "pouring your picks" placeholder while the narrative streams before picks arrive', async () => {
  // Narrative tokens stream, then the generator hangs before emitting picks —
  // mirrors the real gap where picks land only after the narrative completes.
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are ' };
    yield { type: 'token', text: 'three bottles.' };
    await new Promise(() => {}); // no picks yet
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText(/Pouring your picks/i)).toBeInTheDocument());
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

it('sends conversational:true on a follow-up when natural mode is on', async () => {
  // natural mode is on by default (empty storage)
  const store = {};
  vi.stubGlobal('localStorage', {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  });
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are three wines.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Here are three wines.'));
  const input = screen.getAllByPlaceholderText('Ask a follow-up…')[0];
  await userEvent.type(input, 'why that one?{Enter}');
  await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(2));
  expect(streamRecommend.mock.calls[1][0]).toMatchObject({ conversational: true, message: 'why that one?' });
  vi.unstubAllGlobals();
});

it('sends conversational:false on a follow-up when natural mode is off', async () => {
  const store = { somm_natural_off: '1' };   // explicit opt-out
  vi.stubGlobal('localStorage', {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  });
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are three wines.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Here are three wines.'));
  const input = screen.getAllByPlaceholderText('Ask a follow-up…')[0];
  await userEvent.type(input, 'why that one?{Enter}');
  await waitFor(() => expect(streamRecommend).toHaveBeenCalledTimes(2));
  expect(streamRecommend.mock.calls[1][0]).toMatchObject({ conversational: false });
  vi.unstubAllGlobals();
});

it('renders picks as conversational messages on mobile (Option C — name link, price, no card/sheet)', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Weight and grip under $60.\n\n**Esprit de Tablas** is my first call.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Dark cherry, garrigue, leather.' }], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));    // wine name link inline
  expect(screen.getByText('$55')).toBeInTheDocument();           // inline price
  expect(screen.getByText(/Dark cherry/)).toBeInTheDocument();   // per-pick tasting note (why)
  expect(screen.queryByText(/picks near you/)).toBeNull();       // no card-block label
  expect(screen.queryByTestId('wine-sheet')).toBeNull();         // no bottom sheet
  window.matchMedia = undefined;
});

it('shows the Vivino rating badge in a mobile pick message', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'One pick.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.', vivino_rating: 4.3, vivino_ratings_count: 57491 }], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  expect(screen.getByText(/4\.3★/)).toBeInTheDocument();   // rating
  expect(screen.getByText(/57k/)).toBeInTheDocument();      // compact count
  window.matchMedia = undefined;
});

it('suppresses per-wine paragraphs while streaming on mobile, so nothing collapses when cards arrive', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  let release;
  const gate = new Promise(r => { release = r; });
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Weight and grip tonight.\n\n**Hall Napa** is structured cassis.\n\n**Jadot Beaujolais** is the value play.' };
    await gate;   // hold the stream open — narrative done, picks not yet arrived
    yield { type: 'picks', picks: [
      { wine_id: 'uuid-1', name: 'Hall Napa', price: 99, retailer: 'H-E-B', why: 'Structured.' },
      { wine_id: 'uuid-2', name: 'Jadot Beaujolais', price: 13, retailer: 'Twin Liquors', why: 'Value.' },
    ], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText(/Weight and grip/));   // framing line streams
  expect(screen.queryByText('Hall Napa')).toBeNull();          // per-wine paras held back
  expect(screen.queryByText('Jadot Beaujolais')).toBeNull();
  release();
  // cards arrive; wine names now exist only as card name-links (one each, no collapse-remnant text)
  await waitFor(() => expect(screen.getAllByText('Hall Napa')).toHaveLength(1));
  expect(screen.getAllByText('Jadot Beaujolais')).toHaveLength(1);
  expect(screen.getByText(/Weight and grip/)).toBeInTheDocument();  // framing line intact
  window.matchMedia = undefined;
});

it('reveals held-back paragraphs when the stream ends without picks (education answers)', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  let release;
  const gate = new Promise(r => { release = r; });
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Two things matter here.\n\n**Tannins** dry the palate.' };
    await gate;
    // stream ends with no picks event — an education-mode answer
  });
  renderScreen();
  await waitFor(() => screen.getByText(/Two things matter/));
  expect(screen.queryByText('Tannins')).toBeNull();
  release();
  await waitFor(() => expect(screen.getByText('Tannins')).toBeInTheDocument());
  window.matchMedia = undefined;
});

it('never suppresses the first paragraph even when it opens with a bold name', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: '**Esprit de Tablas** is my first call.' };
    await new Promise(() => {});   // still streaming
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument());
  window.matchMedia = undefined;
});

it('renders a card from a progressive pick event, before the final picks array', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'My first call.' };
    yield { type: 'pick', pick: { wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' } };
    // no final picks event — the progressive pick alone must render
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  expect(screen.getByText('$55')).toBeInTheDocument();
  window.matchMedia = undefined;
});

it('final picks event replaces progressive picks without duplicating cards', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  const pick = { wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' };
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'My first call.' };
    yield { type: 'pick', pick };
    yield { type: 'picks', picks: [pick], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  expect(screen.getAllByText('Esprit de Tablas')).toHaveLength(1);
  window.matchMedia = undefined;
});

it('shows store distance in the mobile store pill when provided', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'One pick.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.', distance_miles: 2.1 }], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  expect(screen.getByText(/◎ Spec's · 2\.1 mi/)).toBeInTheDocument();
  window.matchMedia = undefined;
});

it('mobile store pill shows just the retailer when distance is missing', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'One pick.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  expect(screen.getByText("◎ Spec's")).toBeInTheDocument();
  window.matchMedia = undefined;
});

it('omits the rating badge when a mobile pick has no Vivino rating', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'One pick.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-2', name: 'Obscure Natural', price: 32, retailer: "Geraldine's", why: 'Funky.' }], session_id: 'sess-2' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Obscure Natural'));
  expect(screen.queryByText(/★/)).toBeNull();
  window.matchMedia = undefined;
});

it('tapping the wine-name link on mobile navigates to the dossier', async () => {
  window.matchMedia = vi.fn().mockImplementation(q => ({
    matches: true, media: q, addEventListener: () => {}, removeEventListener: () => {},
  }));
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'One pick.' };
    yield { type: 'picks', picks: [{ wine_id: 'uuid-1', name: 'Esprit de Tablas', price: 55, retailer: "Spec's", why: 'Great.' }], session_id: 'sess-1' };
  });
  renderScreen();
  await waitFor(() => screen.getByText('Esprit de Tablas'));
  await userEvent.click(screen.getByText('Esprit de Tablas'));
  expect(mockNavigate).toHaveBeenCalledWith('/wine/uuid-1', expect.objectContaining({
    state: expect.objectContaining({ pick: expect.objectContaining({ wine_id: 'uuid-1' }) }),
  }));
  window.matchMedia = undefined;
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

it('shows "Was this useful?" row under sommelier messages', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are your picks.' };
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Here are your picks.')).toBeInTheDocument());
  expect(screen.getByText('Was this useful?')).toBeInTheDocument();
});

it('appends follow-up bubble on thumbs-down of sommelier message', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are your picks.' };
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Was this useful?')).toBeInTheDocument());
  await userEvent.click(screen.getByTitle('Not helpful'));
  expect(screen.getByText(/what didn't land/i)).toBeInTheDocument();
});

it('does not append a second follow-up when toggling thumbs-down off', async () => {
  streamRecommend.mockImplementation(async function* () {
    yield { type: 'token', text: 'Here are your picks.' };
  });
  renderScreen();
  await waitFor(() => expect(screen.getByText('Was this useful?')).toBeInTheDocument());
  await userEvent.click(screen.getByTitle('Not helpful'));
  await userEvent.click(screen.getByTitle('Not helpful')); // toggle off
  expect(screen.getAllByText(/what didn't land/i)).toHaveLength(1);
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

it('restores dynamic follow-up chips (not the defaults) from _restored', async () => {
  renderScreen({
    prefs, apiReq,
    _restored: {
      messages: [{ role: 'sommelier', text: 'picks' }],
      picks: [],
      followups: ['Is 2018 a good vintage?', 'Decant this?', 'Cheaper alternative?'],
    },
  });
  await new Promise(r => setTimeout(r, 50));
  // the restored suggestions show, not the DEFAULT_FOLLOWUPS
  expect(screen.getByText('Is 2018 a good vintage?')).toBeInTheDocument();
  expect(screen.queryByText('Anything from Burgundy?')).not.toBeInTheDocument();
});
