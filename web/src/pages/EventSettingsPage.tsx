import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { PrizeListEditor, TrackListEditor } from '../components/EventConfigEditors';
import { ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
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

function EventSettingsForm() {
  const { slug = '' } = useParams();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tracks, setTracks] = useState<string[]>([]);
  const [prizes, setPrizes] = useState<PrizeEntry[]>([]);
  const [maxTeamSize, setMaxTeamSize] = useState('4');
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
      })
      .catch((err) => !cancelled && setLoadError(err instanceof ApiError ? err.message : 'Could not load this event.'));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!event) return;
    setSaving(true);
    try {
      const updated = await api.patch<EventRecord>(`/api/events/${event.id}`, {
        tracks,
        prize_config: { prizes: prizes.filter((p) => p.rank.trim() && p.reward.trim()) },
        max_team_size: Number(maxTeamSize) || 4,
      });
      setEvent(updated);
      setToast({ message: 'Event settings saved.', ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not save these settings.', ok: false });
    } finally {
      setSaving(false);
    }
  }

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

      <Card title="Event settings" meta={event.name}>
        <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
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
        <WebhookPanel eventId={event.id} onToast={setToast} />
      </div>

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
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
          Each webhook receives a signed POST (verifiable with <code>GET /api/public-key</code>) when a
          submission is submitted, judges are assigned, a score is submitted, or results are revealed.
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
            placeholder="https://example.com/hooks/judger"
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
