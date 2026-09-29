import { useEffect, useRef } from 'react';
import { useAuth } from '../lib/auth-context';
import { hasSeenTour, runTour } from '../lib/tour';

/**
 * Starts the role-appropriate tour the first time someone signs in on this
 * browser (PLAN.md Phase 8). Renders nothing.
 *
 * The short delay lets the page it landed on finish its first data fetch, so
 * page-specific anchors are in the DOM before tour.ts filters steps by which
 * selectors actually resolved. A missed anchor only costs that one step, so
 * this is a "make it likelier" delay, not a correctness dependency.
 */
export function GuidedTour() {
  const { user, status } = useAuth();
  const startedFor = useRef<string | null>(null);

  useEffect(() => {
    if (status !== 'ready' || !user) return;
    if (startedFor.current === user.role || hasSeenTour(user.role)) return;

    startedFor.current = user.role;
    const timer = setTimeout(() => runTour(user.role), 700);
    return () => clearTimeout(timer);
  }, [user, status]);

  return null;
}
