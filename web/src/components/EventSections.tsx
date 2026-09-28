import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Button, Card, Input } from './ui';
import { EmptyState, ErrorState, SkeletonRows } from './feedback';
import { ApiError, api } from '../lib/api';
import type { Announcement, EventRecord, PublicCriterion, WinnersView } from '../types';

/** Plain text with its line breaks kept - never parsed as HTML (PLAN.md 10.8). */
function Paragraphs({ text }: { text: string }) {
  return <p className="whitespace-pre-line text-body text-ink-700">{text}</p>;
}

export function EventRules({ event }: { event: EventRecord }) {
  if (!event.rules.trim()) return null;
  return (
    <Card title="Rules">
      <Paragraphs text={event.rules} />
    </Card>
  );
}

/**
 * PLAN.md 10.8: entrants can see what they'll be judged on - criterion names,
 * weights and what each means. Never a score; the endpoint carries none.
 */
export function JudgingCriteria({ eventId }: { eventId: number }) {
  const [criteria, setCriteria] = useState<PublicCriterion[] | null>(null);

  useEffect(() => {
    api
      .get<PublicCriterion[]>(`/api/events/${eventId}/criteria`)
      .then(setCriteria)
      .catch(() => setCriteria([]));
  }, [eventId]);

  if (criteria === null) return <SkeletonRows rows={2} cols={1} />;
  if (criteria.length === 0) return null;
  return (
    <Card title="How projects are judged" meta="Weights add up to 100%">
      <ul className="flex flex-col divide-y divide-border-subtle">
        {criteria.map((c, i) => (
          <li key={`${c.rubric}-${c.label}-${i}`} className="flex flex-col gap-0.5 py-3 first:pt-0 last:pb-0">
            <span className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-label text-ink-800">{c.label}</span>
              <span className="tabular text-meta text-ink-500">
                {Math.round(c.weight * 100)}% · out of {c.max_score}
              </span>
            </span>
            {c.description && <span className="text-meta text-ink-600">{c.description}</span>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** PLAN.md 10.6: shown once results are revealed; withheld by the API before that. */
export function WinnersSection({ eventId }: { eventId: number }) {
  const [view, setView] = useState<WinnersView | null>(null);

  useEffect(() => {
    api
      .get<WinnersView>(`/api/events/${eventId}/winners`)
      .then(setView)
      .catch(() => setView({ visible: false, winners: [] }));
  }, [eventId]);

  if (!view?.visible || view.winners.length === 0) return null;
  return (
    <Card title="Winners">
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {view.winners.map((w) => (
          <li key={w.prize_rank} className="flex flex-col gap-1 rounded-lg border border-border-subtle p-card-sm">
            <span>
              <Badge status="success">{w.prize_rank}</Badge>
            </span>
            <Link to={`/submissions/${w.submission_id}`} className="mt-1 text-label text-ink-900 hover:text-brand-500">
              {w.title}
            </Link>
            <span className="text-meta text-ink-500">{w.team_name}</span>
            {w.reward && <span className="text-meta text-ink-700">{w.reward}</span>}
            {w.note && <span className="text-meta italic text-ink-600">{w.note}</span>}
          </li>
        ))}
      </ul>
    </Card>
  );
}

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/**
 * PLAN.md 10.11. Everyone sees the list; organizers get a composer, with an
 * "also email" option that only appears when email is set up.
 */
export function Announcements({
  eventId,
  canPost,
  emailEnabled,
}: {
  eventId: number;
  canPost: boolean;
  emailEnabled: boolean;
}) {
  const [items, setItems] = useState<Announcement[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [emailToo, setEmailToo] = useState(false);
  const [posting, setPosting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .get<Announcement[]>(`/api/events/${eventId}/announcements`)
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load announcements.'));
  }, [eventId]);

  useEffect(load, [load]);

  async function post(e: FormEvent) {
    e.preventDefault();
    if (title.trim().length < 3 || !body.trim()) {
      setFormError('Give it a title (3+ characters) and write the announcement.');
      return;
    }
    setPosting(true);
    setFormError(null);
    setNotice(null);
    try {
      const created = await api.post<Announcement>(`/api/events/${eventId}/announcements`, {
        title,
        body,
        email_participants: emailToo,
      });
      setTitle('');
      setBody('');
      setEmailToo(false);
      const n = created.email_queued ?? 0;
      setNotice(n ? `Posted, and emailed to ${n} participant${n === 1 ? '' : 's'}.` : 'Posted.');
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not post this announcement.');
    } finally {
      setPosting(false);
    }
  }

  async function remove(a: Announcement) {
    if (!window.confirm(`Delete "${a.title}"? It disappears from the page; emails already sent stay sent.`)) return;
    try {
      await api.del(`/api/events/${eventId}/announcements/${a.id}`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not delete that announcement.');
    }
  }

  if (!canPost && items && items.length === 0) return null;

  return (
    <Card title="Announcements" meta={items && items.length > 0 ? `${items.length}` : undefined}>
      <div data-tour="announcements" className="flex flex-col gap-5">
        {canPost && (
          <form className="flex flex-col gap-3 rounded-md border border-border-subtle p-card-sm" onSubmit={post} noValidate>
            <Input
              label="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Deadline moved to 20:00"
            />
            <label className="flex flex-col gap-1.5">
              <span className="text-label text-ink-800">Message</span>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={3}
                maxLength={2000}
                className="rounded-md border border-border bg-surface-0 px-3 py-2 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
              />
              <span className="text-meta text-ink-500">
                Plain text. Everyone on a team in this event sees it on their dashboard.
              </span>
            </label>
            {emailEnabled && (
              <label className="flex items-center gap-2 text-body text-ink-700">
                <input type="checkbox" checked={emailToo} onChange={(e) => setEmailToo(e.target.checked)} />
                Also email everyone in this event
              </label>
            )}
            {formError && (
              <p role="alert" className="text-meta text-danger-fg">
                {formError}
              </p>
            )}
            {notice && (
              <p role="status" className="text-meta text-success-fg">
                {notice}
              </p>
            )}
            <div>
              <Button type="submit" variant="primary" loading={posting} loadingLabel="Posting...">
                Post announcement
              </Button>
            </div>
          </form>
        )}

        {error && <ErrorState description={error} onRetry={load} />}
        {items === null && !error && <SkeletonRows rows={2} cols={1} />}
        {items && items.length === 0 && canPost && (
          <EmptyState title="No announcements yet" description="Anything you post here reaches every team in the event." />
        )}
        {items && items.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {items.map((a) => (
              <li key={a.id} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
                <span className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-label text-ink-900">{a.title}</span>
                  <span className="text-meta text-ink-500">
                    {a.author_name} · {when(a.created_at)}
                  </span>
                </span>
                <Paragraphs text={a.body} />
                {canPost && (
                  <span className="flex gap-3 text-meta text-ink-500">
                    {a.emailed_count > 0 && <span>Emailed to {a.emailed_count}</span>}
                    <button
                      type="button"
                      className="underline underline-offset-2 hover:text-ink-900"
                      onClick={() => remove(a)}
                    >
                      Delete
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
