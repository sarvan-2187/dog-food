import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { EventRecord, Rubric } from '../types';

const TOLERANCE = 1e-6;

interface Row {
  key: string;
  label: string;
  weight: string;
  max_score: string;
}

const BLANK: Row = { key: '', label: '', weight: '', max_score: '10' };

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
  const [name, setName] = useState('');
  const [rows, setRows] = useState<Row[]>([{ ...BLANK }, { ...BLANK }]);
  const [locked, setLocked] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState(false);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<EventRecord>(`/api/events/${slug}`)
      .then(async (ev) => {
        if (cancelled) return;
        setEvent(ev);
        try {
          const existing = await api.get<Rubric>(`/api/events/${ev.id}/rubric`);
          if (cancelled) return;
          setName(existing.name);
          setRows(
            existing.criteria.map((c) => ({
              key: c.key,
              label: c.label,
              weight: String(c.weight),
              max_score: String(c.max_score),
            })),
          );
        } catch {
          // No rubric yet is the normal starting state, not an error.
        }
      })
      .catch((err) => !cancelled && setLoadError(err instanceof ApiError ? err.message : 'Could not load this event.'));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const weightSum = rows.reduce((s, r) => s + (Number(r.weight) || 0), 0);
  const weightsOk = Math.abs(weightSum - 1) <= TOLERANCE;
  const keys = rows.map((r) => r.key.trim()).filter(Boolean);
  const duplicateKey = keys.length !== new Set(keys).size;
  const rowsComplete = rows.every((r) => r.key.trim() && r.label.trim() && r.weight !== '');
  const nameOk = name.trim().length >= 3;
  const canSave = nameOk && rowsComplete && weightsOk && !duplicateKey;

  function update(i: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!canSave || !event) return;
    setSaving(true);
    try {
      await api.put<Rubric>(`/api/events/${event.id}/rubric`, {
        name,
        criteria: rows.map((r) => ({
          key: r.key.trim(),
          label: r.label.trim(),
          weight: Number(r.weight),
          max_score: Number(r.max_score) || 10,
        })),
      });
      setToast({ message: 'Rubric saved. Judges will score against these criteria.', ok: true });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Could not save the rubric.';
      if (err instanceof ApiError && err.status === 409) setLocked(true);
      setToast({ message, ok: false });
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

      <Card title="Judging rubric" meta={event.name}>
        {locked && (
          <div role="alert" className="mb-4 rounded-md border border-border bg-warning-bg px-4 py-3 text-body text-warning-fg">
            Judges have already scored against this rubric, so its criteria can no longer be changed - editing the
            weights now would silently invalidate every score already given.
          </div>
        )}

        <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
          <Input
            label="Rubric name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
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
                      onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
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
              </div>
            ))}
          </div>

          <Button type="button" variant="secondary" onClick={() => setRows((rs) => [...rs, { ...BLANK }])}>
            Add a criterion
          </Button>

          {/* Weight total is validated at the field level, live, not as a generic
              form-level rejection on submit (PLAN.md Phase 2 UX). */}
          <div
            aria-live="polite"
            className={[
              'flex flex-wrap items-baseline justify-between gap-2 rounded-md px-4 py-3',
              weightsOk ? 'bg-success-bg' : 'bg-warning-bg',
            ].join(' ')}
          >
            <span className={weightsOk ? 'text-label text-success-fg' : 'text-label text-warning-fg'}>
              {weightsOk ? '✓ Weights add up to 1.00' : 'Weights must add up to 1.00'}
            </span>
            <span className={weightsOk ? 'tabular text-h3 text-success-fg' : 'tabular text-h3 text-warning-fg'}>
              {weightSum.toFixed(2)}
            </span>
          </div>

          {!weightsOk && (
            <p className="text-meta text-warning-fg">
              {weightSum > 1
                ? `That is ${(weightSum - 1).toFixed(2)} too much - reduce a weight.`
                : `That is ${(1 - weightSum).toFixed(2)} short - increase a weight or add a criterion.`}
            </p>
          )}
          {duplicateKey && <p className="text-meta text-danger-fg">Each criterion needs its own key.</p>}
          {touched && !rowsComplete && (
            <p className="text-meta text-danger-fg">Give every criterion a label and a weight.</p>
          )}

          <Button type="submit" variant="primary" loading={saving} loadingLabel="Saving rubric..." disabled={!canSave}>
            Save rubric
          </Button>
        </form>
      </Card>

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
