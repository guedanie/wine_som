import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import SignInModal from '../SignInModal.jsx';

test('State A: email entry with generic head + send button', () => {
  render(<SignInModal onClose={() => {}} signInWithEmail={vi.fn()} />);
  expect(screen.getByPlaceholderText(/you@/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Send magic link/i })).toBeInTheDocument();
});

test('contextual head shows the wine name when a wine is passed', () => {
  render(<SignInModal wine={{ name: 'Esprit de Tablas' }} onClose={() => {}} signInWithEmail={vi.fn()} />);
  expect(screen.getByText(/Esprit de Tablas/)).toBeInTheDocument();
});

test('submitting the email calls signInWithEmail and advances to State B', async () => {
  const signIn = vi.fn().mockResolvedValue({ error: null });
  render(<SignInModal onClose={() => {}} signInWithEmail={signIn} />);
  await userEvent.type(screen.getByPlaceholderText(/you@/i), 'me@test.com');
  await userEvent.click(screen.getByRole('button', { name: /Send magic link/i }));
  await waitFor(() => expect(signIn).toHaveBeenCalledWith('me@test.com'));
  expect(screen.getByText(/Check your inbox/i)).toBeInTheDocument();
  expect(screen.getByText(/me@test.com/)).toBeInTheDocument();
});

test('Change email returns to State A', async () => {
  const signIn = vi.fn().mockResolvedValue({ error: null });
  render(<SignInModal onClose={() => {}} signInWithEmail={signIn} />);
  await userEvent.type(screen.getByPlaceholderText(/you@/i), 'me@test.com');
  await userEvent.click(screen.getByRole('button', { name: /Send magic link/i }));
  await waitFor(() => screen.getByText(/Check your inbox/i));
  await userEvent.click(screen.getByRole('button', { name: /Change email/i }));
  expect(screen.getByRole('button', { name: /Send magic link/i })).toBeInTheDocument();
});

it('watch kind shows the price-watch nudge copy, never a wall', () => {
  render(<SignInModal wine={{ name: 'Esprit de Tablas' }} kind="watch" onClose={() => {}} signInWithEmail={vi.fn()} />);
  expect(screen.getByText('WATCH THIS PRICE')).toBeInTheDocument();
  expect(screen.getByText(/I’ll tell you when|I'll tell you when/)).toBeInTheDocument();
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
  expect(screen.getByText(/this just saves the watch/)).toBeInTheDocument();
});
