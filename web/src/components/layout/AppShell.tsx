import {
  Bell,
  CalendarDays,
  CirclePlus,
  ClipboardCheck,
  Images,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeft,
  User,
  Users,
  UsersRound,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';
import { cn } from '../../lib/cn';
import type { Announcement, EventRecord, JudgeProgress, Team, User as Account } from '../../types';
import { eventPhase } from '../EventTimeline';
import { RoleBadge } from '../ui';
import { RaptorMark } from '../ui/Logo';
import { NavBar } from './NavBar';

/**
 * The signed-in frame: a sidebar of role-aware links, a slim top bar with the
 * page title, one live status chip, the role badge and an announcements bell,
 * and the page itself on the right. Signed-out visitors, the landing page and
 * the auth screens keep the pill NavBar instead (App.tsx decides).
 *
 * Link names and `data-tour` hooks match the old NavBar exactly: the guided
 * tour (lib/tour.ts) and the E2E suite find their targets by them. Below md the
 * sidebar becomes a drawer behind an "Open menu" button, the same label the
 * pill nav's hamburger used.
 */

type NavItem = { to: string; label: string; icon: LucideIcon; tour?: string };

function navFor(role: Account['role']): { label: string; items: NavItem[] }[] {
  const workspace: NavItem[] = [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, tour: 'nav-dashboard' }];
  if (role === 'participant') workspace.push({ to: '/teams/mine', label: 'My teams', icon: UsersRound, tour: 'nav-teams' });
  if (role === 'judge') workspace.push({ to: '/judge', label: 'Judging', icon: ClipboardCheck, tour: 'nav-judge' });
  if (role === 'organizer' || role === 'admin') {
    workspace.push({ to: '/events/new', label: 'Create event', icon: CirclePlus, tour: 'nav-create-event' });
  }
  if (role === 'admin') workspace.push({ to: '/admin/users', label: 'Users', icon: Users, tour: 'nav-users' });
  return [
    { label: 'Workspace', items: workspace },
    {
      label: 'Explore',
      items: [
        { to: '/events', label: 'Events', icon: CalendarDays, tour: 'nav-events' },
        { to: '/gallery', label: 'Gallery', icon: Images, tour: 'nav-gallery' },
      ],
    },
  ];
}

/** Shown in the top bar. Deliberately not a heading: each page owns its h1. */
export function pageTitle(path: string): string {
  const rules: [RegExp, string][] = [
    [/^\/dashboard/, 'Dashboard'],
    [/^\/events\/new/, 'Create event'],
    [/^\/events\/[^/]+\/rubric/, 'Judging rubric'],
    [/^\/events\/[^/]+\/settings/, 'Event settings'],
    [/^\/events\/[^/]+\/results/, 'Assignments & results'],
    [/^\/events\/[^/]+\/gallery/, 'Gallery'],
    [/^\/events\/[^/]+/, 'Event'],
    [/^\/events/, 'Events'],
    [/^\/gallery/, 'Gallery'],
    [/^\/judge-invite/, 'Judge invitation'],
    [/^\/judge/, 'Judging'],
    [/^\/assignments/, 'Score a project'],
    [/^\/submissions/, 'Project'],
    [/^\/teams\/mine/, 'My teams'],
    [/^\/teams/, 'Your submission'],
    [/^\/join/, 'Join a team'],
    [/^\/profile/, 'Profile'],
    [/^\/admin\/users/, 'Users'],
  ];
  return rules.find(([re]) => re.test(path))?.[1] ?? 'HackFlow';
}

const COLLAPSE_KEY = 'hackflow.sidebar.collapsed';

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1';
  } catch {
    return false;
  }
}

const iconButton =
  'inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-surface-0 text-ink-700 transition-colors duration-fast hover:bg-surface-100 focus:outline-none focus-visible:ring-[3px] focus-visible:ring-brand-500/20';

/** Routes that keep the pill nav even when signed in: the marketing page and
 * the auth screens, which carry their own chrome. */
const PILL_ROUTES = ['/', '/login', '/register'];

/**
 * Chooses the chrome: the sidebar shell when signed in, the pill NavBar
 * otherwise. The page (`children`) sits at the same position in the tree in
 * both, so signing in mid-page (a password reset, say) swaps the frame around
 * it without remounting it and losing its state.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => setDrawerOpen(false), [pathname]);

  function toggleCollapsed() {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1');
      } catch {
        /* per-browser convenience only */
      }
      return !c;
    });
  }

  const shell = user !== null && !PILL_ROUTES.includes(pathname);

  return (
    <div className={shell ? 'flex min-h-screen bg-surface-50' : 'min-h-screen'}>
      {shell && (
        <aside
          className={cn(
            'sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border-subtle bg-surface-0 transition-[width] duration-base ease-standard md:flex',
            collapsed ? 'w-[76px]' : 'w-64',
          )}
        >
          <SidebarContent user={user!} collapsed={collapsed} />
        </aside>
      )}

      {shell && drawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-ink-900/40"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-surface-0 shadow-lg">
            <SidebarContent user={user!} collapsed={false} />
          </aside>
        </div>
      )}

      <div className={shell ? 'flex min-w-0 flex-1 flex-col' : undefined}>
        {shell ? (
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border-subtle bg-surface-0/90 px-4 backdrop-blur md:px-6">
          <button
            type="button"
            aria-label="Open menu"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
            className={cn(iconButton, 'md:hidden')}
          >
            <Menu size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-pressed={collapsed}
            onClick={toggleCollapsed}
            className={cn(iconButton, 'hidden md:inline-flex')}
          >
            <PanelLeft size={18} aria-hidden="true" />
          </button>
          <p className="min-w-0 truncate text-body text-ink-800">{pageTitle(pathname)}</p>

          <div className="ml-auto flex items-center gap-2">
            <StatusChip user={user!} />
            <RoleBadge role={user!.role} className="hidden sm:inline-flex" />
            <AnnouncementsBell />
          </div>
        </header>
        ) : (
          <NavBar />
        )}
        {/* Always a div, so the page never changes element type (and remounts)
            when the frame switches; only the shell gives it the main landmark,
            since the auth screens bring their own <main>. */}
        <div role={shell ? 'main' : undefined} className={shell ? 'flex-1' : undefined}>
          {children}
        </div>
      </div>
    </div>
  );
}

function SidebarContent({ user, collapsed }: { user: Account; collapsed: boolean }) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-body transition-colors duration-fast',
      'focus:outline-none focus-visible:ring-[3px] focus-visible:ring-brand-500/20',
      collapsed && 'justify-center px-0',
      isActive ? 'bg-surface-100 text-ink-900' : 'text-ink-600 hover:bg-surface-100 hover:text-ink-900',
    );

  async function signOut() {
    await logout();
    navigate('/login');
  }

  return (
    <>
      <Link
        to="/dashboard"
        aria-label="HackFlow home"
        className={cn('flex h-16 shrink-0 items-center gap-2 px-5 text-ink-900', collapsed && 'justify-center px-0')}
      >
        <RaptorMark className="h-5 w-10" />
        {!collapsed && (
          <span className="text-h3">
            Hack<span className="font-serif italic">Flow</span>
          </span>
        )}
      </Link>

      <nav aria-label="Main" className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 py-4">
        {navFor(user.role).map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            {collapsed ? (
              <span className="mx-auto mb-1 h-px w-6 bg-border-subtle" aria-hidden="true" />
            ) : (
              <p className="px-3 pb-1 text-eyebrow uppercase text-ink-400">{group.label}</p>
            )}
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/events'}
                data-tour={item.tour}
                className={linkClass}
                title={collapsed ? item.label : undefined}
              >
                <item.icon size={18} aria-hidden="true" className="shrink-0" />
                <span className={cn(collapsed && 'sr-only')}>{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-1 border-t border-border-subtle px-3 py-4">
        <NavLink to="/profile" data-tour="nav-profile" className={linkClass} title={collapsed ? 'Profile' : undefined}>
          <User size={18} aria-hidden="true" className="shrink-0" />
          <span className={cn(collapsed && 'sr-only')}>Profile</span>
        </NavLink>
        <button
          type="button"
          onClick={signOut}
          title={collapsed ? 'Log out' : undefined}
          className={cn(linkClass({ isActive: false }), 'text-danger-fg hover:text-danger-fg')}
        >
          <LogOut size={18} aria-hidden="true" className="shrink-0" />
          <span className={cn(collapsed && 'sr-only')}>Log out</span>
        </button>
      </div>
    </>
  );
}

/** One live number per role, from endpoints that already exist. */
function StatusChip({ user }: { user: Account }) {
  const [text, setText] = useState<string | null>(null);
  const { pathname } = useLocation();

  useEffect(() => {
    let cancelled = false;
    const set = (t: string | null) => {
      if (!cancelled) setText(t);
    };
    const now = Date.now();
    (async () => {
      try {
        if (user.role === 'judge') {
          const p = await api.get<JudgeProgress>('/api/judge/assignments');
          set(p.total ? `${p.completed} of ${p.total} scored` : null);
        } else if (user.role === 'participant') {
          const [teams, events] = await Promise.all([
            api.get<Team[]>('/api/teams/mine'),
            api.get<EventRecord[]>('/api/events'),
          ]);
          const mine = new Set(teams.map((t) => t.event_id));
          const next = events
            .filter((e) => mine.has(e.id) && new Date(e.end_at).getTime() > now)
            .sort((a, b) => new Date(a.end_at).getTime() - new Date(b.end_at).getTime())[0];
          set(next ? `Closes in ${untilText(new Date(next.end_at).getTime() - now)}` : null);
        } else if (user.role === 'organizer') {
          const events = await api.get<EventRecord[]>('/api/events');
          const open = events.filter((e) => e.created_by_id === user.id && eventPhase(e, now) === 'open');
          set(`${open.length} open now`);
        } else {
          const page = await api.get<{ total: number }>('/api/admin/users');
          set(`${page.total} accounts`);
        }
      } catch {
        set(null); // a chip is a nicety; the page itself reports real failures
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user.id, user.role, pathname]);

  if (!text) return null;
  return (
    <span className="tabular hidden items-center rounded-full border border-border bg-surface-0 px-3 py-1 text-meta text-ink-700 sm:inline-flex">
      {text}
    </span>
  );
}

function untilText(ms: number): string {
  const hours = Math.floor(ms / 3_600_000);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}d ${hours % 24}h`;
  return `${hours}h ${Math.floor((ms % 3_600_000) / 60_000)}m`;
}

function AnnouncementsBell() {
  const [items, setItems] = useState<Announcement[] | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .get<Announcement[]>('/api/announcements/mine')
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [open]);

  const count = items?.length ?? 0;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={count ? `Announcements (${count})` : 'Announcements'}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={cn(iconButton, 'relative rounded-full')}
      >
        <Bell size={17} aria-hidden="true" />
        {count > 0 && <span aria-hidden="true" className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-danger-solid" />}
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-surface-0 p-2 shadow-lg">
          <p className="px-2 pb-2 pt-1 text-eyebrow uppercase text-ink-400">Announcements</p>
          {count === 0 ? (
            <p className="px-2 pb-2 text-meta text-ink-500">Nothing new from your events.</p>
          ) : (
            <ul className="flex max-h-80 flex-col overflow-y-auto">
              {items!.map((a) => (
                <li key={a.id}>
                  <Link
                    to={`/events/${a.event_slug}`}
                    onClick={() => setOpen(false)}
                    className="block rounded-md px-2 py-2 hover:bg-surface-100"
                  >
                    <span className="block text-label text-ink-900">{a.title}</span>
                    <span className="line-clamp-2 block text-meta text-ink-600">{a.body}</span>
                    <span className="block text-meta text-ink-400">{a.event_name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
