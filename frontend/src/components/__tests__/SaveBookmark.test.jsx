import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

const auth = { isConfigured: true, isSaved: vi.fn(() => false), toggleSave: vi.fn() };
vi.mock('../../lib/auth.jsx', () => ({ useAuth: () => auth }));

import SaveBookmark from '../SaveBookmark.jsx';

beforeEach(() => { auth.isConfigured = true; auth.isSaved = vi.fn(() => false); auth.toggleSave = vi.fn(); });

test('renders a Save control and toggles on click (with the wine)', async () => {
  const wine = { id: 'w1', name: 'Esprit de Tablas' };
  render(<SaveBookmark wine={wine} />);
  const btn = screen.getByRole('button', { name: /save/i });
  await userEvent.click(btn);
  expect(auth.toggleSave).toHaveBeenCalledWith(wine);
});

test('reflects the saved state', () => {
  auth.isSaved = vi.fn(() => true);
  render(<SaveBookmark wine={{ id: 'w1' }} />);
  expect(screen.getByRole('button', { name: /saved/i })).toBeInTheDocument();
});

test('renders nothing when auth is not configured', () => {
  auth.isConfigured = false;
  const { container } = render(<SaveBookmark wine={{ id: 'w1' }} />);
  expect(container).toBeEmptyDOMElement();
});

test('renders nothing without a wine id', () => {
  const { container } = render(<SaveBookmark wine={{}} />);
  expect(container).toBeEmptyDOMElement();
});

test('uses wine_id when present (chat picks)', async () => {
  const wine = { wine_id: 'p1', name: 'Pick' };
  auth.isSaved = vi.fn(id => id === 'p1');
  render(<SaveBookmark wine={wine} />);
  expect(screen.getByRole('button', { name: /saved/i })).toBeInTheDocument();
});
