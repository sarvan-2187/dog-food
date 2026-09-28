import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { ProjectLinks } from '../components/EventSections';
import type { Criterion, Score, ScoringSheet } from '../types';

export function ScorePage() {
  return (
    <RequireRole roles={['judge']}>
      <ScoreForm />
    </RequireRole>
  );
}

function ScoreForm() {
  const { assignmentId = '' } = useParams();
  const [sheet, setSheet] = useState<ScoringSheet | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [comment, setComment] = useState('');
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedTotal, setSavedTotal] = useState<number | null>(null);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        // One call: the submission, the rubric, and this judge's own score if any.
        // The endpoint is scoped to the owning judge, so an assignment belonging
        // to someone else comes back 403 rather than partially rendering.
        const data = await api.get<ScoringSheet>(`/api/assignments/${assignmentId}/sheet`);
        if (cancelled) return;
        setSheet(data);
        if (data.my_values) {
          setValues(Object.fromEntries(Object.entries(data.my_values).map(([k, v]) => [k, String(v)])));
          setComment(data.my_comment);
          setSavedTotal(data.my_raw_total ?? null);
        }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Could not load this assignment.');
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [assignmentId]);

  // Flat for the scoring math (running total, completeness, submit payload) --
  // Score.values is one flat dict across every rubric in the event, same as
  // the backend. Grouping by rubric only matters for how this renders below.
  const criteria: Criterion[] = sheet?.rubrics.flatMap((r) => r.criteria) ?? [];

  function fieldError(c: Criterion): string | undefined {
    const raw = values[c.key];
    if (raw === undefined || raw.trim() === '') return touched[c.key] ? `Give ${c.label} a score.` : undefined;
    const n = Number(raw);
    if (Number.isNaN(n)) return 'Enter a number.';
    if (n < 0 || n > c.max_score) return `${c.label} must be between 0 and ${c.max_score}.`;
    return undefined;
  }

  // Running total, recomputed live as the judge types (PLAN.md Phase 2 UX).
  const runningTotal = useMemo(
    () =>
      criteria.reduce((sum, c) => {
        const n = Number(values[c.key]);
        return sum + (Number.isFinite(n) && values[c.key] !== '' ? c.weight * n : 0);
      }, 0),
    [criteria, values],
  );

  const maxTotal = useMemo(() => criteria.reduce((s, c) => s + c.weight * c.max_score, 0), [criteria]);
  const complete = criteria.length > 0 && criteria.every((c) => !fieldError(c) && (values[c.key] ?? '') !== '');

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(Object.fromEntries(criteria.map((c) => [c.key, true])));
    if (!complete || !sheet) return;
    setSaving(true);
    try {
      const saved = await api.put<Score>(`/api/assignments/${assignmentId}/score`, {
        values: Object.fromEntries(criteria.map((c) => [c.key, Number(values[c.key])])),
        comment,
      });
      setSavedTotal(saved.raw_total);
      setToast({ message: `Score saved for "${sheet.submission_title}". Weighted total ${saved.raw_total.toFixed(2)}.`, ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not save your score.', ok: false });
    } finally {
      setSaving(false);
    }
  }

  if (loadError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <ErrorState title="You cannot score this" description={loadError} />
        <p className="mt-4 text-center text-meta">
          <Link to="/judge" className="text-brand-500">
            Back to judging
          </Link>
        </p>
      </div>
    );
  }

  if (!sheet) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <SkeletonRows rows={6} cols={1} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-section">
      <p className="mb-4 text-meta">
        <Link to="/judge" className="text-brand-500">
          &larr; Judging
        </Link>
      </p>

      <Card title={sheet.submission_title} meta={sheet.rubrics.map((r) => r.rubric_name).join(' + ')}>
        {/* PLAN.md 10.5: what the judge is actually scoring - not just a paragraph. */}
        <div className="mb-6 flex flex-col gap-4 border-b border-border-subtle pb-4">
          {sheet.submission_image_url && (
            <div className="max-h-80 overflow-hidden rounded-md bg-surface-100">
              <img src={sheet.submission_image_url} alt={`Screenshot of ${sheet.submission_title}`} className="w-full object-cover" />
            </div>
          )}
          {sheet.submission_description && (
            <p className="whitespace-pre-wrap text-body text-ink-600">{sheet.submission_description}</p>
          )}
          <ProjectLinks repo={sheet.repo_url} demo={sheet.demo_url} video={sheet.video_url} />
        </div>

        <form className="flex flex-col gap-6" onSubmit={onSubmit} noValidate>
          {sheet.rubrics.map((group) => (
            <div key={group.rubric_id} className="flex flex-col gap-5">
              {sheet.rubrics.length > 1 && (
                <h4 className="text-label uppercase tracking-wide text-ink-500">{group.rubric_name}</h4>
              )}
              {group.criteria.map((c) => {
                const error = fieldError(c);
                return (
                  <div key={c.key} className="flex flex-col gap-1.5">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <label htmlFor={`c-${c.key}`} className="text-label text-ink-800">
                        {c.label}
                      </label>
                      {/* The weight is shown with the field, not only in a legend. */}
                      <span className="text-meta text-ink-500">
                        weight {(c.weight * 100).toFixed(0)}% &middot; out of {c.max_score}
                      </span>
                    </div>
                    {c.description && <p className="text-meta text-ink-600">{c.description}</p>}
                    <input
                      id={`c-${c.key}`}
                      type="number"
                      inputMode="decimal"
                      min={0}
                      max={c.max_score}
                      step={0.5}
                      value={values[c.key] ?? ''}
                      aria-invalid={error ? true : undefined}
                      aria-describedby={error ? `c-${c.key}-error` : undefined}
                      onChange={(e) => setValues((v) => ({ ...v, [c.key]: e.target.value }))}
                      onBlur={() => setTouched((t) => ({ ...t, [c.key]: true }))}
                      className={[
                        'h-10 rounded-md bg-surface-0 px-3 text-body text-ink-800 border',
                        'focus:outline-none focus:ring-[3px] focus:ring-brand-500/20',
                        error ? 'border-danger-fg focus:border-danger-fg' : 'border-border focus:border-brand-500',
                      ].join(' ')}
                    />
                    {error && (
                      <p id={`c-${c.key}-error`} className="text-meta text-danger-fg">
                        {error}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ))}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="score-comment" className="text-label text-ink-800">
              Comment <span className="text-ink-500">(optional)</span>
            </label>
            <textarea
              id="score-comment"
              rows={4}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="rounded-md border border-border bg-surface-0 px-3 py-2 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
            />
          </div>

          {/* Running weighted total, live (PLAN.md Phase 2 UX). */}
          <div
            aria-live="polite"
            className="flex flex-wrap items-baseline justify-between gap-2 rounded-md bg-surface-100 px-4 py-3"
          >
            <span className="text-label text-ink-700">Weighted total</span>
            <span className="tabular text-h3 text-ink-900">
              {runningTotal.toFixed(2)} <span className="text-meta text-ink-500">/ {maxTotal.toFixed(2)}</span>
            </span>
          </div>

          {!complete && (
            <p className="text-meta text-ink-500">
              Score every criterion to enable submitting - the total above updates as you go.
            </p>
          )}

          <Button type="submit" variant="primary" loading={saving} loadingLabel="Saving score..." disabled={!complete}>
            {savedTotal === null ? 'Submit score' : 'Update score'}
          </Button>

          {savedTotal !== null && (
            <p className="flex items-center gap-2 text-meta text-success-fg">
              <Badge status="success"><span aria-hidden="true">&#10003;</span> Saved</Badge>
              This score is recorded. You can change it and submit again.
            </p>
          )}
        </form>
      </Card>

      {savedTotal === null && (
        <ConflictDeclaration assignmentId={sheet.assignment_id} onError={(message) => setToast({ message, ok: false })} />
      )}

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}

/**
 * PLAN.md 10.7: a judge steps back from a project they can't judge fairly.
 * The project is released for someone else and never handed back to them.
 * Only offered before they've scored it.
 */
function ConflictDeclaration({ assignmentId, onError }: { assignmentId: number; onError: (message: string) => void }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  async function declare() {
    if (!window.confirm("Step back from this project? It will go to another judge, and it won't be assigned to you again.")) return;
    setBusy(true);
    try {
      await api.post(`/api/assignments/${assignmentId}/conflict`, { reason });
      navigate('/judge');
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Could not record the conflict.');
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 rounded-lg border border-border-subtle p-card-sm">
      {!open ? (
        <button
          type="button"
          className="text-meta text-ink-600 underline underline-offset-2 hover:text-ink-900"
          onClick={() => setOpen(true)}
        >
          I have a conflict of interest with this project
        </button>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-body text-ink-700">
            If you know the team, helped build it, or can't judge it fairly for any reason, step back. The organizer sees
            your note.
          </p>
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">
              Reason <span className="text-ink-500">(optional)</span>
            </span>
            <input
              value={reason}
              maxLength={300}
              onChange={(e) => setReason(e.target.value)}
              placeholder="I mentored this team"
              className="h-10 rounded-md border border-border bg-surface-0 px-3 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" loading={busy} loadingLabel="Stepping back..." onClick={declare}>
              Step back from this project
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
