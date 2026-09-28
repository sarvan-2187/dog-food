import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

/**
 * DESIGN_SYSTEM.md 7.3. Border, not shadow, is the default separation.
 *
 * Laid out as a full-height flex column so that when cards sit side by side in a
 * grid they line up: the grid already stretches each item to the tallest in the
 * row, but without `h-full` the card's own box stopped at its content, and
 * without `flex-1` on the body the footer floated up under short content instead
 * of sitting on the card's bottom edge. That is what made footer actions (the
 * gallery's vote buttons, "Explore feature" links) sit at different heights
 * across a row.
 *
 * `h-full` is inert where it isn't wanted: a percentage height against an
 * auto-height parent resolves to auto, so a card in ordinary block flow is
 * unaffected.
 */
export function Card({
  title,
  meta,
  media,
  footer,
  className,
  children,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  /**
   * Full-bleed art above the header (an event's cover, say). Sits outside the
   * padded body so it meets the card's edges, and above the title so a row of
   * cards lines its images up even when one title wraps to two lines and
   * another doesn't.
   */
  media?: ReactNode;
  footer?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn('flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface-0', className)}>
      {media}
      {(title || meta) && (
        <header className="flex items-baseline justify-between gap-4 border-b border-border-subtle px-card py-4">
          {title && <h3 className="text-h3 text-ink-800">{title}</h3>}
          {meta && <span className="text-meta text-ink-500">{meta}</span>}
        </header>
      )}
      <div className="flex-1 p-card">{children}</div>
      {footer && (
        <footer className="mt-auto rounded-b-lg border-t border-border-subtle bg-surface-100 px-card py-3 text-meta text-ink-500">
          {footer}
        </footer>
      )}
    </section>
  );
}
