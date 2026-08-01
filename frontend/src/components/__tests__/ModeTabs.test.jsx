// frontend/src/components/__tests__/ModeTabs.test.jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { TopBar } from '../MobileChrome.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => mockNavigate.mockClear());

function renderAt(entry) {
  return render(<MemoryRouter initialEntries={[entry]}><TopBar /></MemoryRouter>);
}

it('shows both mode tabs on /, PLAN active', () => {
  renderAt('/');
  const plan = screen.getByText('PLAN A BOTTLE');
  const ask = screen.getByText('ASK');
  expect(plan).toBeInTheDocument();
  expect(ask).toBeInTheDocument();
  expect(plan.style.color).toBe('var(--ink)');
  expect(ask.style.color).toBe('var(--faded)');
});

it('shows ASK active on /recommend in ask mode', () => {
  renderAt({ pathname: '/recommend', state: { mode: 'ask' } });
  expect(screen.getByText('ASK').style.color).toBe('var(--ink)');
  expect(screen.getByText('PLAN A BOTTLE').style.color).toBe('var(--faded)');
});

it('keeps the plan-thread title (no tabs) on /recommend with prefs', () => {
  renderAt({ pathname: '/recommend', state: { prefs: { zip: '78209' } } });
  expect(screen.queryByText('PLAN A BOTTLE')).toBeNull();
  expect(screen.getByText(/Tonight, near 78209/)).toBeInTheDocument();
});

it('tapping ASK navigates to the ask face', async () => {
  renderAt('/');
  await userEvent.click(screen.getByText('ASK'));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', { state: { mode: 'ask' } });
});

it('tapping PLAN A BOTTLE navigates home', async () => {
  renderAt({ pathname: '/recommend', state: { mode: 'ask' } });
  await userEvent.click(screen.getByText('PLAN A BOTTLE'));
  expect(mockNavigate).toHaveBeenCalledWith('/');
});
