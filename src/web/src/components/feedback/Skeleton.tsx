import { cn } from '../../lib/cn';

/** DESIGN_SYSTEM.md 7.7. Shapes match the real content's line heights. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('animate-pulse rounded-sm bg-surface-200', className)} />;
}

/** Table-shaped placeholder. Use while any list view loads. */
export function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} className={cn('h-5 flex-1', c === 0 && 'max-w-[40%]')} />
          ))}
        </div>
      ))}
    </div>
  );
}
