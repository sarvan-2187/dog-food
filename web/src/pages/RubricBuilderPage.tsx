import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { EventRecord, Rubric } from '../types';

const TOLERANCE = 1e-6;
let nextDraftId = -1;

interface Row {
  key: string;
  label: string;
  weight: string;
  max_score: string;
  description: string;
}

interface Draft {
  draftId: number;
  rubricId: number | null; // null = not yet saved
  name: string;
  rows: Row[];
}

const BLANK_ROW: Row = { key: '', label: '', weight: '', max_score: '10', description: '' };

function draftFromRubric(rubric: Rubric): Draft {
  return {
    draftId: nextDraftId--,
    rubricId: rubric.id,
    name: rubric.name,
    rows: rubric.criteria.map((c) => ({
      key: c.key,
      label: c.label,
      weight: String(c.weight),
      max_score: String(c.max_score),
      description: c.description ?? '',
    })),
  };
}

function blankDraft(): Draft {
  return { draftId: nextDraftId--, rubricId: null, name: '', rows: [{ ...BLANK_ROW }, { ...BLANK_ROW }] };
}

export function RubricBuilderPage() {
  return (
    <RequireRole roles={['organizer', 'admin']}>
      <RubricBuilder />
    </RequireRole>
  );
}

function RubricBuilder() {
  const { slug = '' } = useParams();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<EventRecord>(`/api/events/${slug}`)
      .then(async (ev) => {
        if (cancelled) return;
        setEvent(ev);
        try {
          const existing = await api.get<Rubric[]>(`/api/events/${ev.id}/rubrics`);
          if (cancelled) return;
          setDrafts(existing.length ? existing.map(draftFromRubric) : [blankDraft()]);
        } catch {
          setDrafts([blankDraft()]);
        }
      })
      .catch((err) => !cancelled && setLoadError(err instanceof ApiError ? err.message : 'Could not load this event.'));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // The combined weight across every rubric in the set, saved or not -- this
  // is what actually has to reach 1.0 before judges can be assigned, so it's
  // shown once here rather than misleadingly per-rubric.
  const combinedWeight = drafts.reduce(
    (sum, d) => sum + d.rows.reduce((s, r) => s + (Number(r.weight) || 0), 0),
    0,
  );
  const combinedOk = Math.abs(combinedWeight - 1) <= TOLERANCE;

  function updateDraft(draftId: number, patch: Partial<Draft>) {
    setDrafts((ds) => ds.map((d) => (d.draftId === draftId ? { ...d, ...patch } : d)));
  }

  function removeDraft(draftId: number) {
    setDrafts((ds) => ds.filter((d) => d.draftId !== draftId));
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

      <div className="flex flex-col gap-6">
        <div
          aria-live="polite"
          className={[
            'flex flex-wrap items-baseline justify-between gap-2 rounded-md px-4 py-3',
            combinedOk ? 'bg-success-bg' : 'bg-warning-bg',
          ].join(' ')}
        >
          <span className={combinedOk ? 'text-label text-success-fg' : 'text-label text-warning-fg'}>
            {combinedOk ? '✓ This event’s rubrics weight to 1.00' : 'All rubrics together must weight to 1.00'}
          </span>
          <span className={combinedOk ? 'tabular text-h3 text-success-fg' : 'tabular text-h3 text-warning-fg'}>
            {combinedWeight.toFixed(2)}
          </span>
        </div>
        <p className="-mt-2 text-meta text-ink-500">
          Every submission in this event is scored against the combined criteria of every rubric below.
          Split them however makes sense - e.g. one for technical merit, one for presentation.
        </p>

        {drafts.map((draft) => (
          <RubricCard
            key={draft.draftId}
            eventId={event.id}
            draft={draft}
            onChange={(patch) => updateDraft(draft.draftId, patch)}
            onSaved={(rubric) => updateDraft(draft.draftId, { rubricId: rubric.id, name: rubric.name })}
            onDeleted={() => removeDraft(draft.draftId)}
            onToast={setToast}
          />
        ))}

        <Button type="button" variant="secondary" onClick={() => setDrafts((ds) => [...ds, blankDraft()])}>
          Add another rubric
        </Button>
      </div>

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}

function RubricCard({
  eventId,
  draft,
  onChange,
  onSaved,
  onDeleted,
  onToast,
}: {
  eventId: number;
  draft: Draft;
  onChange: (patch: Partial<Draft>) => void;
  onSaved: (rubric: Rubric) => void;
  onDeleted: () => void;
  onToast: (t: { message: string; ok: boolean }) => void;
}) {
  const [locked, setLocked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [touched, setTouched] = useState(false);

  const { name, rows } = draft;
  const weightSum = rows.reduce((s, r) => s + (Number(r.weight) || 0), 0);
  const keys = rows.map((r) => r.key.trim()).filter(Boolean);
  const duplicateKey = keys.length !== new Set(keys).size;
  const rowsComplete = rows.length > 0 && rows.every((r) => r.key.trim() && r.label.trim() && r.weight !== '');
  const nameOk = name.trim().length >= 3;
  const canSave = nameOk && rowsComplete && !duplicateKey;

  function update(i: number, patch: Partial<Row>) {
    onChange({ rows: rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!canSave) return;
    setSaving(true);
    try {
      const body = {
        name,
        criteria: rows.map((r) => ({
          key: r.key.trim(),
          label: r.label.trim(),
          weight: Number(r.weight),
          max_score: Number(r.max_score) || 10,
          description: r.description.trim(),
        })),
      };
      const saved = draft.rubricId
        ? await api.put<Rubric>(`/api/events/${eventId}/rubrics/${draft.rubricId}`, body)
        : await api.post<Rubric>(`/api/events/${eventId}/rubrics`, body);
      onSaved(saved);
      onToast({ message: `"${saved.name}" saved.`, ok: true });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Could not save this rubric.';
      if (err instanceof ApiError && err.status === 409) setLocked(true);
      onToast({ message, ok: false });
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    if (!draft.rubricId) {
      onDeleted(); // never saved - just drop it locally
      return;
    }
    setDeleting(true);
    try {
      await api.del(`/api/events/${eventId}/rubrics/${draft.rubricId}`);
      onDeleted();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Could not delete this rubric.';
      if (err instanceof ApiError && err.status === 409) setLocked(true);
      onToast({ message, ok: false });
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Card title={name.trim() || 'New rubric'}>
      {locked && (
        <div role="alert" className="mb-4 rounded-md border border-border bg-warning-bg px-4 py-3 text-body text-warning-fg">
          Judges have already scored in this event, so this rubric can no longer be changed - editing it now would
          silently invalidate scores already given.
        </div>
      )}

      <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
        <Input
          label="Rubric name"
          required
          value={name}
          onChange={(e) => onChange({ name: e.target.value })}
          onBlur={() => setTouched(true)}
          error={touched && !nameOk ? 'Rubric name must be at least 3 characters.' : undefined}
        />

        <div className="flex flex-col gap-4">
          {rows.map((row, i) => (
            <div key={i} className="flex flex-col gap-3 rounded-md border border-border-subtle p-card-sm">
              <div className="flex items-center justify-between">
                <span className="text-label text-ink-700">Criterion {i + 1}</span>
                {rows.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onChange({ rows: rows.filter((_, idx) => idx !== i) })}
                  >
                    Remove
                  </Button>
                )}
              </div>
              <Input
                label="Label"
                value={row.label}
                onChange={(e) =>
                  update(i, {
                    label: e.target.value,
                    // Derive the key from the label until the organizer edits it
                    // themselves, so they rarely have to think about it.
                    key: row.key || e.target.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_'),
                  })
                }
                hint="Shown to judges on the score form."
              />
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Weight"
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={row.weight}
                  onChange={(e) => update(i, { weight: e.target.value })}
                  onBlur={() => setTouched(true)}
                  hint="0 to 1"
                />
                <Input
                  label="Max score"
                  type="number"
                  min="1"
                  max="100"
                  value={row.max_score}
                  onChange={(e) => update(i, { max_score: e.target.value })}
                />
              </div>
              {/* PLAN.md 10.8: judges read this under the field; entrants see it on the event page. */}
              <Input
                label="What this means (optional)"
                value={row.description}
                maxLength={300}
                onChange={(e) => update(i, { description: e.target.value })}
                placeholder="Who would use this, and how much would it help them?"
                hint="Shown to judges while scoring, and to entrants on the event page."
              />
            </div>
          ))}
        </div>

        <Button type="button" variant="secondary" onClick={() => onChange({ rows: [...rows, { ...BLANK_ROW }] })}>
          Add a criterion
        </Button>

        <p className="text-meta text-ink-500">This rubric's own weights: {weightSum.toFixed(2)}</p>
        {duplicateKey && <p className="text-meta text-danger-fg">Each criterion needs its own key.</p>}
        {touched && !rowsComplete && (
          <p className="text-meta text-danger-fg">Give every criterion a label and a weight.</p>
        )}

        <div className="flex gap-2">
          <Button type="submit" variant="primary" loading={saving} loadingLabel="Saving..." disabled={!canSave}>
            {draft.rubricId ? 'Save changes' : 'Add rubric'}
          </Button>
          <Button type="button" variant="ghost" loading={deleting} loadingLabel="Removing..." onClick={onDelete}>
            {draft.rubricId ? 'Delete rubric' : 'Discard'}
          </Button>
        </div>
      </form>
    </Card>
  );
}
