import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import type { Status } from '../ui/Badge';

type ToastStatus = Exclude<Status, 'neutral'>;

const ACCENT: Record<ToastStatus, string> = {
  danger: 'border-l-danger-fg',
  warning: 'border-l-warning-fg',
  success: 'border-l-success-fg',
  info: 'border-l-brand-500',
};

export interface ToastProps {
  status: ToastStatus;
  message: string;
  onDismiss: () => void;
}

/**
 * DESIGN_SYSTEM.md 7.7. Success/info auto-dismiss after 5s; errors and
 * warnings persist until dismissed so nothing important disappears unread.
 */
export function Toast({ status, message, onDismiss }: ToastProps) {
  const persistent = status === 'danger' || status === 'warning';

  useEffect(() => {
    if (persistent) return;
    const timer = window.setTimeout(onDismiss, 5000);
    return () => window.clearTimeout(timer);
  }, [persistent, onDismiss]);

  return (
    <div
      role={status === 'danger' ? 'alert' : 'status'}
      aria-live={status === 'danger' ? 'assertive' : 'polite'}
      className={cn(
        'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border border-border',
        'border-l-4 bg-surface-0 p-4 text-body text-ink-800 shadow-lg',
        ACCENT[status],
      )}
    >
      <p className="flex-1">{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="rounded-sm px-1 text-ink-500 hover:text-ink-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      >
        &times;
      </button>
    </div>
  );
}

export function ToastRegion({ children }: { children: ReactNode }) {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {children}
    </div>
  );
}
