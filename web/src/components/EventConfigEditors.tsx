import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import { Button, Input } from './ui';
import type { PrizeEntry } from '../types';

/**
 * Tracks and prizes (PLAN.md Phase 7.1) share one "list of rows with a
 * remove button" interaction, the same pattern RubricBuilderPage's criteria
 * rows already use - no new interaction to design, and both
 * EventCreatePage and EventSettingsPage reuse these two components as-is.
 */
export function TrackListEditor({ tracks, onChange }: { tracks: string[]; onChange: (tracks: string[]) => void }) {
  const [draft, setDraft] = useState('');

  function add() {
    const v = draft.trim();
    if (!v || tracks.includes(v)) return;
    onChange([...tracks, v]);
    setDraft('');
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault();
      add();
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-label text-ink-800">Tracks</span>
      <div className="flex flex-wrap gap-2">
        {tracks.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1.5 rounded-full bg-surface-100 px-3 py-1 text-label text-ink-700"
          >
            {t}
            <button
              type="button"
              onClick={() => onChange(tracks.filter((x) => x !== t))}
              aria-label={`Remove track ${t}`}
              className="text-ink-500 hover:text-danger-fg"
            >
              &times;
            </button>
          </span>
        ))}
        {tracks.length === 0 && (
          <span className="text-meta text-ink-500">No tracks configured - submissions use free text.</span>
        )}
      </div>
      <div className="flex items-end gap-2">
        <Input label="New track" value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKeyDown} className="flex-1" />
        <Button type="button" variant="secondary" onClick={add}>
          Add track
        </Button>
      </div>
    </div>
  );
}

export function PrizeListEditor({ prizes, onChange }: { prizes: PrizeEntry[]; onChange: (prizes: PrizeEntry[]) => void }) {
  function update(i: number, patch: Partial<PrizeEntry>) {
    onChange(prizes.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
  }

  return (
    <div className="flex flex-col gap-3">
      <span className="text-label text-ink-800">Prizes</span>
      {prizes.length === 0 && <p className="text-meta text-ink-500">No prizes configured yet.</p>}
      {prizes.map((p, i) => (
        <div key={i} className="flex flex-col gap-2 rounded-md border border-border-subtle p-card-sm md:flex-row md:items-end">
          <Input label="Rank" value={p.rank} onChange={(e) => update(i, { rank: e.target.value })} className="flex-1" />
          <Input label="Reward" value={p.reward} onChange={(e) => update(i, { reward: e.target.value })} className="flex-1" />
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange(prizes.filter((_, idx) => idx !== i))}>
            Remove
          </Button>
        </div>
      ))}
      <Button type="button" variant="secondary" onClick={() => onChange([...prizes, { rank: '', reward: '' }])}>
        Add a prize
      </Button>
    </div>
  );
}
