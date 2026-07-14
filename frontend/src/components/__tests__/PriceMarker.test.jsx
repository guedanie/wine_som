import { render, screen } from '@testing-library/react';
import PriceMarker from '../PriceMarker.jsx';
import PriceContextModule from '../PriceContextModule.jsx';

describe('PriceMarker', () => {
  it('drop variant carries amount, week anchor, and store', () => {
    render(<PriceMarker variant="drop" amount={5} store="H-E-B" />);
    expect(screen.getByText(/\$5 this week · H-E-B/)).toBeInTheDocument();
    expect(screen.getByText('↓')).toBeInTheDocument();
  });

  it('drop variant omits the store when context already names it', () => {
    render(<PriceMarker variant="drop" amount={4.5} />);
    expect(screen.getByText(/\$4\.50 this week/)).toBeInTheDocument();
    expect(screen.queryByText(/·/)).toBeNull();
  });

  it('steady variant reads as a cellar note', () => {
    render(<PriceMarker variant="steady" sinceLabel="since June" />);
    expect(screen.getByText(/steady since June/)).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('restock variant names the store', () => {
    render(<PriceMarker variant="restock" store="Spec's" />);
    expect(screen.getByText(/back in stock · Spec's/)).toBeInTheDocument();
  });

  it('watch variant says watching', () => {
    render(<PriceMarker variant="watch" />);
    expect(screen.getByText('watching')).toBeInTheDocument();
  });
});

const DROP_CTX = {
  variant: 'drop', amount: 5, from_price: 24.99, to_price: 19.99,
  store: 'H-E-B', since_label: 'this week', weeks_tracked: 6,
  strip: [24.99, 24.99, 24.99, 24.99, 24.99, 19.99],
  cheapest: { retailer: 'H-E-B', price: 19.99, delta_vs_next: 3.0 },
};

const STEADY_CTX = {
  variant: 'steady', amount: null, from_price: null, to_price: null,
  store: null, since_label: 'since June', weeks_tracked: 6,
  strip: [28, 28, 28, 28, 28, 28],
  cheapest: { retailer: "Spec's", price: 28, delta_vs_next: null },
};

describe('PriceContextModule', () => {
  it('drop state: prose lede with new price, store, was-price sub, drop chip', () => {
    render(<PriceContextModule ctx={DROP_CTX} />);
    expect(screen.getByText(/Down to/)).toBeInTheDocument();
    expect(screen.getByText(/\$19\.99/)).toBeInTheDocument();
    expect(screen.getByText(/at H-E-B/)).toBeInTheDocument();
    expect(screen.getByText(/Was \$24\.99/)).toBeInTheDocument();
    expect(screen.getByText(/Cheapest nearby by \$3/)).toBeInTheDocument();
    expect(screen.getByText(/\$5 this week/)).toBeInTheDocument();   // the chip
  });

  it('steady state: resolved, complete, no drop chip', () => {
    render(<PriceContextModule ctx={STEADY_CTX} />);
    expect(screen.getByText(/\$28 at Spec's/)).toBeInTheDocument();
    expect(screen.getByText(/steady so far/)).toBeInTheDocument();
    expect(screen.getByText(/the week it drops/)).toBeInTheDocument();
    expect(screen.queryByText('↓')).toBeNull();
    expect(screen.getByText(/steady since June/)).toBeInTheDocument(); // steady chip
  });

  it('shows the weekly-checks caption', () => {
    render(<PriceContextModule ctx={DROP_CTX} />);
    expect(screen.getByText(/6 weekly checks/)).toBeInTheDocument();
  });

  it('renders nothing without a context', () => {
    const { container } = render(<PriceContextModule ctx={null} />);
    expect(container.firstChild).toBeNull();
  });
});
