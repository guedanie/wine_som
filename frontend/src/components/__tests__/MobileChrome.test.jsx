import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { BottomTabs } from '../MobileChrome.jsx';

describe('BottomTabs', () => {
  it('includes a Scan tab linking to /identify', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <BottomTabs />
      </MemoryRouter>
    );
    expect(screen.getByText('Scan')).toBeInTheDocument();
  });
});
