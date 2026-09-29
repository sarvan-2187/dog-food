import { Badge } from './ui';

const day = (d: Date) => d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/**
 * An event's soft judging deadline. Text, not just colour (PLAN.md 4.5). Past
 * the deadline it reads "Overdue" - scoring still works, the organizer sees it.
 */
export function DueBadge({ at }: { at: string | null | undefined }) {
  if (!at) return null;
  const due = new Date(at);
  const msLeft = due.getTime() - Date.now();
  if (msLeft <= 0) return <Badge status="danger">Overdue · was due {day(due)}</Badge>;
  const days = Math.floor(msLeft / 86_400_000);
  return (
    <Badge status={days < 2 ? 'warning' : 'neutral'}>
      Due {day(due)} · {days >= 1 ? `${days} day${days === 1 ? '' : 's'} left` : 'under a day left'}
    </Badge>
  );
}
