import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

/** DESIGN_SYSTEM.md 7.1. One `primary` per view. */
const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-brand-500 text-surface-0 hover:bg-brand-600 active:bg-brand-700 disabled:bg-brand-500/40',
  secondary:
    'bg-surface-0 text-ink-800 border border-border hover:bg-surface-100 hover:border-border-strong active:bg-surface-200 disabled:opacity-50',
  ghost: 'text-ink-700 hover:bg-surface-100 active:bg-surface-200 disabled:opacity-50',
  danger:
    'bg-danger-solid text-surface-0 hover:bg-danger-hover active:bg-danger-active disabled:opacity-40',
};

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3',
  md: 'h-9 px-4',
  lg: 'h-11 px-5',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** In-flight: disables the control and shows a spinner (PLAN.md 4.1, no double-submits). */
  loading?: boolean;
  loadingLabel?: string;
  trailingIcon?: ReactNode;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  loadingLabel = 'Saving...',
  trailingIcon,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-label',
        'transition-colors duration-fast ease-standard',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? (
        <>
          <Spinner />
          {loadingLabel}
        </>
      ) : (
        <>
          {children}
          {trailingIcon}
        </>
      )}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn('h-3.5 w-3.5 animate-spin', className)}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path
        d="M14.5 8A6.5 6.5 0 0 0 8 1.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
