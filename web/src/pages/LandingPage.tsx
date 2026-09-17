import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Button, Card, MetricTile } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { EventRecord, Submission } from '../types';

/**
 * DESIGN_SYSTEM.md §10 — built here for the first time in Phase 5. §3/§10 called
 * for this from Phase 0 onward; it was never built across Phases 0-3 (the root
 * route just redirected into the app). Composition follows §10's nine sections
 * exactly; copy is honest about what this platform actually does, not borrowed
 * stats from hackraptors.pdf (that PDF informs README positioning only — see
 * PLAN.md Open Questions).
 */
export function LandingPage() {
  const { user } = useAuth();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [submissions, setSubmissions] = useState<Submission[] | null>(null);

  useEffect(() => {
    api
      .get<EventRecord[]>('/api/events')
      .then((events) => setEvent(events[0] ?? null))
      .catch(() => setEvent(null));
    api
      .get<Submission[]>('/api/gallery')
      .then(setSubmissions)
      .catch(() => setSubmissions(null));
  }, []);

  const primaryTo = user ? '/events' : '/register';
  const primaryLabel = user ? 'Go to your events' : 'Get started';

  return (
    <div className="flex flex-col">
      {/* 2. Hero */}
      <section className="border-b border-border-subtle bg-brand-25 px-4 py-hero md:px-6">
        <div className="mx-auto max-w-[1200px]">
          <p className="text-eyebrow uppercase text-brand-700">Judging, without the spreadsheet</p>
          <h1 className="mt-4 max-w-prose text-display text-ink-900">
            From submission to <span className="font-serif italic text-ink-900">verdict.</span> One workspace.
          </h1>
          <p className="mt-4 max-w-prose text-body-lg text-ink-600">
            Teams submit. Judges score against a locked rubric. Normalization cancels out who grades hard.
            Results reveal on a schedule everyone agreed to in advance.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Link to={primaryTo}>
              <Button variant="primary">{primaryLabel}</Button>
            </Link>
            <Link to="/gallery">
              <Button variant="ghost">Explore the gallery</Button>
            </Link>
          </div>

          <div className="mt-12 grid gap-6 border-t border-border-subtle pt-8 md:grid-cols-3">
            <ClaimItem term="Deterministic" description="The same inputs always produce the same judge assignment." />
            <ClaimItem term="Conflict-aware" description="A judge is never assigned a submission from their own team." />
            <ClaimItem term="Policy-controlled" description="Results stay hidden until the reveal time the event set." />
          </div>
          <p className="mt-6 text-meta text-ink-500">Built for organizers, judges, and the teams building.</p>
        </div>
      </section>

      {/* 3. Product proof */}
      <section className="px-4 py-section md:px-6">
        <div className="mx-auto grid max-w-[1200px] gap-8 md:grid-cols-12">
          <div className="md:col-span-4">
            <p className="text-eyebrow uppercase text-ink-400">The decision workspace</p>
            <h2 className="mt-2 text-h2 text-ink-900">Built for the moment a submission becomes a decision.</h2>
            <p className="mt-3 text-body text-ink-600">
              Every entry moves through the same accountable pipeline. Only the rubric and the reveal
              clock decide what gets seen, and when.
            </p>
            <Link to="/events" className="mt-3 inline-block text-label text-brand-500">
              See the current event →
            </Link>
          </div>
          <div className="md:col-span-8">
            <Card
              title={event ? event.name : 'No event yet'}
              meta={event ? 'PREVIEW / LIVE DATA' : undefined}
              footer="Real data from this deployment — not a mockup."
            >
              <div className="grid gap-4 md:grid-cols-2">
                <MetricTile
                  label="Submissions in the gallery"
                  value={submissions ? submissions.length : '—'}
                  accent
                  caption={event ? event.tracks.join(', ') || 'No tracks configured' : undefined}
                />
                <MetricTile
                  label="Deadline"
                  value={event ? new Date(event.end_at).toLocaleDateString() : '—'}
                  caption={event ? new Date(event.end_at).toLocaleTimeString() : undefined}
                />
              </div>
              {submissions && submissions.length > 0 && (
                <ul className="mt-4 flex flex-col gap-2 border-t border-border-subtle pt-4">
                  {submissions.slice(0, 3).map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-3 text-body text-ink-700">
                      <span className="truncate">{s.title || 'Untitled submission'}</span>
                      <Badge status={s.status === 'submitted' ? 'success' : 'info'}>{s.status}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      </section>

      {/* 4. Numbered list */}
      <section className="border-t border-border-subtle bg-surface-100 px-4 py-section md:px-6">
        <div className="mx-auto grid max-w-[1200px] gap-8 md:grid-cols-12">
          <div className="md:col-span-4">
            <p className="text-eyebrow uppercase text-ink-400">How judging stays fair</p>
          </div>
          <div className="md:col-span-8">
            <p className="max-w-prose text-body-lg text-ink-600">
              Three rules, enforced by the server on every write — not a convention anyone has to remember.
            </p>
            <ol className="mt-6 flex flex-col">
              <NumberedRow n="01" title="Deterministic assignment" active>
                Judges are assigned round-robin by current load, ties broken by judge ID. Re-running the
                assignment never produces a different result or a duplicate.
              </NumberedRow>
              <NumberedRow n="02" title="A rubric that locks">
                Criteria and weights lock the moment any score exists for the event — a rubric edit can
                never silently invalidate scores already given.
              </NumberedRow>
              <NumberedRow n="03" title="Normalized, not raw">
                A harsh judge and a lenient one are put on the same scale before ranking, using each
                judge's own mean and spread.
              </NumberedRow>
            </ol>
          </div>
        </div>
      </section>

      {/* 5. Timeline / trail (illustrative — the real audit log is organizer/admin only) */}
      <section className="px-4 py-section md:px-6">
        <div className="mx-auto max-w-[1200px]">
          <p className="text-eyebrow uppercase text-ink-400">Decision trail</p>
          <p className="mt-2 max-w-prose text-body-lg text-ink-600">
            Every system contribution is timestamped and attributable. Illustrative example below — the
            real trail is in the organizer-only audit log.
          </p>
          <div className="mt-6 overflow-hidden rounded-lg border border-border">
            <table className="w-full text-left text-body">
              <thead className="bg-surface-100">
                <tr className="text-eyebrow uppercase text-ink-400">
                  <th scope="col" className="px-4 py-3 font-normal">
                    Elapsed
                  </th>
                  <th scope="col" className="px-4 py-3 font-normal">
                    System contribution
                  </th>
                  <th scope="col" className="px-4 py-3 text-right font-normal">
                    Outcome
                  </th>
                </tr>
              </thead>
              <tbody>
                <TrailRow t="00:00.0" label="Submission received" value="Flake Finder — Developer Tools" />
                <TrailRow t="+04:12" label="Assignment run" value="3 judges, 0 conflicts" />
                <TrailRow t="+51:03" label="Scores recorded" value="3 of 3 judges" />
                <TrailRow t="+51:04" label="Normalization" value="Ranked #2 of 4" />
                <TrailRow t="+72:00" label="Results revealed" value="Published" status="success" last />
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* 6. Capability cards */}
      <section className="[overflow-x:clip] border-t border-border-subtle bg-surface-100 px-4 py-section md:px-6">
        <div className="mx-auto max-w-[1200px]">
          <p className="text-eyebrow uppercase text-ink-400">What's built</p>
          <div className="mt-6 flex w-full min-w-0 max-w-full gap-4 overflow-x-auto pb-2">
            <CapabilityCard n="01" lead="Assign fairly." rest="Conflict-aware, load-balanced, deterministic." to="/events" />
            <CapabilityCard n="02" lead="Score consistently." rest="A locked rubric and a live running total." to="/events" />
            <CapabilityCard n="03" lead="Rank honestly." rest="Per-judge normalization, not a raw average." to="/events" />
            <CapabilityCard n="04" lead="Reveal on schedule." rest="Results hidden until everyone can see them at once." to="/gallery" />
          </div>
        </div>
      </section>

      {/* 7. Dashboard preview (illustrative) */}
      <section className="px-4 py-section md:px-6">
        <div className="mx-auto grid max-w-[1200px] gap-8 md:grid-cols-12">
          <div className="md:col-span-4">
            <p className="text-eyebrow uppercase text-ink-400">See it in action</p>
            <h2 className="mt-2 text-h2 text-ink-900">Your entire event, in one view.</h2>
            <p className="mt-3 text-body text-ink-600">
              Follow a submission from its first draft to a published, normalized result.
            </p>
            <Link to="/events">
              <Button variant="primary" className="mt-4">
                Open the workspace
              </Button>
            </Link>
          </div>
          <div className="md:col-span-8">
            <Card title="Event overview" meta="Illustrative preview">
              <div className="grid gap-4 md:grid-cols-3">
                <MetricTile label="Teams" value="12" />
                <MetricTile label="Submissions" value="9" />
                <MetricTile label="Judges assigned" value="4" />
              </div>
              <ul className="mt-4 flex flex-col gap-2 border-t border-border-subtle pt-4 text-body text-ink-700">
                <li className="flex items-center justify-between">
                  <span>Flake Finder</span>
                  <Badge status="warning">Review</Badge>
                </li>
                <li className="flex items-center justify-between">
                  <span>Standup Digest</span>
                  <Badge status="success">Scored</Badge>
                </li>
              </ul>
            </Card>
          </div>
        </div>
      </section>

      {/* 8. Accent band */}
      <section className="bg-brand-500 px-4 py-section text-surface-0 md:px-6">
        <div className="mx-auto max-w-[1200px]">
          <p className="text-eyebrow uppercase text-surface-0/70">Governed judging, start to finish</p>
          <div className="mt-8 grid gap-6 border-t border-surface-0/20 pt-8 md:grid-cols-5">
            <StepItem n="01" label="Submit" value="Draft, autosave" />
            <StepItem n="02" label="Assign" value="Conflict-aware" />
            <StepItem n="03" label="Score" value="Locked rubric" />
            <StepItem n="04" label="Normalize" value="Per-judge z-score" />
            <StepItem n="05" label="Reveal" value="On schedule" last />
          </div>
        </div>
      </section>

      {/* FAQ - accordion, same left-label/right-content split as sections 4/6 */}
      <section className="border-t border-border-subtle px-4 py-section md:px-6">
        <div className="mx-auto grid max-w-[1200px] gap-8 md:grid-cols-12">
          <div className="md:col-span-4">
            <p className="text-eyebrow uppercase text-ink-400">09 — FAQ</p>
            <h2 className="mt-2 text-h1 text-ink-900">
              Ask. <span className="font-serif italic">Learn.</span> Build.
            </h2>
          </div>
          <div className="md:col-span-8">
            <FaqAccordion
              items={[
                {
                  q: 'How is a judge assigned to a submission?',
                  a: 'Round-robin by current load, excluding any judge on the submitting team, with ties broken by judge ID. Re-running the assignment never produces a different result or a duplicate — see JUDGING.md.',
                },
                {
                  q: 'Can an organizer change the rubric after judging starts?',
                  a: 'No. Criteria and weights lock the moment any score exists for the event, so a rubric edit can never silently invalidate scores already given.',
                },
                {
                  q: "Why doesn't the raw average decide the ranking?",
                  a: 'A harsh judge and a lenient one are put on the same scale first, using each judge’s own mean and spread, before anything is ranked — a raw average would let one judge’s grading style skew the result.',
                },
                {
                  q: 'When do vote counts and results become visible?',
                  a: 'Not until the reveal time the event set. Enforced in the API response itself, not just hidden in the interface, so early counts can never sway the vote.',
                },
                {
                  q: 'What happens if I miss the submission deadline?',
                  a: 'The server rejects the write the moment the deadline passes — the countdown on your submission page is the same clock the server enforces, so it is never a surprise.',
                },
              ]}
            />
          </div>
        </div>
      </section>

      {/* 9. Footer */}
      <footer className="px-4 py-8 md:px-6">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-h3 text-ink-900">Dogfood 2026</p>
            <p className="text-meta text-ink-500">Hackathon judging, accountable by design.</p>
          </div>
          <nav className="flex gap-4 text-label text-ink-700">
            <Link to="/events">Events</Link>
            <Link to="/gallery">Gallery</Link>
            <Link to="/login">Log in</Link>
          </nav>
        </div>
        <div className="mx-auto mt-6 max-w-[1200px] border-t border-border-subtle pt-4 text-meta text-ink-500">
          Team CodeHawk · Built for events like Hackathon Raptors runs.
        </div>
      </footer>
    </div>
  );
}

function ClaimItem({ term, description }: { term: string; description: string }) {
  return (
    <div className="border-t border-border-subtle pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0 first:md:border-l-0 first:md:pl-0">
      <p className="text-label font-semibold text-ink-900">{term}</p>
      <p className="mt-1 text-body text-ink-600">{description}</p>
    </div>
  );
}

function NumberedRow({ n, title, active, children }: { n: string; title: string; active?: boolean; children: string }) {
  return (
    <li className={active ? 'border-b border-border-subtle border-l-2 border-l-brand-500 pl-3 -ml-[calc(0.75rem+2px)]' : 'border-b border-border-subtle'}>
      <div className="flex gap-4 py-4">
        <span className="font-mono text-meta text-ink-400">{n}</span>
        <div>
          <p className="text-h3 text-ink-800">{title}</p>
          <p className="mt-1 text-body text-ink-600">{children}</p>
        </div>
      </div>
    </li>
  );
}

function TrailRow({
  t,
  label,
  value,
  status,
  last,
}: {
  t: string;
  label: string;
  value: string;
  status?: 'success';
  last?: boolean;
}) {
  return (
    <tr className={last ? 'bg-success-bg' : undefined}>
      <td className={`px-4 py-3 font-mono text-mono text-ink-400 ${last ? '' : 'border-b border-border-subtle'}`}>{t}</td>
      <td className={`px-4 py-3 text-ink-700 ${last ? '' : 'border-b border-border-subtle'}`}>{label}</td>
      <td
        className={`px-4 py-3 text-right ${last ? 'font-semibold text-success-fg' : 'border-b border-border-subtle text-ink-600'}`}
      >
        {status ? <Badge status="success">{value}</Badge> : value}
      </td>
    </tr>
  );
}

function CapabilityCard({ n, lead, rest, to }: { n: string; lead: string; rest: string; to: string }) {
  return (
    <Link
      to={to}
      className="flex w-64 shrink-0 flex-col justify-between rounded-lg border border-border bg-surface-0 p-card"
    >
      <p className="text-right font-mono text-meta text-ink-400">{n}</p>
      <div className="mt-4">
        <p className="text-h3">
          <span className="text-brand-500">{lead}</span> <span className="text-ink-800">{rest}</span>
        </p>
      </div>
      <span className="mt-4 text-label text-brand-500">Explore feature →</span>
    </Link>
  );
}

function StepItem({ n, label, value, last }: { n: string; label: string; value: string; last?: boolean }) {
  return (
    <div className={last ? '' : 'md:border-r md:border-surface-0/20 md:pr-6'}>
      <p className="font-mono text-meta text-surface-0/60">{n}</p>
      <p className="mt-2 text-eyebrow uppercase text-surface-0/70">{label}</p>
      <p className="mt-1 text-h3 text-surface-0">{value}</p>
    </div>
  );
}

interface FaqItem {
  q: string;
  a: string;
}

/**
 * The reference screenshot's accordion pattern: hairline-divided rows, a
 * +/- toggle at the far right, each row's answer only in the DOM (not just
 * visually hidden) while expanded. Rows toggle independently.
 */
function FaqAccordion({ items }: { items: FaqItem[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(1);

  return (
    <div className="flex flex-col border-t border-border-subtle">
      {items.map((item, i) => {
        const open = openIndex === i;
        const panelId = `faq-panel-${i}`;
        return (
          <div key={item.q} className="border-b border-border-subtle">
            <button
              type="button"
              aria-expanded={open}
              aria-controls={panelId}
              onClick={() => setOpenIndex(open ? null : i)}
              className="flex w-full items-center justify-between gap-4 py-5 text-left"
            >
              <span className="text-h3 text-ink-800">{item.q}</span>
              <span
                aria-hidden="true"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border text-ink-600"
              >
                {open ? '−' : '+'}
              </span>
            </button>
            {open && (
              <p id={panelId} className="max-w-prose pb-5 text-body text-ink-600">
                {item.a}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
