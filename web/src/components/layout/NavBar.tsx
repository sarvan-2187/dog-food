import { useEffect, useId, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth-context';
import { Button, RoleBadge } from '../ui';

/**
 * DESIGN_SYSTEM.md 7.6, rebuilt to match raptors.dev's real header (live
 * self-check): a wordmark left, a single circular ink-filled button right —
 * no persistent inline nav links at any width. Clicking it opens a full-bleed
 * ink overlay (raptors.dev's real --menu-bg, #1F2426 at 90%) listing the
 * links. Role-aware: an item a role can't use is absent, not disabled
 * (PLAN.md 4.4).
 */
export function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const openButtonRef = useRef<HTMLButtonElement>(null);

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

  useEffect(() => {
    if (!open) return;
    closeButtonRef.current?.focus();
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open]);

  function closeAndReturnFocus() {
    setOpen(false);
    openButtonRef.current?.focus();
  }

  async function onLogout() {
    await logout();
    closeAndReturnFocus();
    navigate('/');
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border-subtle bg-surface-0">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between gap-4 px-4 md:px-6">
        <Link to="/" className="text-h3 lowercase tracking-tight text-ink-900">
          Dogfood 2026
        </Link>
        <div className="flex items-center gap-3">
          {user && (
            <>
              <RoleBadge role={user.role} className="hidden sm:inline-flex" />
              <span className="hidden text-label text-ink-700 md:inline">{user.name}</span>
            </>
          )}
          <button
            ref={openButtonRef}
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            aria-label={open ? 'Close menu' : 'Open menu'}
            onClick={() => setOpen(true)}
            className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full bg-brand-500 text-surface-0 transition-colors duration-fast hover:bg-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          >
            <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
            <span aria-hidden="true" className="flex flex-col items-center gap-[3px]">
              <span className="h-[2px] w-[18px] rounded-full bg-surface-0" />
              <span className="h-[2px] w-[18px] rounded-full bg-surface-0" />
              <span className="h-[2px] w-[18px] rounded-full bg-surface-0" />
            </span>
          </button>
        </div>
      </div>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-modal="true"
          aria-label="Site menu"
          className="fixed inset-0 z-50 flex flex-col bg-brand-500/90 px-4 py-6 text-surface-0 md:px-6"
        >
          <div className="mx-auto flex w-full max-w-[1200px] items-center justify-between">
            <Link to="/" onClick={closeAndReturnFocus} className="text-h3 lowercase tracking-tight text-surface-0">
              Dogfood 2026
            </Link>
            <button
              ref={closeButtonRef}
              type="button"
              aria-label="Close menu"
              onClick={closeAndReturnFocus}
              className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full bg-surface-0 text-brand-500 transition-colors duration-fast hover:bg-surface-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-surface-0 focus-visible:ring-offset-2 focus-visible:ring-offset-brand-500"
            >
              <span aria-hidden="true" className="text-h3 leading-none">
                &times;
              </span>
              <span className="sr-only">Close menu</span>
            </button>
          </div>

          <nav className="mx-auto flex w-full max-w-[1200px] flex-1 flex-col justify-center gap-5 overflow-y-auto py-6">
            {links.map((l) => (
              <Link
                key={l.to}
                to={l.to}
                onClick={closeAndReturnFocus}
                className="text-h2 text-surface-0 transition-opacity hover:opacity-70"
              >
                {l.label}
              </Link>
            ))}
          </nav>

          <div className="mx-auto flex w-full max-w-[1200px] items-center gap-3 border-t border-surface-0/20 pt-6">
            {user ? (
              <>
                <RoleBadge role={user.role} className="border-surface-0/40 bg-transparent text-surface-0" />
                <span className="text-label text-surface-0/80">{user.name}</span>
                <Button variant="secondary" size="sm" onClick={onLogout} className="ml-auto">
                  Log out
                </Button>
              </>
            ) : (
              <>
                <Link to="/login" onClick={closeAndReturnFocus} className="text-label text-surface-0">
                  Log in
                </Link>
                <Link to="/register" onClick={closeAndReturnFocus} className="ml-auto">
                  <Button variant="secondary" size="sm">
                    Sign up
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
