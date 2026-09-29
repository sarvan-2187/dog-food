import { useEffect, useState } from 'react';
import { Badge } from './ui';

function format(ms: number): string {
  const totalMinutes = Math.floor(ms / 60000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days}d ${hours}h remaining`;
  if (hours > 0) return `${hours}h ${minutes}m remaining`;
  return `${minutes}m remaining`;
}

/**
 * The user should never discover a deadline passed only via a rejected save
 * (PLAN.md 4.1). Always visible on the submission page.
 */
export function DeadlineCountdown({ endAt }: { endAt: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(id);
  }, []);

  const remaining = new Date(endAt).getTime() - now;
  const passed = remaining <= 0;

  return (
    <Badge status={passed ? 'danger' : 'warning'}>
      {passed ? 'Deadline passed' : format(remaining)} - {new Date(endAt).toLocaleString()}
    </Badge>
  );
}
