import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Discovery from '../Discovery.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => { mockNavigate.mockClear(); });

function renderScreen() {
  return render(<MemoryRouter><Discovery /></MemoryRouter>);
}

it('renders all 18 region names', () => {
  renderScreen();
  expect(screen.getAllByText('Tuscany')[0]).toBeInTheDocument();        // tier 1 — Poster footer renders name
  expect(screen.getAllByText('Paso Robles')[0]).toBeInTheDocument();    // tier 1 — Poster footer renders name
  expect(screen.getAllByText('Champagne')[0]).toBeInTheDocument();      // tier 2 — Poster footer also renders name
  expect(screen.getAllByText('Mosel')[0]).toBeInTheDocument();          // tier 2 — same
});

it('renders a "More regions" section divider between tiers', () => {
  renderScreen();
  expect(screen.getByText(/more regions/i)).toBeInTheDocument();
});

it('navigates to the region detail page when a region card is clicked', async () => {
  renderScreen();
  await userEvent.click(screen.getAllByText('Tuscany')[0]);
  expect(mockNavigate).toHaveBeenCalledWith('/regions/tuscany');
});
