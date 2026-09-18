import type { ReactNode } from 'react';
import { Link, NavLink, useSearchParams } from 'react-router-dom';
import { cn } from '../../lib/cn';
import { RaptorMark } from '../ui/Logo';

/**
 * Split-screen shell shared by /login and /register: a full-bleed photo panel
 * on the left, the form on the right, with tabs that swap between the two
 * routes without the visitor ever leaving the screen they are looking at.
 *
 * The layout follows the reference; the palette deliberately does not. The
 * reference is a saturated purple/green brand, while HackFlow's tokens are
 * monochrome ink-on-white by design (src/styles/tokens.ts) - copying the
 * reference's colours here would leave the auth screens as the one place in
 * the app that doesn't look like the app.
 *
 * This renders its own <header>, because the global pill nav hides itself on
 * these two routes (it would collide with the photo panel and duplicate the
 * wordmark) and every page still owes the page a banner landmark.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  const [searchParams] = useSearchParams();
  // Carry ?next= across the tab swap, so bouncing between the two tabs doesn't
  // silently drop where the visitor was originally headed.
  const next = searchParams.get('next');
  const withNext = (path: string) => (next ? `${path}?next=${encodeURIComponent(next)}` : path);

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex-1 rounded-full px-4 py-2.5 text-center text-label transition-colors duration-fast',
      isActive ? 'bg-surface-0 text-ink-900 shadow-sm' : 'text-ink-500 hover:text-ink-800',
    );

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Photo panel: decorative, so it is hidden from assistive tech and from
          small viewports where it would just push the form below the fold. */}
      <aside aria-hidden="true" className="relative hidden overflow-hidden bg-ink-900 lg:block">
        <img
          src="/images/community/hero-hack-room.jpg"
          alt=""
          className="absolute inset-0 h-full w-full object-cover opacity-70"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-ink-900 via-ink-900/55 to-ink-900/25" />
        <div className="relative flex h-full flex-col justify-end p-10 xl:p-14">
          <p className="max-w-[18ch] text-display text-surface-0">
            Build. Ship. <span className="font-serif italic">Get judged fairly.</span>
          </p>
          <p className="mt-5 max-w-[46ch] text-body-lg text-surface-0/75">
            Conflict-aware judge assignment, locked rubrics, and normalized scores — so the
            team that built the best thing actually wins.
          </p>
        </div>
      </aside>

      <main className="flex flex-col bg-surface-0">
        <header className="px-6 pt-8 md:px-10">
          <Link to="/" aria-label="HackFlow home" className="inline-flex items-center gap-2.5 text-ink-900">
            <RaptorMark className="h-6 w-12" />
            <span className="text-h3 tracking-tight">
              Hack<span className="font-serif italic">Flow</span>
            </span>
          </Link>
        </header>

        <div className="flex flex-1 items-center justify-center px-6 py-10 md:px-10">
          <div className="w-full max-w-[420px]">
            <h1 className="text-h1 text-ink-900">{title}</h1>
            <p className="mt-2 text-body text-ink-500">{subtitle}</p>

            <nav aria-label="Account" className="mt-7 flex gap-1 rounded-full bg-surface-100 p-1">
              <NavLink to={withNext('/login')} className={tabClass}>
                Sign in
              </NavLink>
              <NavLink to={withNext('/register')} className={tabClass}>
                Create account
              </NavLink>
            </nav>

            <div className="mt-6">{children}</div>

            <div className="mt-8 border-t border-border-subtle pt-5 text-meta text-ink-500">{footer}</div>
          </div>
        </div>
      </main>
    </div>
  );
}
