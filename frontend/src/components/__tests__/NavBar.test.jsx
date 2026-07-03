import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NavBar from '../NavBar.jsx';

it('renders the Somm wordmark as a link', () => {
  render(<MemoryRouter><NavBar /></MemoryRouter>);
  expect(screen.getByRole('link', { name: /somm/i })).toBeInTheDocument();
});

it('renders a Recommend nav link', () => {
  render(<MemoryRouter><NavBar /></MemoryRouter>);
  expect(screen.getByRole('link', { name: /recommend/i })).toBeInTheDocument();
});

it('renders a Discover nav link', () => {
  render(<MemoryRouter><NavBar /></MemoryRouter>);
  expect(screen.getByRole('link', { name: /discover/i })).toBeInTheDocument();
});
