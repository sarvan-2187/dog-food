import { cn } from '../../lib/cn';

/**
 * The HackFlow mark + wordmark, drawn fresh for the rebrand (not copied from any
 * reference asset). One component so the nav, footer, and any future usage
 * stay pixel-identical rather than three hand-typed copies drifting apart.
 */
export function Logo({ tone = 'ink', className }: { tone?: 'ink' | 'inverted'; className?: string }) {
  const strokeColor = tone === 'inverted' ? '#F8F9F9' : '#1F2426';
  const textClass = tone === 'inverted' ? 'text-surface-0' : 'text-ink-900';
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <svg width="22" height="22" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path d="M7 5 L12 27" stroke={strokeColor} strokeWidth="3.4" strokeLinecap="round" />
        <path d="M16 3 L20 27" stroke={strokeColor} strokeWidth="3.4" strokeLinecap="round" />
        <path d="M24 6 L26 22" stroke={strokeColor} strokeWidth="3.4" strokeLinecap="round" />
      </svg>
      <span className={cn('text-h3 tracking-tight', textClass)}>
        Hack<span className="font-serif italic">Flow</span>
      </span>
    </span>
  );
}
