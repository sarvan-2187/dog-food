import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth-context';
import { Button, RoleBadge } from '../ui';

/** DESIGN_SYSTEM.md 7.6 - role-aware nav: absent, not disabled (PLAN.md 4.4). */
export function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

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

  async function onLogout() {
    await logout();
    navigate('/');
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border-subtle bg-surface-0">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between gap-4 px-4 md:px-6">
        <Link to="/" className="text-h3 text-ink-900">
          Dogfood 2026
        </Link>
        <nav className="hidden flex-1 items-center gap-6 md:flex">
          {links.map((l) => (
            <Link key={l.to} to={l.to} className="text-label text-ink-700 hover:text-ink-900">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          {user ? (
            <>
              <RoleBadge role={user.role} />
              <span className="hidden text-label text-ink-700 md:inline">{user.name}</span>
              <Button variant="ghost" size="sm" onClick={onLogout}>
                Log out
              </Button>
            </>
          ) : (
            <>
              <Link to="/login">
                <Button variant="ghost" size="sm">
                  Log in
                </Button>
              </Link>
              <Link to="/register">
                <Button variant="primary" size="sm">
                  Sign up
                </Button>
              </Link>
            </>
          )}
        </div>
      </div>
      <nav className="flex gap-4 overflow-x-auto border-t border-border-subtle px-4 py-2 md:hidden">
        {links.map((l) => (
          <Link key={l.to} to={l.to} className="whitespace-nowrap text-label text-ink-700">
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
