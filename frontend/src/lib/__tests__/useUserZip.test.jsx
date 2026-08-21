import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useUserZip } from '../useUserZip.js';
import { saveZip } from '../useIsMobile.js';

function Probe() {
  return <div data-testid="zip">{useUserZip()}</div>;
}

function renderWith(state) {
  render(
    <MemoryRouter initialEntries={[{ pathname: '/wine/1', state }]}>
      <Probe />
    </MemoryRouter>,
  );
  return screen.getByTestId('zip').textContent;
}

// Captures the hook's raw return value. The DOM-based renderWith() above
// stringifies through textContent, which can't tell null from '' — and the
// null case is precisely what the test below exists to pin down.
function renderRawWith(state) {
  let captured;
  function RawProbe() { captured = useUserZip(); return null; }
  render(
    <MemoryRouter initialEntries={[{ pathname: '/wine/1', state }]}>
      <RawProbe />
    </MemoryRouter>,
  );
  return captured;
}

beforeEach(() => { localStorage.clear(); });

describe('useUserZip — one precedence chain for every screen', () => {
  it('prefers an explicit state.zip', () => {
    saveZip('37210');
    expect(renderWith({ zip: '75201' })).toBe('75201');
  });

  it('falls back to ASK-mode askZip (the lazy in-conversation zip)', () => {
    // The dossier bug: ASK keeps its zip in askZip, not prefs.zip, so a chain that
    // only knew prefs.zip resolved to null and the API skipped its proximity filter.
    expect(renderWith({ chatState: { askZip: '37210', prefs: null } })).toBe('37210');
  });

  it('reads askZip out of a restored session', () => {
    expect(renderWith({ _restored: { askZip: '28202' } })).toBe('28202');
  });

  it('reads prefs.zip from a pick-carried chatState', () => {
    expect(renderWith({ pick: { chatState: { prefs: { zip: '78230' } } } })).toBe('78230');
  });

  it('falls back to the persisted zip when navigation state carries none', () => {
    saveZip('37210');
    expect(renderWith(undefined)).toBe('37210');
  });

  it('returns null when nothing is stored — "no location" must be representable', () => {
    // Previously this asserted a fabricated '78209' default. That default was
    // rendered to users as though confirmed (top bar, aisle context pill) while
    // a separate flag still said the zip was unknown — the root cause of the
    // aisle-mode "asked for a zip I already gave you" bug. The invariant that
    // actually mattered (never send a null zip to a required-zip endpoint) is
    // enforced at the call sites instead — see Deals/Discovery guards.
    expect(renderRawWith(undefined)).toBe(null);
  });
});
