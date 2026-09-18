import { Home } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../lib/auth-context';
import { cn } from '../../lib/cn';

/**
 * Rebuilt to match a reference pill-style nav exactly: a centered, rounded,
 * dark bar with a home icon and tab links, the current one highlighted as a
 * white pill against the dark bar. No hamburger, no persistent inline
 * account controls - post-login actions (log out, etc.) live on /profile,
 * which appears as an ordinary tab once signed in, per an explicit request.
 * Role-aware: an item a role can't use is absent, not disabled (PLAN.md 4.4).
 */
export function NavBar() {
  const { user } = useAuth();

  const links: { to: string; label: string }[] = [
    { to: '/events', label: 'Events' },
    { to: '/gallery', label: 'Gallery' },
  ];
  if (user?.role === 'organizer' || user?.role === 'admin') {
    links.push({ to: '/events/new', label: 'Create event' });
  }
  if (user?.role === 'participant') {
    links.push({ to: '/teams/mine', label: 'My teams' });
  }
  if (user?.role === 'judge') {
    links.push({ to: '/judge', label: 'Judging' });
  }
  if (user) {
    links.push({ to: '/profile', label: 'Profile' });
  } else {
    links.push({ to: '/login', label: 'Log in' }, { to: '/register', label: 'Sign up' });
  }

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-label uppercase tracking-wide transition-colors duration-fast',
      isActive ? 'bg-surface-0 text-ink-900' : 'text-surface-0/90 hover:text-surface-0',
    );

  return (
    <header className="sticky top-0 z-40 bg-surface-200 px-4 py-4 md:px-6">
      <nav
        aria-label="Primary"
        className="mx-auto flex w-fit max-w-full items-center gap-1 overflow-x-auto rounded-full bg-ink-700 p-1.5"
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
          <NavLink key={l.to} to={l.to} className={tabClass}>
            {l.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
