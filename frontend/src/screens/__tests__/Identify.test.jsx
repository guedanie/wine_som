import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Identify from '../Identify.jsx';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../lib/api.js', () => ({ identifyBottle: vi.fn() }));
import { identifyBottle } from '../../lib/api.js';

beforeEach(() => {
  identifyBottle.mockReset();
  mockNavigate.mockClear();
});

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={['/identify']}>
      <Routes>
        <Route path="/identify" element={<Identify />} />
      </Routes>
    </MemoryRouter>
  );
}

function selectPhoto(file = new File(['bytes'], 'bottle.jpg', { type: 'image/jpeg' })) {
  const input = screen.getByTestId('identify-file-input');
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

describe('Identify screen', () => {
  it('shows an idle upload prompt initially', () => {
    renderScreen();
    expect(screen.getByTestId('identify-file-input')).toBeInTheDocument();
  });

  it('shows the identifying state immediately after a photo is selected', async () => {
    identifyBottle.mockReturnValue(new Promise(() => {})); // never resolves — stay in-flight
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/Let me get a look at it/i)).toBeInTheDocument();
  });

  it('renders an exact match with a link to the dossier', async () => {
    identifyBottle.mockResolvedValue({
      status: 'exact',
      wine: { id: 'w1', name: 'Esprit de Tablas', brand: 'Tablas Creek', vintage_year: 2021, region: 'Paso Robles' },
    });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText('Esprit de Tablas')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/See where to buy/i));
    expect(mockNavigate).toHaveBeenCalledWith('/wine/w1');
  });

  it('renders a vintage mismatch with the soft-confirm line', async () => {
    identifyBottle.mockResolvedValue({
      status: 'vintage_mismatch',
      wine: { id: 'w1', name: 'Esprit de Tablas', brand: 'Tablas Creek', vintage_year: 2021, region: 'Paso Robles' },
      read_vintage: '2019',
    });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText('Esprit de Tablas')).toBeInTheDocument();
    expect(screen.getByText(/2021/)).toBeInTheDocument();
    expect(screen.getByText(/2019/)).toBeInTheDocument();
  });

  it('renders a candidates list and navigates on tapping one', async () => {
    identifyBottle.mockResolvedValue({
      status: 'candidates',
      candidates: [
        { id: 'w1', name: 'Bramare Malbec', vintage_year: 2022, region: 'Uco Valley' },
        { id: 'w2', name: 'Bramare Malbec', vintage_year: 2023, region: 'Uco Valley' },
      ],
    });
    renderScreen();
    selectPhoto();
    await screen.findByText(/2022/);
    fireEvent.click(screen.getByText(/2023/));
    expect(mockNavigate).toHaveBeenCalledWith('/wine/w2');
  });

  it('renders the unstocked state with no card and no dead end', async () => {
    identifyBottle.mockResolvedValue({ status: 'unstocked', read: { producer: 'Cobos', wine_name: 'Volturno' } });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/Volturno/i)).toBeInTheDocument();
    expect(screen.getByTestId('identify-retake')).toBeInTheDocument();
  });

  it('renders the unreadable state with a retake tip', async () => {
    identifyBottle.mockResolvedValue({ status: 'unreadable' });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/whole front label/i)).toBeInTheDocument();
  });

  it('renders the not_wine state', async () => {
    identifyBottle.mockResolvedValue({ status: 'not_wine' });
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/not.*wine/i)).toBeInTheDocument();
  });

  it('renders an error state on a rejected call, with retry resetting to idle', async () => {
    identifyBottle.mockRejectedValue(new Error('Couldn’t reach the vision service — try again.'));
    renderScreen();
    selectPhoto();
    expect(await screen.findByText(/try again/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('identify-retake'));
    expect(screen.getByTestId('identify-file-input')).toBeInTheDocument();
  });
});
