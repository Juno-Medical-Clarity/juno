import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConfigurationCard from './ConfigurationCard';

// No firebase imports in ConfigurationCard, but mock for safety
vi.mock('../api/firebase', () => ({
  firebaseAuth: { currentUser: null },
  API_URL: 'http://localhost:8082',
}));

describe('ConfigurationCard', () => {
  it('renders the "Enable grading" label', () => {
    render(<ConfigurationCard gradingEnabled={false} onGradingEnabledChange={() => {}} />);
    expect(screen.getByText('Enable grading')).toBeInTheDocument();
  });

  it('renders the grading checkbox as unchecked when gradingEnabled=false', () => {
    render(<ConfigurationCard gradingEnabled={false} onGradingEnabledChange={() => {}} />);
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();
  });

  it('renders the grading checkbox as checked when gradingEnabled=true', () => {
    render(<ConfigurationCard gradingEnabled={true} onGradingEnabledChange={() => {}} />);
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toBeChecked();
  });

  it('calls onGradingEnabledChange(true) when unchecked checkbox is clicked', async () => {
    const user = userEvent.setup();
    const onGradingEnabledChange = vi.fn();

    render(<ConfigurationCard gradingEnabled={false} onGradingEnabledChange={onGradingEnabledChange} />);
    const checkbox = screen.getByRole('checkbox');

    await user.click(checkbox);
    expect(onGradingEnabledChange).toHaveBeenCalledOnce();
    expect(onGradingEnabledChange).toHaveBeenCalledWith(true);
  });

  it('calls onGradingEnabledChange(false) when checked checkbox is clicked', async () => {
    const user = userEvent.setup();
    const onGradingEnabledChange = vi.fn();

    render(<ConfigurationCard gradingEnabled={true} onGradingEnabledChange={onGradingEnabledChange} />);
    const checkbox = screen.getByRole('checkbox');

    await user.click(checkbox);
    expect(onGradingEnabledChange).toHaveBeenCalledOnce();
    expect(onGradingEnabledChange).toHaveBeenCalledWith(false);
  });
});
