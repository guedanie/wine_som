import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

const auth = { authState: 'signed_in', user: { id: 'u1' }, requireSignIn: vi.fn() };
vi.mock('../../lib/auth.jsx', () => ({ useAuth: () => auth }));

const { saveTasteProfile } = vi.hoisted(() => ({ saveTasteProfile: vi.fn(async () => true) }));
vi.mock('../../lib/profile.js', () => ({ saveTasteProfile, getTasteProfile: vi.fn(async () => null) }));

import TasteProfile from '../TasteProfile.jsx';

const renderScreen = () => render(<MemoryRouter><TasteProfile /></MemoryRouter>);

test('signed out invites sign-in', async () => {
  auth.authState = 'anonymous';
  renderScreen();
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
  expect(auth.requireSignIn).toHaveBeenCalled();
  auth.authState = 'signed_in';
});

test('completing the interview saves a structured taste profile', async () => {
  auth.authState = 'signed_in';
  saveTasteProfile.mockClear();
  renderScreen();
  await userEvent.click(screen.getByRole('button', { name: 'Bold reds' }));
  await userEvent.click(screen.getByRole('button', { name: 'Big & bold' }));
  await userEvent.click(screen.getByRole('button', { name: 'Bone dry, always' }));
  await userEvent.click(screen.getByRole('button', { name: 'Open to a nudge' }));
  await userEvent.click(screen.getByRole('button', { name: 'Napa' }));          // regions (multi)
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
  await userEvent.click(screen.getByRole('button', { name: 'Oaky Chardonnay' })); // avoid (multi)
  await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
  await waitFor(() => expect(saveTasteProfile).toHaveBeenCalledWith('u1', expect.objectContaining({
    lean: 'bold_red', body: 'full', sweetness: 'dry', adventurous: 'open',
    regions_love: ['Napa'], avoid: ['Oaky Chardonnay'],
  })));
  expect(screen.getByText(/See my picks/i)).toBeInTheDocument();
});
