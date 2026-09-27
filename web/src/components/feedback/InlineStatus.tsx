import { Spinner } from '../ui/Button';
import { cn } from '../../lib/cn';

export type SaveState = 'idle' | 'saving' | 'saved' | 'unsaved';

/**
 * DESIGN_SYSTEM.md 7.7. The autosave indicator required by PLAN.md 4.1 - the
 * user never has to guess whether their edits are safe.
 */
export function InlineStatus({ state, className }: { state: SaveState; className?: string }) {
  if (state === 'idle') return null;

  const content = {
    saving: (
      <>
        <Spinner className="h-3 w-3" /> Saving...
      </>
    ),
    saved: (
      <>
        <span aria-hidden="true">&#10003;</span> Saved
      </>
    ),
    unsaved: <>Unsaved changes</>,
  }[state];

  const tone = {
    saving: 'text-ink-500',
    saved: 'text-success-fg',
    unsaved: 'text-warning-fg',
  }[state];

  return (
    <span
      role="status"
      aria-live="polite"
      className={cn('inline-flex items-center gap-1.5 text-meta', tone, className)}
    >
      {content}
    </span>
  );
}
