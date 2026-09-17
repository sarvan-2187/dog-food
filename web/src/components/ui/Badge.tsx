import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

export type Status = 'danger' | 'warning' | 'success' | 'info' | 'neutral';
export type Role = 'participant' | 'judge' | 'organizer' | 'admin';

const STATUS: Record<Status, string> = {
  danger: 'bg-danger-bg text-danger-fg',
  warning: 'bg-warning-bg text-warning-fg',
  success: 'bg-success-bg text-success-fg',
  info: 'bg-info-bg text-info-fg',
  neutral: 'bg-surface-100 text-ink-700 border border-border',
};

const ROLE: Record<Role, string> = {
  participant: 'bg-surface-100 text-ink-700 border border-border',
  judge: 'bg-brand-100 text-brand-700 border border-brand-500/20',
  organizer: 'bg-navy-800 text-surface-0',
  admin: 'bg-navy-800 text-surface-0',
};

const base =
  'inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-eyebrow uppercase tracking-[0.06em]';

/**
 * DESIGN_SYSTEM.md 7.5 / 2.5. The label text is mandatory - colour is never
 * the only signal (PLAN.md 4.5).
 */
export function Badge({
  status = 'neutral',
  children,
  className,
}: {
  status?: Status;
  children: ReactNode;
  className?: string;
}) {
  return <span className={cn(base, STATUS[status], className)}>{children}</span>;
}

export function RoleBadge({ role, className }: { role: Role; className?: string }) {
  return (
    <span className={cn(base, ROLE[role], className)}>
      {role === 'admin' && <span aria-hidden="true">&#9873;</span>}
      {role}
    </span>
  );
}
