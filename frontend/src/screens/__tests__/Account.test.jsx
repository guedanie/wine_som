import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

const auth = {
  authState: 'anonymous', user: null, savedIds: [], isConfigured: true,
  requireSignIn: vi.fn(), signOut: vi.fn(),
};
vi.mock('../../lib/auth.jsx', () => ({ useAuth: () => auth }));

import Account from '../Account.jsx';

const renderAccount = () => render(<MemoryRouter><Account /></MemoryRouter>);

beforeEach(() => {
  auth.authState = 'anonymous'; auth.user = null; auth.savedIds = [];
  auth.requireSignIn = vi.fn(); auth.signOut = vi.fn();
});

test('signed out: shows the sign-in invite and triggers sign-in', async () => {
  renderAccount();
  const btn = screen.getByRole('button', { name: /sign in with email/i });
  await userEvent.click(btn);
  expect(auth.requireSignIn).toHaveBeenCalled();
});

test('signed in: shows email, saved count, and sign out', async () => {
  auth.authState = 'signed_in';
  auth.user = { email: 'me@test.com' };
  auth.savedIds = ['w1', 'w2', 'w3'];
  renderAccount();
  expect(screen.getByText('me@test.com')).toBeInTheDocument();
  expect(screen.getByText('3')).toBeInTheDocument();              // saved stat
  await userEvent.click(screen.getByRole('button', { name: /sign out/i }));
  expect(auth.signOut).toHaveBeenCalled();
});
