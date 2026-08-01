// frontend/src/components/__tests__/CompareFrame.test.jsx
import { render, screen } from '@testing-library/react';
import CompareFrame from '../CompareFrame.jsx';

const A = { wine_id: 'a', name: 'Caymus Cabernet', price: 89,
            structure_profile: { body: 5, tannins: 4 } };
const B = { wine_id: 'b', name: 'Bonanza Cabernet', price: 21,
            structure_profile: { body: 4, tannins: 3 } };

it('renders both columns with price/body/tannin rows and flags the winner', () => {
  render(<CompareFrame picks={[A, B]} />);
  expect(screen.getByText('Caymus Cabernet')).toBeInTheDocument();
  expect(screen.getByText('Bonanza Cabernet')).toBeInTheDocument();
  expect(screen.getByText('$89')).toBeInTheDocument();
  expect(screen.getByText('$21')).toBeInTheDocument();
  expect(screen.getByText('MINE')).toBeInTheDocument();
  expect(screen.getAllByText('Full')).toHaveLength(2);    // body 5 and 4 both map Full
  expect(screen.getByText('Firm')).toBeInTheDocument();   // tannins 4
  expect(screen.getByText('Medium')).toBeInTheDocument(); // tannins 3
});

it('omits a row when neither pick has the datum, renders nothing under 2 picks', () => {
  render(<CompareFrame picks={[
    { ...A, price: null, structure_profile: { body: 5 } },
    { ...B, price: null, structure_profile: { body: 4 } },
  ]} />);
  expect(screen.queryByText('PRICE')).toBeNull();
  expect(screen.queryByText('TANNIN')).toBeNull();
  expect(screen.getAllByText('BODY')).toHaveLength(2);

  const solo = render(<CompareFrame picks={[A]} />);
  expect(solo.container.firstChild).toBeNull();
});
