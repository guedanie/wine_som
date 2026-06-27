import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PreferenceCapture from '../PreferenceCapture.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeEach(() => mockNavigate.mockClear());

function renderScreen() {
  return render(<MemoryRouter><PreferenceCapture /></MemoryRouter>);
}

it('pre-fills zip with 78209', () => {
  renderScreen();
  expect(screen.getByDisplayValue('78209')).toBeInTheDocument();
});

it('disables Find wines when zip is empty', () => {
  renderScreen();
  fireEvent.change(screen.getByDisplayValue('78209'), { target: { value: '' } });
  expect(screen.getByRole('button', { name: /find wines/i })).toBeDisabled();
});

it('disables Find wines when no style is selected', () => {
  renderScreen();
  fireEvent.click(screen.getByText('Bold & Tannic')); // deselect default
  expect(screen.getByRole('button', { name: /find wines/i })).toBeDisabled();
});

it('enables Find wines when zip is 5 digits and a style is selected', () => {
  renderScreen(); // defaults: zip=78209, style=Bold & Tannic
  expect(screen.getByRole('button', { name: /find wines/i })).toBeEnabled();
});

it('navigates to /recommend with prefs and apiReq on submit', () => {
  renderScreen();
  fireEvent.click(screen.getByRole('button', { name: /find wines/i }));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', expect.objectContaining({
    state: expect.objectContaining({
      prefs:  expect.objectContaining({ zip: '78209' }),
      apiReq: expect.objectContaining({ zip_code: '78209' }),
    }),
  }));
});

it('renders wine type chips for Red, White, Rosé, Sparkling', () => {
  renderScreen();
  expect(screen.getByRole('button', { name: /^red$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^white$/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /rosé/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sparkling/i })).toBeInTheDocument();
});

it('selecting a wine type chip includes it in apiReq.wine_types', () => {
  renderScreen();
  fireEvent.click(screen.getByRole('button', { name: /^red$/i }));
  fireEvent.click(screen.getByRole('button', { name: /find wines/i }));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', expect.objectContaining({
    state: expect.objectContaining({
      apiReq: expect.objectContaining({ wine_types: ['red'] }),
    }),
  }));
});

it('does not show varietal chips until Advanced search is expanded', () => {
  renderScreen();
  expect(screen.queryByRole('button', { name: /cabernet sauvignon/i })).not.toBeInTheDocument();
});

it('shows varietal chips after clicking Advanced search toggle', () => {
  renderScreen();
  fireEvent.click(screen.getByRole('button', { name: /advanced search/i }));
  expect(screen.getByRole('button', { name: /cabernet sauvignon/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /chardonnay/i })).toBeInTheDocument();
});

it('selected varietals are included in apiReq.grapes', () => {
  renderScreen();
  fireEvent.click(screen.getByRole('button', { name: /advanced search/i }));
  fireEvent.click(screen.getByRole('button', { name: /cabernet sauvignon/i }));
  fireEvent.click(screen.getByRole('button', { name: /find wines/i }));
  expect(mockNavigate).toHaveBeenCalledWith('/recommend', expect.objectContaining({
    state: expect.objectContaining({
      apiReq: expect.objectContaining({ grapes: ['Cabernet Sauvignon'] }),
    }),
  }));
});
