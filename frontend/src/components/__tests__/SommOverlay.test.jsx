import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SommOverlay from '../SommOverlay.jsx';

vi.mock('../../lib/api.js', () => ({
  streamSomm: vi.fn(),
  postFeedback: vi.fn(),
}));
import { streamSomm, postFeedback } from '../../lib/api.js';

const wine = {
  wine_name: 'Esprit de Tablas',
  producer: 'Tablas Creek',
  vintage: 2021,
  price: 55,
  store: "Spec's",
  tags: ['dark cherry', 'garrigue'],
  region: 'Paso Robles',
  wine_type: 'Red Wine',
};

beforeEach(() => {
  streamSomm.mockClear();
  postFeedback.mockClear();
  streamSomm.mockImplementation(async function* () {
    yield { type: 'token', text: 'A structured, complex wine.' };
  });
});

it('renders FAB button', () => {
  render(<SommOverlay wine={wine} />);
  expect(screen.getByRole('button', { name: /ask somm/i })).toBeInTheDocument();
});

it('panel is hidden by default', () => {
  render(<SommOverlay wine={wine} />);
  expect(screen.queryByText('Somm')).not.toBeInTheDocument();
});

it('clicking FAB opens panel', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText('Somm')).toBeInTheDocument();
});

it('FAB hides when panel is open', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.queryByRole('button', { name: /ask somm/i })).not.toBeInTheDocument();
});

it('context strip shows wine name', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
});

it('context strip shows price', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText('$55')).toBeInTheDocument();
});

it('opening message streams on first open', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText('A structured, complex wine.')).toBeInTheDocument());
});

it('shows "Was this useful?" row on sommelier message', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText('Was this useful?')).toBeInTheDocument());
});

it('shows suggestion chips', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  expect(screen.getByText(/Cellar potential/i)).toBeInTheDocument();
});

it('close button hides panel and shows FAB again', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await userEvent.click(screen.getByTitle('Close'));
  expect(screen.queryByText('Somm')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /ask somm/i })).toBeInTheDocument();
});

it('chat history persists across close and reopen', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText('A structured, complex wine.')).toBeInTheDocument());
  await userEvent.click(screen.getByTitle('Close'));
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  // Message should still be visible; streamSomm should NOT have been called a second time
  expect(screen.getByText('A structured, complex wine.')).toBeInTheDocument();
  expect(streamSomm).toHaveBeenCalledTimes(1);
});

it('chip click sends the chip text as a message', async () => {
  render(<SommOverlay wine={wine} />);
  await userEvent.click(screen.getByRole('button', { name: /ask somm/i }));
  await waitFor(() => expect(screen.getByText(/Cellar potential/i)).toBeInTheDocument());
  await userEvent.click(screen.getByText(/Cellar potential/i));
  // The chip text should appear as a user bubble
  await waitFor(() => expect(screen.getByText('Cellar potential?')).toBeInTheDocument());
});
