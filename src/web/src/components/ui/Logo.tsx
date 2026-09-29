import { cn } from '../../lib/cn';

/**
 * The HackFlow mark + wordmark. The mark is the HackRaptors raptor
 * (public/images/raptor.png, alpha-trimmed from the supplied logo).
 *
 * It is painted as a CSS mask rather than an <img> so the single black-on-
 * transparent source tints to whatever colour the surface needs - ink on the
 * light page, white on the dark pill nav - instead of shipping two files that
 * can drift apart.
 */

/** Shared so the nav's scroll mascot lands on a mark identical to the wordmark's. */
export function RaptorMark({ id, className, style }: { id?: string; className?: string; style?: React.CSSProperties }) {
  return (
    <span
      id={id}
      aria-hidden="true"
      className={cn('inline-block shrink-0 bg-current', className)}
      style={{
        maskImage: 'url(/images/raptor.png)',
        WebkitMaskImage: 'url(/images/raptor.png)',
        maskRepeat: 'no-repeat',
        WebkitMaskRepeat: 'no-repeat',
        maskSize: 'contain',
        WebkitMaskSize: 'contain',
        maskPosition: 'center',
        WebkitMaskPosition: 'center',
        ...style,
      }}
    />
  );
}

export function Logo({
  tone = 'ink',
  className,
  showMark = true,
  markId,
}: {
  tone?: 'ink' | 'inverted';
  className?: string;
  /** The landing page hides the mark until the scroll mascot hands it over. */
  showMark?: boolean;
  /** Lets the scroll mascot measure this mark as its landing target. */
  markId?: string;
}) {
  const toneClass = tone === 'inverted' ? 'text-surface-0' : 'text-ink-900';
  return (
    <span className={cn('inline-flex items-center gap-2.5', toneClass, className)}>
      <RaptorMark
        id={markId}
        className={cn('h-7 w-14 transition-opacity duration-base', showMark ? 'opacity-100' : 'opacity-0')}
      />
      <span className="text-h3 tracking-tight">
        Hack<span className="font-serif italic">Flow</span>
      </span>
    </span>
  );
}
