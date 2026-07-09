import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

const auth = { isConfigured: true, authState: 'signed_in', user: { id: 'u1' }, requireSignIn: vi.fn() };
vi.mock('../../lib/auth.jsx', () => ({ useAuth: () => auth }));

const { postFeedback } = vi.hoisted(() => ({ postFeedback: vi.fn() }));
vi.mock('../../lib/api.js', () => ({ postFeedback }));

// supabase read of an existing vote — default: none
vi.mock('../../lib/supabase.js', () => ({ supabase: null }));

import DossierRateButton from '../DossierRateButton.jsx';

test('signed in: thumbs-up posts wine_card feedback with the user id', async () => {
  auth.authState = 'signed_in'; postFeedback.mockClear();
  render(<DossierRateButton wineId="w1" zip="78209" />);
  await userEvent.click(screen.getByRole('button', { name: /loved it/i }));
  expect(postFeedback).toHaveBeenCalledWith(expect.objectContaining({
    type: 'wine_card', entity_id: 'w1', vote: 'up', user_id: 'u1',
  }));
});

test('anonymous: tapping a thumb opens the sign-in prompt instead of posting', async () => {
  auth.authState = 'anonymous'; auth.requireSignIn = vi.fn(); postFeedback.mockClear();
  render(<DossierRateButton wineId="w1" />);
  await userEvent.click(screen.getByRole('button', { name: /not for me/i }));
  expect(auth.requireSignIn).toHaveBeenCalled();
  expect(postFeedback).not.toHaveBeenCalled();
});

test('renders nothing when auth is not configured', () => {
  auth.isConfigured = false;
  const { container } = render(<DossierRateButton wineId="w1" />);
  expect(container).toBeEmptyDOMElement();
  auth.isConfigured = true;
});
