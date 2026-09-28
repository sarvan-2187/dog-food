import { useId } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/cn';

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  /** The specific problem, not "Invalid input" (PLAN.md 4.3). */
  error?: string;
  hint?: string;
  /** Control rendered inside the field's right edge, e.g. a password reveal toggle. */
  trailing?: ReactNode;
}

/** DESIGN_SYSTEM.md 7.2. An error is always carried by text, never colour alone. */
export function Input({ label, error, hint, trailing, className, required, ...rest }: InputProps) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-label text-ink-800">
        {label}
        {required && <span className="text-danger-fg"> *</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(
            'h-10 w-full rounded-md bg-surface-0 px-3 text-body text-ink-800 placeholder:text-ink-500',
            'border transition-colors duration-fast ease-standard',
            'focus:outline-none focus:ring-[3px] focus:ring-brand-500/20',
            error ? 'border-danger-fg focus:border-danger-fg' : 'border-border focus:border-brand-500',
            'disabled:bg-surface-100 disabled:text-ink-500',
            trailing && 'pr-11',
            className,
          )}
          {...rest}
        />
        {trailing && (
          <span className="absolute inset-y-0 right-1 flex items-center">{trailing}</span>
        )}
      </div>
      {error ? (
        <p id={`${id}-error`} className="text-meta text-danger-fg">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-meta text-ink-500">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
