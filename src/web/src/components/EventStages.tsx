import { Check, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { ApiError, api } from '../lib/api';
import { cn } from '../lib/cn';
import type { EventRecord, EventStage } from '../types';
import { Badge, Button, Card, Input } from './ui';

type StageState = 'done' | 'current' | 'next';

function stateOf(stage: EventStage, now: number): StageState {
  if (now >= new Date(stage.ends_at).getTime()) return 'done';
  if (now >= new Date(stage.starts_at).getTime()) return 'current';
  return 'next';
}

function when(stage: EventStage): string {
  const fmt = (iso: string) =>
    new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  return `${fmt(stage.starts_at)} – ${fmt(stage.ends_at)}`;
}

/**
 * The event's rounds as a numbered timeline (Stage 1, Stage 2, ...), the way
 * Unstop shows a competition's rounds: done stages ticked, the current one
 * highlighted, the rest ahead. Informational only; the server's own deadlines
 * are the event dates.
 */
export function StageTimeline({ stages }: { stages: EventStage[] }) {
  if (stages.length === 0) return null;
  const now = Date.now();
  const current = stages.findIndex((s) => stateOf(s, now) === 'current');
  return (
    <Card
      title="Stages"
      meta={current >= 0 ? `Now: Stage ${current + 1} of ${stages.length}` : `${stages.length} stages`}
      className="rounded-xl"
    >
      <ol className="grid gap-4 md:grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]" aria-label="Event stages">
        {stages.map((s, i) => {
          const state = stateOf(s, now);
          return (
            <li
              key={`${s.name}-${i}`}
              aria-current={state === 'current' ? 'step' : undefined}
              className={cn(
                'relative flex flex-col gap-2 rounded-lg border p-4',
                state === 'current' ? 'border-brand-500 bg-surface-0 shadow-sm' : 'border-border-subtle bg-surface-50',
              )}
            >
              <span className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    'flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-meta',
                    state === 'done' && 'bg-success-bg text-success-fg',
                    state === 'current' && 'bg-brand-500 text-surface-0',
                    state === 'next' && 'border border-border text-ink-500',
                  )}
                >
                  {state === 'done' ? <Check size={14} /> : i + 1}
                </span>
                <span className="text-eyebrow uppercase text-ink-400">Stage {i + 1}</span>
                {state === 'current' && <Badge status="success">Now</Badge>}
              </span>
              <span className="text-label text-ink-900">{s.name}</span>
              <span className="tabular text-meta text-ink-500">{when(s)}</span>
              {s.description && <span className="text-meta text-ink-600">{s.description}</span>}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type Draft = { name: string; description: string; starts: string; ends: string };

/** Organizer editor for an event's stages. Saved as a whole, sorted by start on the server. */
export function StagesEditor({
  event,
  onSaved,
  onToast,
}: {
  event: EventRecord;
  onSaved: (event: EventRecord) => void;
  onToast: (t: { message: string; ok: boolean }) => void;
}) {
  const [rows, setRows] = useState<Draft[]>(
    event.stages.map((s) => ({
      name: s.name,
      description: s.description,
      starts: toLocalInput(s.starts_at),
      ends: toLocalInput(s.ends_at),
    })),
  );
  const [saving, setSaving] = useState(false);

  const update = (i: number, patch: Partial<Draft>) => setRows((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)));

  function addStage() {
    // A new stage starts where the last one ended, so the common case is one edit.
    const last = rows[rows.length - 1];
    const start = last?.ends || toLocalInput(event.start_at);
    const end = toLocalInput(new Date(new Date(start).getTime() + 86_400_000).toISOString());
    setRows((r) => [...r, { name: '', description: '', starts: start, ends: end }]);
  }

  async function save() {
    setSaving(true);
    try {
      const updated = await api.patch<EventRecord>(`/api/events/${event.id}`, {
        stages: rows.map((r) => ({
          name: r.name,
          description: r.description,
          starts_at: new Date(r.starts).toISOString(),
          ends_at: new Date(r.ends).toISOString(),
        })),
      });
      onSaved(updated);
      onToast({ message: 'Stages saved.', ok: true });
    } catch (err) {
      onToast({ message: err instanceof ApiError ? err.message : 'Could not save the stages.', ok: false });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card
      title="Stages"
      meta={`${rows.length} of 10`}
      footer="Shown as a timeline on the event page, like Stage 1: Registration, Stage 2: Build sprint. They inform; the event dates above still decide when submissions close."
    >
      <div className="flex flex-col gap-4">
        {rows.length === 0 && (
          <p className="text-body text-ink-500">No stages yet. Add the rounds of your event in order.</p>
        )}
        {rows.map((r, i) => (
          <fieldset key={i} className="flex flex-col gap-3 rounded-lg border border-border-subtle p-4">
            <legend className="px-1 text-eyebrow uppercase text-ink-400">Stage {i + 1}</legend>
            <div className="grid gap-3 md:grid-cols-2">
              <Input label="Name" value={r.name} maxLength={60} onChange={(e) => update(i, { name: e.target.value })} placeholder="Build sprint" />
              <Input
                label="Description"
                value={r.description}
                maxLength={300}
                onChange={(e) => update(i, { description: e.target.value })}
                placeholder="What happens in this stage"
              />
              <Input label="Starts" type="datetime-local" value={r.starts} onChange={(e) => update(i, { starts: e.target.value })} />
              <Input label="Ends" type="datetime-local" value={r.ends} onChange={(e) => update(i, { ends: e.target.value })} />
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="self-start"
              onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
              aria-label={`Remove stage ${i + 1}`}
            >
              <Trash2 size={14} aria-hidden="true" /> Remove
            </Button>
          </fieldset>
        ))}
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={addStage} disabled={rows.length >= 10}>
            <Plus size={14} aria-hidden="true" /> Add stage
          </Button>
          <Button variant="primary" onClick={save} loading={saving} loadingLabel="Saving...">
            Save stages
          </Button>
        </div>
      </div>
    </Card>
  );
}
