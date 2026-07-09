import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const auth = { authState: 'signed_in', user: { id: 'u1', email: 'm@t.com' }, requireSignIn: vi.fn() };
vi.mock('../../lib/auth.jsx', () => ({ useAuth: () => auth }));

const { listCellar, drinkBottle, removeBottle } = vi.hoisted(() => ({
  listCellar: vi.fn(async () => []),
  drinkBottle: vi.fn(async () => true),
  removeBottle: vi.fn(async () => true),
}));
vi.mock('../../lib/cellar.js', () => ({ listCellar, drinkBottle, removeBottle }));

const { postFeedback } = vi.hoisted(() => ({ postFeedback: vi.fn() }));
vi.mock('../../lib/api.js', () => ({ postFeedback }));

import Cellar from '../Cellar.jsx';

const renderCellar = () => render(<MemoryRouter><Cellar /></MemoryRouter>);
const bottle = { id: 'c1', name: 'Barolo Riserva', vintage: 2015, region: 'Piedmont', quantity: 2, drink_from: 2019, drink_to: 2030, status: 'owned' };

beforeEach(() => {
  auth.authState = 'signed_in'; auth.requireSignIn = vi.fn();
  listCellar.mockResolvedValue([]); drinkBottle.mockResolvedValue(true); removeBottle.mockResolvedValue(true);
});

test('signed out: shows an invite, not a wall', async () => {
  auth.authState = 'anonymous';
  renderCellar();
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
  expect(auth.requireSignIn).toHaveBeenCalled();
});

test('empty cellar shows an empty state', async () => {
  renderCellar();
  await waitFor(() => expect(screen.getByText(/nothing in your cellar yet/i)).toBeInTheDocument());
});

test('renders a bottle with its drinking-window label', async () => {
  listCellar.mockResolvedValue([bottle]);
  renderCellar();
  await waitFor(() => expect(screen.getByText('Barolo Riserva')).toBeInTheDocument());
  expect(screen.getByText('2015')).toBeInTheDocument();
  expect(screen.getByText(/Peak|Drink|Hold/)).toBeInTheDocument();  // window label
});

test('"drank it" logs a consumed bottle', async () => {
  listCellar.mockResolvedValue([bottle]);
  renderCellar();
  await waitFor(() => screen.getByText('Barolo Riserva'));
  await userEvent.click(screen.getByRole('button', { name: /drank/i }));
  expect(drinkBottle).toHaveBeenCalledWith('u1', expect.objectContaining({ id: 'c1' }));
});

test('rating the wine you just drank records feedback (catalog wine)', async () => {
  postFeedback.mockClear();
  listCellar.mockResolvedValue([{ ...bottle, wine_id: 'cw1' }]);
  renderCellar();
  await waitFor(() => screen.getByText('Barolo Riserva'));
  await userEvent.click(screen.getByRole('button', { name: /drank/i }));
  const up = await screen.findByRole('button', { name: /loved it/i });   // rating prompt appeared
  await userEvent.click(up);
  expect(postFeedback).toHaveBeenCalledWith(expect.objectContaining({ type: 'wine_card', entity_id: 'cw1', vote: 'up' }));
});
