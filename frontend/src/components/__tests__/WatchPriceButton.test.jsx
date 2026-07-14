import { render, screen, fireEvent } from '@testing-library/react';
import WatchPriceButton from '../WatchPriceButton.jsx';
import PriceContextModule from '../PriceContextModule.jsx';

const mockAuth = { isConfigured: true, isWatched: vi.fn(() => false), toggleWatch: vi.fn() };
vi.mock('../../lib/auth.jsx', () => ({ useAuth: () => mockAuth }));

beforeEach(() => {
  mockAuth.isWatched = vi.fn(() => false);
  mockAuth.toggleWatch = vi.fn();
  mockAuth.isConfigured = true;
});

describe('WatchPriceButton', () => {
  it('ghost "Watch price" by default; click passes the wine to toggleWatch', () => {
    render(<WatchPriceButton wineId="w1" name="Esprit de Tablas" />);
    fireEvent.click(screen.getByText('Watch price'));
    expect(mockAuth.toggleWatch).toHaveBeenCalledWith({ wine_id: 'w1', name: 'Esprit de Tablas' });
  });

  it('flips to solid "Watching" when the wine is watched', () => {
    mockAuth.isWatched = vi.fn(() => true);
    render(<WatchPriceButton wineId="w1" name="X" />);
    expect(screen.getByText('Watching')).toBeInTheDocument();
  });

  it('renders nothing when auth is not configured — the affordance is account-bound', () => {
    mockAuth.isConfigured = false;
    const { container } = render(<WatchPriceButton wineId="w1" name="X" />);
    expect(container.firstChild).toBeNull();
  });
});

const CTX = {
  variant: 'steady', amount: null, from_price: null, to_price: null, store: null,
  since_label: 'since June', weeks_tracked: 6, strip: [28, 28, 28],
  cheapest: { retailer: "Spec's", price: 28, delta_vs_next: null },
};

describe('PriceContextModule watch slot — both layouts', () => {
  it('desktop module carries the watch button inline with the chip', () => {
    render(<PriceContextModule ctx={CTX} wineId="w1" wineName="X" />);
    expect(screen.getByText('Watch price')).toBeInTheDocument();
  });

  it('mobile (compact) module carries it full-width under the price', () => {
    render(<PriceContextModule ctx={CTX} compact wineId="w1" wineName="X" />);
    const btn = screen.getByText('Watch price').closest('button');
    expect(btn).toBeInTheDocument();
    expect(btn.style.width).toBe('100%');
  });
});
