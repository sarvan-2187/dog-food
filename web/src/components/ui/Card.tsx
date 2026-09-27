import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

/** DESIGN_SYSTEM.md 7.3. Border, not shadow, is the default separation. */
export function Card({
  title,
  meta,
  footer,
  className,
  children,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  footer?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn('rounded-lg border border-border bg-surface-0', className)}>
      {(title || meta) && (
        <header className="flex items-baseline justify-between gap-4 border-b border-border-subtle px-card py-4">
          {title && <h3 className="text-h3 text-ink-800">{title}</h3>}
          {meta && <span className="text-meta text-ink-500">{meta}</span>}
        </header>
      )}
      <div className="p-card">{children}</div>
      {footer && (
        <footer className="rounded-b-lg border-t border-border-subtle bg-surface-100 px-card py-3 text-meta text-ink-500">
          {footer}
        </footer>
      )}
    </section>
  );
}
