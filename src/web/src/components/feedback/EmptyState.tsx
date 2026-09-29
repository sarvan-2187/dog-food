import type { ReactNode } from 'react';

/**
 * DESIGN_SYSTEM.md 7.7. Says why it is empty and what to do next. The action
 * is passed in only when the current role can actually act (PLAN.md 4.2).
 */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-prose flex-col items-center gap-3 px-4 py-12 text-center">
      <h3 className="text-h3 text-ink-800">{title}</h3>
      <p className="text-body text-ink-600">{description}</p>
      {action}
    </div>
  );
}
