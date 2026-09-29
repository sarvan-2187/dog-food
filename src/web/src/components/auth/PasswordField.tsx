import { Eye, EyeOff } from 'lucide-react';
import { useState } from 'react';
import type { ComponentProps } from 'react';
import { Input } from '../ui';

/**
 * Password input with a reveal toggle, per the reference layout. The toggle is
 * a real button so it is keyboard-reachable, and it announces which state it
 * will move to rather than which state it is in.
 */
export function PasswordField(props: Omit<ComponentProps<typeof Input>, 'type' | 'trailing'>) {
  const [visible, setVisible] = useState(false);
  return (
    <Input
      {...props}
      type={visible ? 'text' : 'password'}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide password' : 'Show password'}
          className="flex h-8 w-9 items-center justify-center rounded-md text-ink-500 transition-colors duration-fast hover:text-ink-800 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
        >
          {visible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
        </button>
      }
    />
  );
}
