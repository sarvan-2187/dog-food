import { Check } from 'lucide-react';
import { useState } from 'react';
import { ApiError, api } from '../lib/api';
import { cn } from '../lib/cn';
import type { EventRecord } from '../types';
import { Card } from './ui';

/** Keys match src/api/app/scoring/certificate.py TEMPLATES; the server refuses anything else. */
export const CERTIFICATE_DESIGNS = [
  { id: 'classic', label: 'Classic' },
  { id: 'gold', label: 'Classic gold' },
  { id: 'midnight', label: 'Midnight tech' },
  { id: 'gradient', label: 'Modern gradient' },
  { id: 'emerald', label: 'Emerald prestige' },
  { id: 'mono', label: 'Minimal mono' },
  { id: 'royal', label: 'Royal blue' },
  { id: 'pixel', label: 'Retro pixel' },
] as const;

/** Organizer picker for how an event's certificates look. A click saves. */
export function CertificateDesignPicker({
  event,
  onSaved,
  onToast,
}: {
  event: EventRecord;
  onSaved: (event: EventRecord) => void;
  onToast: (t: { message: string; ok: boolean }) => void;
}) {
  const [saving, setSaving] = useState<string | null>(null);
  const current = event.certificate_template ?? 'classic';

  async function choose(id: string, label: string) {
    if (id === current || saving) return;
    setSaving(id);
    try {
      onSaved(await api.patch<EventRecord>(`/api/events/${event.id}`, { certificate_template: id }));
      onToast({ message: `Certificates will use ${label}.`, ok: true });
    } catch (err) {
      onToast({ message: err instanceof ApiError ? err.message : 'Could not change the design.', ok: false });
    } finally {
      setSaving(null);
    }
  }

  return (
    <Card
      title="Certificate design"
      meta={CERTIFICATE_DESIGNS.find((d) => d.id === current)?.label}
      footer="Every team's certificate uses this design, with their names, project, prize and a verifiable serial. Change it any time, even after results are out."
    >
      <div role="radiogroup" aria-label="Certificate design" className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {CERTIFICATE_DESIGNS.map((d) => {
          const selected = d.id === current;
          return (
            <button
              key={d.id}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={saving !== null}
              onClick={() => choose(d.id, d.label)}
              className={cn(
                'group flex flex-col gap-2 rounded-lg border p-2 text-left transition-colors duration-base ease-standard',
                selected ? 'border-brand-500 ring-2 ring-brand-500' : 'border-border-subtle hover:border-border-strong',
                saving === d.id && 'opacity-60',
              )}
            >
              <img
                src={`/images/certificates/${d.id}.jpg`}
                alt=""
                loading="lazy"
                width={660}
                height={510}
                className="aspect-[22/17] w-full rounded-md object-cover"
              />
              <span className="flex items-center gap-1.5 text-meta text-ink-900">
                {selected && <Check size={14} aria-hidden="true" />}
                {d.label}
              </span>
            </button>
          );
        })}
      </div>
    </Card>
  );
}
