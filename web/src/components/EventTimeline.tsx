import { useEffect, useState } from 'react';
import { Badge } from './ui';
import type { EventRecord } from '../types';

export type EventPhase = 'upcoming' | 'open' | 'judging' | 'results';

/**
 * Where an event is in its life (PLAN.md 10.8). Derived from the same dates
 * the server enforces, so the page never says "open" while the API refuses a
 * save. Before this, an event that hadn't started yet showed only a countdown
 * to its deadline and read as if it were already running.
 */
export function eventPhase(
  event: Pick<EventRecord, 'start_at' | 'end_at' | 'results_hidden_until'>,
  now = Date.now(),
): EventPhase {
  if (now < new Date(event.start_at).getTime()) return 'upcoming';
  if (now < new Date(event.end_at).getTime()) return 'open';
  if (event.results_hidden_until && now < new Date(event.results_hidden_until).getTime()) return 'judging';
  return 'results';
}

const PHASE_LABEL: Record<EventPhase, string> = {
  upcoming: 'Upcoming',
  open: 'Open for submissions',
  judging: 'Judging',
  results: 'Results are out',
};

const PHASE_TONE: Record<EventPhase, 'info' | 'success' | 'warning' | 'neutral'> = {
  upcoming: 'info',
  open: 'success',
  judging: 'warning',
  results: 'neutral',
};

export function PhaseBadge({ event }: { event: EventRecord }) {
  if (event.status === 'draft') return <Badge status="neutral">Draft</Badge>;
  const phase = eventPhase(event);
  return <Badge status={PHASE_TONE[phase]}>{PHASE_LABEL[phase]}</Badge>;
}

function span(ms: number): string {
  const minutes = Math.max(0, Math.floor(ms / 60000));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  return `${minutes % 60}m`;
}

const fmt = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });

/** Phase badge, both dates, and one countdown worded for the phase. */
export function EventTimeline({ event }: { event: EventRecord }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(id);
  }, []);

  const phase = eventPhase(event, now);
  const countdown =
    phase === 'upcoming'
      ? `Starts in ${span(new Date(event.start_at).getTime() - now)}`
      : phase === 'open'
        ? `Submissions close in ${span(new Date(event.end_at).getTime() - now)}`
        : phase === 'judging'
          ? `Judging in progress - results on ${fmt(event.results_hidden_until!)}`
          : 'Results are out';

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <PhaseBadge event={event} />
        <span className="text-body text-ink-700">{countdown}</span>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-meta text-ink-500">
        <div className="flex gap-1.5">
          <dt>Starts</dt>
          <dd className="text-ink-800">{fmt(event.start_at)}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt>Submissions close</dt>
          <dd className="text-ink-800">{fmt(event.end_at)}</dd>
        </div>
      </dl>
    </div>
  );
}
