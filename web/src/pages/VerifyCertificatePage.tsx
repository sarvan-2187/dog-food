import { BadgeCheck, SearchX } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Badge, Button, Card, Input } from '../components/ui';
import { SkeletonRows } from '../components/feedback';
import { api } from '../lib/api';
import type { CertificateRecord } from '../types';

/**
 * Public, no sign-in: anyone holding a HackFlow certificate (an employer, a
 * university) can confirm it is genuine and see exactly what it certifies.
 * The serial is printed at the bottom of every certificate.
 */
export function VerifyCertificatePage() {
  const { serial = '' } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState<CertificateRecord | null>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'found' | 'missing'>(serial ? 'loading' : 'idle');
  const [input, setInput] = useState(serial);

  useEffect(() => {
    if (!serial) return;
    setState('loading');
    api
      .get<CertificateRecord>(`/api/certificates/${encodeURIComponent(serial)}`)
      .then((r) => {
        setRecord(r);
        setState('found');
      })
      .catch(() => {
        // Forged, mistyped and not-yet-public all read the same by design.
        setRecord(null);
        setState('missing');
      });
  }, [serial]);

  function lookUp(e: FormEvent) {
    e.preventDefault();
    if (input.trim()) navigate(`/verify/${encodeURIComponent(input.trim())}`);
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-section">
      <header>
        <p className="text-eyebrow uppercase text-ink-400">HackFlow by Hackathon Raptors</p>
        <h1 className="mt-1 text-h1 text-ink-900">Verify a certificate</h1>
        <p className="mt-2 text-body-lg text-ink-500">
          Enter the code printed at the bottom of the certificate, like <span className="font-mono">HF-12-3F9A0C71B2</span>.
        </p>
      </header>

      <form onSubmit={lookUp} className="flex flex-col items-start gap-3 sm:flex-row sm:items-end">
        <Input label="Certificate code" value={input} onChange={(e) => setInput(e.target.value)} className="self-stretch sm:flex-1" />
        <Button type="submit" variant="primary">Check</Button>
      </form>

      {state === 'loading' && <SkeletonRows rows={3} cols={1} />}

      {state === 'found' && record && (
        <Card
          className="rounded-xl"
          title={
            <span className="flex items-center gap-2">
              <BadgeCheck size={20} aria-hidden="true" className="text-success-fg" /> Genuine certificate
            </span>
          }
          meta={<span className="font-mono">{record.serial}</span>}
        >
          <dl className="grid gap-3 text-body sm:grid-cols-[10rem_1fr]">
            <dt className="text-ink-500">Awarded to</dt>
            <dd className="text-ink-900">{record.members.join(', ') || record.team_name}</dd>
            <dt className="text-ink-500">Team</dt>
            <dd className="text-ink-900">{record.team_name}</dd>
            <dt className="text-ink-500">Event</dt>
            <dd className="text-ink-900">
              <Link to={`/events/${record.event_slug}`} className="underline underline-offset-2">
                {record.event_name}
              </Link>{' '}
              <span className="text-ink-500">({record.event_dates})</span>
            </dd>
            <dt className="text-ink-500">Project</dt>
            <dd className="text-ink-900">{record.submission_title}</dd>
            {(record.rank || record.prizes.length > 0) && (
              <>
                <dt className="text-ink-500">Result</dt>
                <dd className="flex flex-wrap gap-2">
                  {record.prizes.map((p) => (
                    <Badge key={p} status="success">{p}</Badge>
                  ))}
                  {record.rank && <Badge status="info">Final rank #{record.rank}</Badge>}
                </dd>
              </>
            )}
          </dl>
        </Card>
      )}

      {state === 'missing' && (
        <Card className="rounded-xl" title={<span className="flex items-center gap-2"><SearchX size={20} aria-hidden="true" /> No match</span>}>
          <p className="text-body text-ink-600">
            No certificate matches <span className="font-mono">{serial}</span>. Check the code for typos. A certificate
            also can't be verified until its event's results are public.
          </p>
        </Card>
      )}
    </div>
  );
}
