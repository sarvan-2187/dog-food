import { Button } from '../ui/Button';

/**
 * DESIGN_SYSTEM.md 7.7. Plain language only - never a status code or stack
 * trace in front of a user (PLAN.md 4.6).
 */
export function ErrorState({
  title = 'Something went wrong',
  description = 'We could not load this just now. Your work has not been lost.',
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="mx-auto flex max-w-prose flex-col items-center gap-3 px-4 py-12 text-center"
    >
      <span
        aria-hidden="true"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-danger-bg text-danger-fg"
      >
        !
      </span>
      <h3 className="text-h3 text-ink-800">{title}</h3>
      <p className="text-body text-ink-600">{description}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}
