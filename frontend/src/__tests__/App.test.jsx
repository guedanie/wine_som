import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App.jsx';

describe('App routing', () => {
  it('renders the Identify screen at /identify', () => {
    render(
      <MemoryRouter initialEntries={['/identify']}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByTestId('identify-file-input')).toBeInTheDocument();
  });
});
