import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NavBar from '../NavBar.jsx';

it('renders the Terroir wordmark as a link', () => {
  render(<MemoryRouter><NavBar /></MemoryRouter>);
  expect(screen.getByRole('link', { name: /terroir/i })).toBeInTheDocument();
});

it('renders a Recommend nav link', () => {
  render(<MemoryRouter><NavBar /></MemoryRouter>);
  expect(screen.getByRole('link', { name: /recommend/i })).toBeInTheDocument();
});

it('renders a Discover nav link', () => {
  render(<MemoryRouter><NavBar /></MemoryRouter>);
  expect(screen.getByRole('link', { name: /discover/i })).toBeInTheDocument();
});
