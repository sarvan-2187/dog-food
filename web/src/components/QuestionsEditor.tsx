import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { ApiError, api } from '../lib/api';
import type { EventQuestion, EventRecord } from '../types';
import { Button, Card, Input } from './ui';

const MAX_QUESTIONS = 10;

type Draft = Omit<EventQuestion, 'id'> & { id?: string };

/**
 * Organizer editor for an event's custom questions (DOGFOOD T1). Teams answer
 * them on the submission form, judges read the answers on the score sheet, and
 * the project page shows the ones ticked "Show publicly". Saved as a whole list.
 *
 * The server refuses to delete a question someone has answered, so the answer
 * is never silently lost; this editor says so and offers Hide instead.
 */
export function QuestionsEditor({
  event,
  onSaved,
  onToast,
}: {
  event: EventRecord;
  onSaved: (event: EventRecord) => void;
  onToast: (t: { message: string; ok: boolean }) => void;
}) {
  const [rows, setRows] = useState<Draft[]>(event.questions ?? []);
  const [saving, setSaving] = useState(false);

  const update = (i: number, patch: Partial<Draft>) =>
    setRows((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)));

  async function save() {
    setSaving(true);
    try {
      const questions = await api.put<EventQuestion[]>(`/api/events/${event.id}/questions`, { questions: rows });
      setRows(questions);
      onSaved({ ...event, questions });
      onToast({ message: 'Questions saved.', ok: true });
    } catch (err) {
      onToast({ message: err instanceof ApiError ? err.message : 'Could not save the questions.', ok: false });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card
      title="Submission questions"
      meta={`${rows.length} of ${MAX_QUESTIONS}`}
      footer="Short text answers, up to 1000 characters. A required question must be answered before a team can submit. Once a team has answered a question it can be hidden but not deleted."
    >
      <div className="flex flex-col gap-4">
        {rows.length === 0 && (
          <p className="text-body text-ink-500">No questions yet. Add anything you want every team to tell you.</p>
        )}
        {rows.map((q, i) => (
          <fieldset key={q.id ?? `new-${i}`} className="flex flex-col gap-3 rounded-lg border border-border-subtle p-4">
            <legend className="px-1 text-eyebrow uppercase text-ink-400">Question {i + 1}</legend>
            <Input
              label="Question"
              value={q.prompt}
              maxLength={200}
              placeholder="Who is this for?"
              onChange={(e) => update(i, { prompt: e.target.value })}
            />
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-body text-ink-700">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={q.required} onChange={(e) => update(i, { required: e.target.checked })} />
                Required
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={q.public} onChange={(e) => update(i, { public: e.target.checked })} />
                Show publicly on the project page
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={q.hidden} onChange={(e) => update(i, { hidden: e.target.checked })} />
                Hidden
              </label>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="self-start"
              onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
              aria-label={`Delete question ${i + 1}`}
            >
              <Trash2 size={14} aria-hidden="true" /> Delete
            </Button>
          </fieldset>
        ))}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => setRows((r) => [...r, { prompt: '', required: false, hidden: false, public: false }])}
            disabled={rows.length >= MAX_QUESTIONS}
          >
            <Plus size={14} aria-hidden="true" /> Add question
          </Button>
          <Button variant="primary" onClick={save} loading={saving} loadingLabel="Saving...">
            Save questions
          </Button>
        </div>
      </div>
    </Card>
  );
}
