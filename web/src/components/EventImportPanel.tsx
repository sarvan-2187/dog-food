import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Input } from './ui';
import { ApiError, api } from '../lib/api';
import type { EventBackup, EventRecord } from '../types';

/** A slug the server will accept: lowercase, digits, single hyphens. */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Restores a backup produced by an event's "Download event backup" button
 * (PLAN.md Phase 4 T4).
 *
 * The export nests the event's own fields under `event` while the import
 * endpoint takes them flat, so the flattening happens here rather than in
 * whatever the organizer's next idea of a JSON editor is.
 *
 * The slug is always editable and pre-filled with a free one, because
 * importing into the same database as the original is the normal case
 * ("duplicate last year's event") and a bare re-post would just 409.
 */
export function EventImportPanel({ onToast }: { onToast: (message: string, ok: boolean) => void }) {
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [backup, setBackup] = useState<EventBackup | null>(null);
  const [filename, setFilename] = useState('');
  const [slug, setSlug] = useState('');
  const [name, setName] = useState('');
  const [importing, setImporting] = useState(false);

  function reset() {
    setBackup(null);
    setFilename('');
    setSlug('');
    setName('');
    if (fileInput.current) fileInput.current.value = '';
  }

  async function onFile(file: File) {
    try {
      const parsed = JSON.parse(await file.text()) as EventBackup;
      if (!parsed?.event?.slug || !parsed.event.start_at) {
        throw new Error('shape');
      }
      setBackup(parsed);
      setFilename(file.name);
      setName(`${parsed.event.name} (copy)`);
      setSlug(slugify(`${parsed.event.slug}-copy`));
    } catch {
      reset();
      onToast('That file is not a HackFlow event backup. Use the JSON downloaded from an event’s settings.', false);
    }
  }

  async function runImport() {
    if (!backup) return;
    setImporting(true);
    try {
      const created = await api.post<EventRecord>('/api/events/import', {
        ...backup.event,
        slug: slugify(slug),
        name: name.trim() || backup.event.name,
        rubrics: backup.rubrics,
        teams: backup.teams,
        submissions: backup.submissions,
      });
      onToast(`Imported "${created.name}".`, true);
      reset();
      navigate(`/events/${created.slug}`);
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not import this event. Please try again.', false);
    } finally {
      setImporting(false);
    }
  }

  const slugError = slug.trim() && slugify(slug) !== slug.trim() ? 'Will be saved as ' + slugify(slug) : undefined;

  return (
    <Card title="Import an event" meta="From a backup file">
      <div className="flex flex-col gap-4">
        <p className="text-body text-ink-600">
          Restores an event backup as a brand new event, with its tracks, prizes, rubrics, teams and submissions.
          Judge assignments and scores are not restored - run assignment again on the new event.
        </p>

        <label className="flex flex-col gap-1.5">
          <span className="text-label text-ink-800">Backup file</span>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            className="text-body text-ink-700 file:mr-3 file:rounded-md file:border file:border-border file:bg-surface-0 file:px-3 file:py-1.5 file:text-label file:text-ink-800 hover:file:bg-surface-100"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onFile(file);
            }}
          />
          {filename && (
            <span className="text-meta text-ink-500">
              {filename} - {backup?.teams.length ?? 0} team{backup?.teams.length === 1 ? '' : 's'},{' '}
              {backup?.submissions.length ?? 0} submission{backup?.submissions.length === 1 ? '' : 's'}
            </span>
          )}
        </label>

        {backup && (
          <>
            <Input label="New event name" value={name} onChange={(e) => setName(e.target.value)} />
            <Input
              label="New URL slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              hint={slugError ?? 'Must be unique - the original event keeps its own slug.'}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                loading={importing}
                loadingLabel="Importing..."
                disabled={!slugify(slug)}
                onClick={runImport}
              >
                Import event
              </Button>
              <Button variant="ghost" onClick={reset} disabled={importing}>
                Cancel
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
