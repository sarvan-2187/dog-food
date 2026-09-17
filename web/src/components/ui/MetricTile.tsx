import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

/**
 * DESIGN_SYSTEM.md 7.8. A dashboard headline number. `accent` turns the value
 * brand-500 for the one number a view is actually about (the reference does
 * this once, for the risk score) — never more than one per screen.
 */
export function MetricTile({
  label,
  value,
  caption,
  accent = false,
  className,
}: {
  label: string;
  value: ReactNode;
  caption?: string;
  accent?: boolean;
  className?: string;
}) {
  return (
    <div className={cn('rounded-lg border border-border bg-surface-0 p-card', className)}>
      <p className="text-eyebrow uppercase text-ink-400">{label}</p>
      <p className={cn('mt-2 text-h1 tabular-nums', accent ? 'text-brand-500' : 'text-ink-800')}>{value}</p>
      {caption && <p className="mt-1 text-meta text-ink-500">{caption}</p>}
    </div>
  );
}
