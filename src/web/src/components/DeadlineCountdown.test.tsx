import { describe, expect, it, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { DeadlineCountdown } from './DeadlineCountdown';

afterEach(cleanup);

/**
 * The regression this pins down: the API used to serialise deadlines without an
 * offset ("2026-09-21T18:00:00"), which `new Date()` reads as *local* time. The
 * countdown then drifted from the deadline the server actually enforces - by
 * 5.5h in IST, in the direction that tells a participant they still have time.
 */
describe('DeadlineCountdown', () => {
  it('reads a UTC-marked deadline as UTC, not as local time', () => {
    const inTwoHours = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString();
    render(<DeadlineCountdown endAt={inTwoHours} />);
    expect(screen.getByText(/1h 59m remaining|2h 0m remaining/)).toBeTruthy();
  });

  it('reports a past deadline as passed', () => {
    const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    render(<DeadlineCountdown endAt={yesterday} />);
    expect(screen.getByText(/Deadline passed/)).toBeTruthy();
  });

  it('shows days remaining for a deadline several days out', () => {
    const threeDays = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000 + 60_000).toISOString();
    render(<DeadlineCountdown endAt={threeDays} />);
    expect(screen.getByText(/3d 0h remaining/)).toBeTruthy();
  });

  it('carries a text label, so colour is never the only signal', () => {
    const past = new Date(Date.now() - 1000).toISOString();
    render(<DeadlineCountdown endAt={past} />);
    // PLAN.md 4.5: the status must survive being read without colour.
    expect(screen.getByText(/Deadline passed/).textContent).toContain('Deadline passed');
  });
});
