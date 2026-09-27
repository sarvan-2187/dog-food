import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { PrizeListEditor, TrackListEditor } from '../components/EventConfigEditors';
import { ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { CertificateDesignPicker } from '../components/CertificateDesign';
import { StagesEditor } from '../components/EventStages';
import { QuestionsEditor } from '../components/QuestionsEditor';
import type { EventRecord, PrizeEntry, WebhookRecord } from '../types';

/**
 * The only way to change an event's tracks, prizes, or team-size cap after
 * creation (PLAN.md Phase 7.1/7.2) - before this screen existed, the only
 * route was a raw PATCH call, which is not "configurable" in any real sense
 * for an organizer.
 */
export function EventSettingsPage() {
  return (
    <RequireRole roles={['organizer', 'admin']}>
      <EventSettingsForm />
    </RequireRole>
  );
}

/** An ISO instant as the value a datetime-local input expects, in local time. */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function EventSettingsForm() {
  const { slug = '' } = useParams();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tracks, setTracks] = useState<string[]>([]);
  const [prizes, setPrizes] = useState<PrizeEntry[]>([]);
  const [maxTeamSize, setMaxTeamSize] = useState('4');
  // PLAN.md 10.8: dates were only settable at creation; rules are new.
  const [startAt, setStartAt] = useState('');
  const [endAt, setEndAt] = useState('');
  const [rules, setRules] = useState('');
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<EventRecord>(`/api/events/${slug}`)
      .then((ev) => {
        if (cancelled) return;
        setEvent(ev);
        setTracks(ev.tracks);
        setPrizes(ev.prize_config.prizes ?? []);
        setMaxTeamSize(String(ev.max_team_size));
        setStartAt(toLocalInput(ev.start_at));
        setEndAt(toLocalInput(ev.end_at));
        setRules(ev.rules);
      })
      .catch((err) => !cancelled && setLoadError(err instanceof ApiError ? err.message : 'Could not load this event.'));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!event || datesError) return;
    const newEnd = new Date(endAt).getTime();
    const closesNow = newEnd <= Date.now() && new Date(event.end_at).getTime() > Date.now();
    if (
      closesNow &&
      !window.confirm(
        'That end date has already passed, so this closes submissions now. Teams will no longer be able to edit their entries. Continue?',
      )
    ) {
      return;
    }
    setSaving(true);
    try {
      const updated = await api.patch<EventRecord>(`/api/events/${event.id}`, {
        tracks,
        prize_config: { prizes: prizes.filter((p) => p.rank.trim() && p.reward.trim()) },
        max_team_size: Number(maxTeamSize) || 4,
        start_at: new Date(startAt).toISOString(),
        end_at: new Date(endAt).toISOString(),
        rules,
      });
      setEvent(updated);
      setToast({ message: 'Event settings saved.', ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not save these settings.', ok: false });
    } finally {
      setSaving(false);
    }
  }

  async function closeNow() {
    if (!event) return;
    if (!window.confirm('Close submissions now? Teams will no longer be able to edit their entries, and judging can start.')) {
      return;
    }
    try {
      const updated = await api.patch<EventRecord>(`/api/events/${event.id}`, { end_at: new Date().toISOString() });
      setEvent(updated);
      setEndAt(toLocalInput(updated.end_at));
      setToast({ message: 'Submissions are closed. You can assign judges from the results page.', ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not close submissions.', ok: false });
    }
  }

  const datesError =
    startAt && endAt && new Date(endAt).getTime() <= new Date(startAt).getTime()
      ? 'The end has to come after the start.'
      : undefined;

  if (loadError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <ErrorState description={loadError} />
      </div>
    );
  }
  if (!event) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <SkeletonRows rows={5} cols={1} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-section">
      <p className="mb-4 text-meta">
        <Link to={`/events/${slug}`} className="text-brand-500">
          &larr; {event.name}
        </Link>
      </p>

      <div className="mb-6">
        <PublishPanel event={event} onChange={setEvent} onToast={setToast} />
      </div>

      <Card title="Event settings" meta={event.name}>
        <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Starts" type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} />
            <Input
              label="Submissions close"
              type="datetime-local"
              value={endAt}
              onChange={(e) => setEndAt(e.target.value)}
              error={datesError}
              hint={datesError ? undefined : 'Judging opens once this passes.'}
            />
          </div>
          {new Date(event.end_at).getTime() > Date.now() && (
            <div>
              <Button type="button" variant="ghost" size="sm" onClick={closeNow}>
                Close submissions now
              </Button>
            </div>
          )}
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Rules</span>
            <textarea
              rows={5}
              maxLength={5000}
              value={rules}
              onChange={(e) => setRules(e.target.value)}
              placeholder={'Teams of up to 4.\nEverything must be built during the event.'}
              className="rounded-md border border-border bg-surface-0 px-3 py-2 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
            />
            <span className="text-meta text-ink-500">Plain text, shown on the event page. Line breaks are kept.</span>
          </label>
          <Input
            label="Max team size"
            type="number"
            min="1"
            max="20"
            value={maxTeamSize}
            onChange={(e) => setMaxTeamSize(e.target.value)}
            hint="Existing teams already over this size are unaffected - the cap only blocks new joins."
          />
          <TrackListEditor tracks={tracks} onChange={setTracks} />
          <PrizeListEditor prizes={prizes} onChange={setPrizes} />
          <Button type="submit" variant="primary" loading={saving} loadingLabel="Saving...">
            Save settings
          </Button>
        </form>
      </Card>

      <div className="mt-6">
        <StagesEditor key={event.id} event={event} onSaved={setEvent} onToast={setToast} />
      </div>

      <div className="mt-6">
        <QuestionsEditor key={event.id} event={event} onSaved={setEvent} onToast={setToast} />
      </div>

      <div className="mt-6">
        <CertificateDesignPicker event={event} onSaved={setEvent} onToast={setToast} />
      </div>

      <div className="mt-6">
        <BackupPanel eventId={event.id} slug={event.slug} onToast={setToast} />
      </div>

      <div className="mt-6">
        <EmbedPanel slug={event.slug} onToast={setToast} />
      </div>

      <div className="mt-6">
        <WebhookPanel eventId={event.id} onToast={setToast} />
      </div>

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}

/**
 * Bulk event backup (PLAN.md Phase 4 T4). Deliberately download-only here -
 * restoring a backup creates a *new* event, so it lives on the events list
 * next to "Create event", not inside one event's settings.
 */
function BackupPanel({
  eventId,
  slug,
  onToast,
}: {
  eventId: number;
  slug: string;
  onToast: (t: { message: string; ok: boolean }) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function download() {
    setBusy(true);
    try {
      await api.download(`/api/events/${eventId}/export.json`, `${slug}-backup.json`);
      onToast({ message: 'Event backup downloaded.', ok: true });
    } catch (err) {
      onToast({ message: err instanceof ApiError ? err.message : 'Could not export this event.', ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Backup" meta="JSON">
      <div className="flex flex-col gap-4">
        <p className="text-body text-ink-600">
          Downloads this event's configuration, rubrics, teams and submissions as one file. Judge assignments and
          scores are deliberately left out - they belong to specific judge accounts, and re-creating them against
          different judges would misrepresent who judged what.
        </p>
        <div>
          <Button variant="secondary" loading={busy} loadingLabel="Preparing..." onClick={download}>
            Download event backup
          </Button>
        </div>
      </div>
    </Card>
  );
}

/**
 * The gallery widget (DOGFOOD T4): a plain HTML page any site can frame, with
 * the same public data as the gallery - vote counts and awards stay hidden
 * until the reveal. It is the only HackFlow page other sites may frame.
 */
function EmbedPanel({ slug, onToast }: { slug: string; onToast: (t: { message: string; ok: boolean }) => void }) {
  const src = `${window.location.origin}/embed/events/${slug}`;
  const snippet = `<iframe src="${src}" title="Hackathon projects" width="100%" height="600" style="border:0" loading="lazy"></iframe>`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet);
      onToast({ message: 'Embed code copied.', ok: true });
    } catch {
      onToast({ message: 'Could not copy - select the code and copy it by hand.', ok: false });
    }
  }

  return (
    <Card title="Embed on your site" meta="HTML">
      <div className="flex flex-col gap-4">
        <p className="text-body text-ink-600">
          Paste this into any web page to show this event's projects. It updates itself as teams submit, and
          shows winners only after your results reveal.
        </p>
        <textarea
          readOnly
          aria-label="Embed code"
          className="min-h-24 w-full rounded-md border border-border bg-surface-100 p-3 font-mono text-meta text-ink-800"
          value={snippet}
          onFocus={(e) => e.currentTarget.select()}
        />
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={copy}>
            Copy embed code
          </Button>
          <a href={src} target="_blank" rel="noopener" className="self-center text-meta text-brand-500">
            Preview the widget
          </a>
        </div>
      </div>
    </Card>
  );
}

const STATUS_BADGE: Record<WebhookRecord['last_status'], 'success' | 'danger' | 'info'> = {
  delivered: 'success',
  failed: 'danger',
  'never fired': 'info',
};

/**
 * Entirely opt-in (PLAN.md Phase 7.3): an event with no rows here makes zero
 * outbound network calls. Deleting a webhook stops delivery immediately -
 * there is no separate deactivate step.
 */
function WebhookPanel({ eventId, onToast }: { eventId: number; onToast: (t: { message: string; ok: boolean }) => void }) {
  const [webhooks, setWebhooks] = useState<WebhookRecord[] | null>(null);
  const [url, setUrl] = useState('');
  const [adding, setAdding] = useState(false);

  function load() {
    api
      .get<WebhookRecord[]>(`/api/events/${eventId}/webhooks`)
      .then(setWebhooks)
      .catch(() => setWebhooks([]));
  }

  useEffect(load, [eventId]);

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setAdding(true);
    try {
      await api.post(`/api/events/${eventId}/webhooks`, { url: url.trim() });
      setUrl('');
      load();
      onToast({ message: 'Webhook added.', ok: true });
    } catch (err) {
      onToast({ message: err instanceof ApiError ? err.message : 'Could not add that webhook.', ok: false });
    } finally {
      setAdding(false);
    }
  }

  async function onDelete(id: number) {
    try {
      await api.del(`/api/events/${eventId}/webhooks/${id}`);
      load();
    } catch (err) {
      onToast({ message: err instanceof ApiError ? err.message : 'Could not remove that webhook.', ok: false });
    }
  }

  return (
    <Card
      title="Webhooks"
      meta="Optional - fires zero outbound calls unless you add one below"
    >
      <div className="flex flex-col gap-4">
        <p className="text-meta text-ink-500">
          Each webhook receives a signed POST (verifiable with <code>GET /api/public-key</code>) for every
          action taken in this event: submissions, teams, judging, scores, votes, comments, announcements and
          settings changes. The topic is the action's name, for example <code>event.updated</code>. Payloads
          carry ids only; fetch details through the API with a key.
        </p>

        {webhooks === null && <p className="text-meta text-ink-500">Loading...</p>}
        {webhooks && webhooks.length === 0 && (
          <p className="text-meta text-ink-500">No webhooks configured for this event.</p>
        )}
        {webhooks && webhooks.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {webhooks.map((w) => (
              <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-body text-ink-800">{w.url}</span>
                  <Badge status={STATUS_BADGE[w.last_status]}>{w.last_status}</Badge>
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={() => onDelete(w.id)}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}

        <form className="flex items-end gap-2" onSubmit={onAdd}>
          <Input
            label="Webhook URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/hooks/hackflow"
            className="flex-1"
          />
          <Button type="submit" variant="secondary" loading={adding} loadingLabel="Adding...">
            Add webhook
          </Button>
        </form>
      </div>
    </Card>
  );
}

/**
 * PLAN.md 10.12. New events start as drafts, visible only to organizers. The
 * checklist warns rather than blocks - an organizer may have good reason to
 * publish before the rubric is written - and unpublishing is refused by the
 * server once any team has joined.
 */
function PublishPanel({
  event,
  onChange,
  onToast,
}: {
  event: EventRecord;
  onChange: (e: EventRecord) => void;
  onToast: (t: { message: string; ok: boolean }) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [hasRubric, setHasRubric] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .get<unknown[]>(`/api/events/${event.id}/criteria`)
      .then((c) => setHasRubric(c.length > 0))
      .catch(() => setHasRubric(null));
  }, [event.id]);

  const warnings = [
    event.tracks.length === 0 && 'No tracks yet.',
    hasRubric === false && "No judging rubric yet - judges can't score without one.",
    !event.rules.trim() && 'No rules written.',
  ].filter(Boolean) as string[];

  async function toggle() {
    const publishing = event.status === 'draft';
    if (!publishing && !window.confirm('Turn this event back into a draft? Participants will no longer see it.')) return;
    setBusy(true);
    try {
      const updated = await api.post<EventRecord>(`/api/events/${event.id}/${publishing ? 'publish' : 'unpublish'}`);
      onChange(updated);
      onToast({ message: publishing ? 'Published - participants can see it now.' : 'Back to draft.', ok: true });
    } catch (err) {
      onToast({ message: err instanceof ApiError ? err.message : 'Could not change the event status.', ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Visibility"
      meta={event.status === 'draft' ? <Badge status="neutral">Draft</Badge> : <Badge status="success">Published</Badge>}
    >
      <div className="flex flex-col gap-3">
        <p className="text-body text-ink-600">
          {event.status === 'draft'
            ? 'Only organizers can see this event. Publish it when it is ready for participants.'
            : 'Participants can see and join this event.'}
        </p>
        {event.status === 'draft' && warnings.length > 0 && (
          <ul className="list-inside list-disc text-meta text-warning-fg">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
        <div>
          <Button
            variant={event.status === 'draft' ? 'primary' : 'secondary'}
            loading={busy}
            loadingLabel="Saving..."
            onClick={toggle}
          >
            {event.status === 'draft' ? 'Publish event' : 'Move back to draft'}
          </Button>
        </div>
      </div>
    </Card>
  );
}
