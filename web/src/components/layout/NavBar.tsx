import { Home, Menu, X } from 'lucide-react';
import { useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useAuth } from '../../lib/auth-context';
import { cn } from '../../lib/cn';
import { Logo } from '../ui';

/**
 * Pill-style nav matching a reference screenshot exactly: a centered, rounded,
 * dark bar with a home icon and tab links, the current one highlighted as a
 * white pill against the dark bar. The HackFlow wordmark sits to its left (a
 * three-column grid keeps the pill mathematically centered regardless of the
 * wordmark's width, rather than the pill drifting off-center). No persistent
 * inline account controls - post-login actions (log out, etc.) live on
 * /profile, which appears as an ordinary tab once signed in. Role-aware: an
 * item a role can't use is absent, not disabled (PLAN.md 4.4).
 *
 * Below md the pill was overflowing into a horizontally-scrolling strip on
 * phone widths, so that breakpoint swaps it for a hamburger toggle that
 * opens a stacked link list instead.
 */
export function NavBar() {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  // `tour` anchors the guided tour's steps (src/lib/tour.ts) to a stable hook
  // rather than to link text or tab order, either of which is fair game to
  // reword or reorder later.
  const links: { to: string; label: string; tour?: string }[] = [
    { to: '/events', label: 'Events', tour: 'nav-events' },
    { to: '/gallery', label: 'Gallery', tour: 'nav-gallery' },
  ];
  if (user?.role === 'organizer' || user?.role === 'admin') {
    links.push({ to: '/events/new', label: 'Create event', tour: 'nav-create-event' });
  }
  if (user?.role === 'participant') {
    links.push({ to: '/teams/mine', label: 'My teams', tour: 'nav-teams' });
  }
  if (user?.role === 'judge') {
    links.push({ to: '/judge', label: 'Judging', tour: 'nav-judge' });
  }
  if (user) {
    links.push({ to: '/profile', label: 'Profile', tour: 'nav-profile' });
  } else {
    links.push({ to: '/login', label: 'Log in' }, { to: '/register', label: 'Sign up' });
  }

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-label uppercase tracking-wide transition-colors duration-fast',
      isActive ? 'bg-surface-0 text-ink-900' : 'text-surface-0/90 hover:text-surface-0',
    );

  const mobileTabClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'rounded-full px-4 py-2 text-label uppercase tracking-wide transition-colors duration-fast',
      isActive ? 'bg-surface-0 text-ink-900' : 'text-surface-0/90 hover:text-surface-0',
    );

  return (
    <header className="sticky top-0 z-40 bg-transparent px-4 py-4 md:px-6">
      <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-4 md:grid md:grid-cols-[1fr_auto_1fr]">
        <Link to="/" className="md:justify-self-start">
          <Logo />
        </Link>
        <nav
          aria-label="Primary"
          className="hidden w-fit max-w-full items-center gap-1 overflow-x-auto rounded-full bg-ink-700 p-1.5 md:flex md:justify-self-center"
        >
          <NavLink
            to="/"
            end
            aria-label="Home"
            className={({ isActive }) =>
              cn(
                'flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-colors duration-fast',
                isActive ? 'bg-surface-0 text-ink-900' : 'text-surface-0/90 hover:text-surface-0',
              )
            }
          >
            <Home size={16} aria-hidden="true" />
          </NavLink>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} data-tour={l.tour} className={tabClass}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-ink-700 text-surface-0 md:hidden"
        >
          {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
        </button>
        <div aria-hidden="true" className="hidden md:block" />
      </div>
      {menuOpen && (
        <nav
          aria-label="Primary mobile"
          className="mx-auto mt-3 flex max-w-[1200px] flex-col items-start gap-1 rounded-2xl bg-ink-700 p-3 md:hidden"
        >
          <NavLink to="/" end onClick={() => setMenuOpen(false)} className={mobileTabClass}>
            Home
          </NavLink>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} onClick={() => setMenuOpen(false)} className={mobileTabClass}>
              {l.label}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}
