// frontend/src/components/__tests__/AisleStrip.test.jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import AisleStrip from '../AisleStrip.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

it('renders the invitation and crosses to the ask face with the store picker open', async () => {
  render(<MemoryRouter><AisleStrip /></MemoryRouter>);
  const strip = screen.getByText(/In a store right now\? Just ask me instead\./);
  await userEvent.click(strip);
  expect(mockNavigate).toHaveBeenCalledWith('/recommend',
    { state: { mode: 'ask', openStorePicker: true } });
});
