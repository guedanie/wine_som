// frontend/src/components/__tests__/components.test.jsx
import { render, screen, fireEvent } from '@testing-library/react';
import WineCard from '../WineCard.jsx';
import StructureBars from '../StructureBars.jsx';
import Poster from '../Poster.jsx';
import Tag from '../Tag.jsx';
import Btn from '../Btn.jsx';
import Eyebrow from '../Eyebrow.jsx';

const wine = {
  wine_id: 'uuid-1',
  name: 'Esprit de Tablas',
  price: 55,
  retailer: "Spec's",
  why: 'Great structure.',
  tagline: 'PASO ROBLES',
  coord: '35.6°N · 120.7°W',
  flavors: ['dark cherry', 'garrigue'],
};

describe('WineCard', () => {
  it('renders wine name', () => {
    render(<WineCard wine={wine} />);
    expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
  });
  it('renders formatted price', () => {
    render(<WineCard wine={wine} />);
    expect(screen.getByText('$55')).toBeInTheDocument();
  });
  it('renders flavor tags', () => {
    render(<WineCard wine={wine} />);
    expect(screen.getByText('dark cherry')).toBeInTheDocument();
  });
  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<WineCard wine={wine} onClick={onClick} />);
    fireEvent.click(screen.getByText('Esprit de Tablas'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
  it('renders without flavors (empty array)', () => {
    render(<WineCard wine={{ ...wine, flavors: [] }} />);
    expect(screen.getByText('Esprit de Tablas')).toBeInTheDocument();
  });

  describe('WineCard feedback thumbs', () => {
    it('renders thumb buttons when onVote is provided', () => {
      render(<WineCard wine={wine} onVote={() => {}} vote={null} />);
      expect(screen.getByTitle('Good pick')).toBeInTheDocument();
      expect(screen.getByTitle('Not for me')).toBeInTheDocument();
    });

    it('does not render thumb buttons when onVote is absent', () => {
      render(<WineCard wine={wine} />);
      expect(screen.queryByTitle('Good pick')).not.toBeInTheDocument();
    });

    it('calls onVote with "up" when up thumb is clicked', () => {
      const onVote = vi.fn();
      render(<WineCard wine={wine} onVote={onVote} vote={null} />);
      fireEvent.click(screen.getByTitle('Good pick'));
      expect(onVote).toHaveBeenCalledWith('up');
    });

    it('calls onVote with "down" when down thumb is clicked', () => {
      const onVote = vi.fn();
      render(<WineCard wine={wine} onVote={onVote} vote={null} />);
      fireEvent.click(screen.getByTitle('Not for me'));
      expect(onVote).toHaveBeenCalledWith('down');
    });

    it('thumb click does not bubble to card onClick', () => {
      const onVote = vi.fn();
      const onClick = vi.fn();
      render(<WineCard wine={wine} onClick={onClick} onVote={onVote} vote={null} />);
      fireEvent.click(screen.getByTitle('Good pick'));
      expect(onVote).toHaveBeenCalled();
      expect(onClick).not.toHaveBeenCalled();
    });
  });
});

describe('StructureBars', () => {
  const items = [['Body', 'Med-Full', 0.8], ['Tannin', 'Firm', 0.7]];

  describe('ruler variant (default)', () => {
    it('renders all labels', () => {
      render(<StructureBars items={items} />);
      expect(screen.getByText('Body')).toBeInTheDocument();
      expect(screen.getByText('Tannin')).toBeInTheDocument();
    });
    it('renders numeric value markers', () => {
      render(<StructureBars items={items} />);
      expect(screen.getByText('80')).toBeInTheDocument();
      expect(screen.getByText('70')).toBeInTheDocument();
    });
  });

  describe('segmented variant', () => {
    it('renders all labels', () => {
      render(<StructureBars items={items} variant="segmented" />);
      expect(screen.getByText('Body')).toBeInTheDocument();
      expect(screen.getByText('Tannin')).toBeInTheDocument();
    });
    it('renders scale labels Low/Med/High/Max', () => {
      render(<StructureBars items={items} variant="segmented" />);
      expect(screen.getAllByText('Low').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Max').length).toBeGreaterThan(0);
    });
    it('renders numeric value right of label', () => {
      render(<StructureBars items={items} variant="segmented" />);
      // 0.8 * 100 = 80, 0.7 * 100 = 70
      expect(screen.getByText('80')).toBeInTheDocument();
    });
  });
});

describe('Poster', () => {
  it('shows img element for a known Tier 1 region', () => {
    render(<Poster region="Tuscany" />);
    expect(screen.getByRole('img', { name: /tuscany/i })).toBeInTheDocument();
  });
  it('shows region name text in placeholder for unknown region', () => {
    render(<Poster region="Unknown Region" />);
    expect(screen.getByText('Unknown Region')).toBeInTheDocument();
  });
  it('shows country eyebrow above poster for known region', () => {
    render(<Poster region="Tuscany" />);
    expect(screen.getByText('Italy')).toBeInTheDocument();
  });
  it('shows region name in footer for known region', () => {
    render(<Poster region="Paso Robles" />);
    // The serif footer name — there will be two matches (eyebrow header + footer)
    // so just check at least one is present
    expect(screen.getAllByText('Paso Robles').length).toBeGreaterThan(0);
  });
  it('shows subregion in footer for known region', () => {
    render(<Poster region="Tuscany" />);
    expect(screen.getByText(/Chianti/i)).toBeInTheDocument();
  });
});

describe('Tag', () => {
  it('renders children', () => {
    render(<Tag>dark cherry</Tag>);
    expect(screen.getByText('dark cherry')).toBeInTheDocument();
  });
});

describe('Btn', () => {
  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<Btn onClick={onClick}>Find wines</Btn>);
    fireEvent.click(screen.getByText('Find wines'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
  it('does not call onClick when disabled', () => {
    const onClick = vi.fn();
    render(<Btn onClick={onClick} disabled>Find wines</Btn>);
    fireEvent.click(screen.getByText('Find wines'));
    expect(onClick).not.toHaveBeenCalled();
  });
  it('renders ghost variant without error', () => {
    render(<Btn variant="ghost">Ghost</Btn>);
    expect(screen.getByText('Ghost')).toBeInTheDocument();
  });
});

describe('Eyebrow', () => {
  it('renders children', () => {
    render(<Eyebrow>The sommelier</Eyebrow>);
    expect(screen.getByText('The sommelier')).toBeInTheDocument();
  });
});
