import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

const { addBottle } = vi.hoisted(() => ({ addBottle: vi.fn(async (_u, b) => ({ id: 'c1', ...b })) }));
vi.mock('../../lib/cellar.js', () => ({ addBottle }));

import AddBottleModal from '../AddBottleModal.jsx';

test('requires a name — submit disabled until entered', async () => {
  render(<AddBottleModal userId="u1" onClose={() => {}} onAdded={() => {}} />);
  const submit = screen.getByRole('button', { name: /add to cellar/i });
  expect(submit).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/wine name/i), 'Barolo Riserva');
  expect(submit).not.toBeDisabled();
});

test('submitting adds the bottle and calls onAdded', async () => {
  const onAdded = vi.fn();
  render(<AddBottleModal userId="u1" onClose={() => {}} onAdded={onAdded} />);
  await userEvent.type(screen.getByLabelText(/wine name/i), 'Barolo');
  await userEvent.type(screen.getByLabelText(/vintage/i), '2015');
  await userEvent.click(screen.getByRole('button', { name: /add to cellar/i }));
  expect(addBottle).toHaveBeenCalledWith('u1', expect.objectContaining({ name: 'Barolo', vintage: 2015 }));
  expect(onAdded).toHaveBeenCalled();
});

test('prefills from a catalog wine', () => {
  render(<AddBottleModal userId="u1" prefill={{ wine_id: 'w9', name: 'Esprit de Tablas', vintage: 2021 }} onClose={() => {}} onAdded={() => {}} />);
  expect(screen.getByLabelText(/wine name/i)).toHaveValue('Esprit de Tablas');
});

test('shows a live drinking-window preview from varietal + vintage', async () => {
  render(<AddBottleModal userId="u1" onClose={() => {}} onAdded={() => {}} />);
  await userEvent.type(screen.getByLabelText(/wine name/i), 'X');
  await userEvent.type(screen.getByLabelText(/varietal/i), 'Cabernet Sauvignon');
  await userEvent.type(screen.getByLabelText(/vintage/i), '2015');
  // window preview appears (label like "Peak 2019–2030" + est range)
  expect(screen.getAllByText(/Peak|Drink|Hold/).length).toBeGreaterThan(0);
  expect(screen.getByText(/est\. 2019/)).toBeInTheDocument();
});
