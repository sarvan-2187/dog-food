import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { PrizeListEditor, TrackListEditor } from '../components/EventConfigEditors';
import { Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { EventRecord, PrizeEntry } from '../types';

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

/** "HackFlow Hackathon 2026!" -> "hackflow-hackathon-2026". Accents are folded, not dropped. */
export function slugify(name: string): string {
  return name
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function EventCreatePage() {
  return (
    <RequireRole roles={['organizer', 'admin']}>
      <EventCreateForm />
    </RequireRole>
  );
}

function EventCreateForm() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  // The slug follows the name until the organizer types their own; clearing it
  // hands it back to the name.
  const [customSlug, setCustomSlug] = useState('');
  const slug = customSlug || slugify(name);
  const [description, setDescription] = useState('');
  const [startAt, setStartAt] = useState('');
  const [endAt, setEndAt] = useState('');
  const [tracks, setTracks] = useState<string[]>([]);
  const [prizes, setPrizes] = useState<PrizeEntry[]>([]);
  const [maxTeamSize, setMaxTeamSize] = useState('4');
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const nameError = touched.name && name.trim().length < 3 ? 'Event name must be at least 3 characters.' : undefined;
  const slugError = touched.slug && slug !== '' && !SLUG_RE.test(slug) ? 'Slug must be lowercase letters, numbers and dashes.' : undefined;
  const dateError =
    touched.endAt && startAt && endAt && new Date(endAt) <= new Date(startAt) ? 'End date must be after the start date.' : undefined;

  const mark = (field: string) => () => setTouched((t) => ({ ...t, [field]: true }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched({ name: true, slug: true, endAt: true });
    if (name.trim().length < 3 || !SLUG_RE.test(slug) || (startAt && endAt && new Date(endAt) <= new Date(startAt))) return;
    setSubmitError(null);
    setLoading(true);
    try {
      const created = await api.post<EventRecord>('/api/events', {
        name,
        slug,
        description,
        start_at: new Date(startAt).toISOString(),
        end_at: new Date(endAt).toISOString(),
        tracks,
        prize_config: { prizes: prizes.filter((p) => p.rank.trim() && p.reward.trim()) },
        max_team_size: Number(maxTeamSize) || 4,
      });
      // New events start as drafts (PLAN.md 10.12); settings is where they're published.
      navigate(`/events/${created.slug}/settings`);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Could not create the event.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-section">
      <Card title="Create an event">
        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          <Input label="Name" required value={name} onChange={(e) => setName(e.target.value)} onBlur={mark('name')} error={nameError} />
          <Input
            label="Slug"
            required
            value={slug}
            onChange={(e) => setCustomSlug(e.target.value)}
            onBlur={mark('slug')}
            error={slugError}
            hint={
              slugError
                ? undefined
                : customSlug
                  ? 'Used in the URL. Clear it to generate one from the name again.'
                  : 'Made from the name and used in the URL. Edit it if you like.'
            }
          />
          <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <Input label="Start" type="datetime-local" required value={startAt} onChange={(e) => setStartAt(e.target.value)} />
          <Input
            label="End"
            type="datetime-local"
            required
            value={endAt}
            onChange={(e) => setEndAt(e.target.value)}
            onBlur={mark('endAt')}
            error={dateError}
          />
          <Input
            label="Max team size"
            type="number"
            min="1"
            max="20"
            value={maxTeamSize}
            onChange={(e) => setMaxTeamSize(e.target.value)}
            hint="Matches this hackathon's own rule (1-4) by default - change it if this event needs a different cap."
          />
          <TrackListEditor tracks={tracks} onChange={setTracks} />
          <PrizeListEditor prizes={prizes} onChange={setPrizes} />
          {submitError && (
            <p role="alert" className="text-meta text-danger-fg">
              {submitError}
            </p>
          )}
          <Button type="submit" variant="primary" loading={loading} loadingLabel="Creating...">
            Create event
          </Button>
        </form>
      </Card>
    </div>
  );
}
