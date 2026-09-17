import { AnimatePresence, motion, useReducedMotion, type Variants } from 'framer-motion';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Button, Card, MetricTile } from '../components/ui';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { EventRecord, Submission } from '../types';

gsap.registerPlugin(ScrollTrigger);

const EASE = [0.2, 0, 0.2, 1] as const;

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE } },
};

const stagger = (delayChildren = 0.08): Variants => ({
  hidden: {},
  visible: { transition: { staggerChildren: delayChildren } },
});

/** Scroll-reveal wrapper: fades a section's content up once, the first time it enters view. */
function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduceMotion ? undefined : 'hidden'}
      whileInView="visible"
      viewport={{ once: true, margin: '-80px' }}
      variants={fadeUp}
      transition={{ duration: 0.6, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}

/**
 * DESIGN_SYSTEM.md §10 — built here for the first time in Phase 5. §3/§10 called
 * for this from Phase 0 onward; it was never built across Phases 0-3 (the root
 * route just redirected into the app). Composition follows §10's nine sections
 * exactly; copy is honest about what this platform actually does, not borrowed
 * stats from hackraptors.pdf (that PDF informs README positioning only — see
 * PLAN.md Open Questions). Motion layer: Framer Motion drives entrance/scroll
 * reveals declaratively; GSAP + ScrollTrigger owns the two effects that need
 * imperative sequencing (the decision-trail rows, the hero's ambient glow).
 */
export function LandingPage() {
  const { user } = useAuth();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [submissions, setSubmissions] = useState<Submission[] | null>(null);
  const reduceMotion = useReducedMotion();
  const glowRef = useRef<HTMLDivElement>(null);
  const trailRef = useRef<HTMLTableSectionElement>(null);
  const stepsRef = useRef<HTMLDivElement>(null);

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

  // Ambient hero glow — a slow, continuous drift that has no scroll trigger of
  // its own, which is exactly the kind of tween GSAP is for and Framer's
  // viewport-driven variants are not.
  useEffect(() => {
    if (reduceMotion || !glowRef.current) return;
    const tween = gsap.to(glowRef.current, {
      x: 60,
      y: -30,
      scale: 1.15,
      duration: 10,
      ease: 'sine.inOut',
      repeat: -1,
      yoyo: true,
    });
    return () => {
      tween.kill();
    };
  }, [reduceMotion]);

  // Decision trail — rows step in one at a time as the table scrolls into
  // view, so the "trail" reads left-to-right, top-to-bottom like a sequence
  // rather than appearing all at once.
  useEffect(() => {
    if (reduceMotion || !trailRef.current) return;
    const rows = trailRef.current.querySelectorAll('tr');
    const ctx = gsap.context(() => {
      gsap.set(rows, { opacity: 0, x: -16 });
      gsap.to(rows, {
        opacity: 1,
        x: 0,
        duration: 0.5,
        ease: 'power2.out',
        stagger: 0.12,
        scrollTrigger: {
          trigger: trailRef.current,
          start: 'top 82%',
        },
      });
    });
    return () => ctx.revert();
  }, [reduceMotion]);

  // Accent band steps — a top border line "draws" left-to-right while the
  // five steps fade up behind it, reinforcing the submit→reveal pipeline.
  useEffect(() => {
    if (reduceMotion || !stepsRef.current) return;
    const line = stepsRef.current.querySelector('[data-role="accent-line"]');
    const steps = stepsRef.current.querySelectorAll('[data-role="step"]');
    const ctx = gsap.context(() => {
      gsap.set(line, { scaleX: 0, transformOrigin: 'left center' });
      gsap.set(steps, { opacity: 0, y: 16 });
      gsap
        .timeline({ scrollTrigger: { trigger: stepsRef.current, start: 'top 85%' } })
        .to(line, { scaleX: 1, duration: 0.8, ease: 'power2.inOut' })
        .to(steps, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out', stagger: 0.1 }, '-=0.4');
    });
    return () => ctx.revert();
  }, [reduceMotion]);

  const primaryTo = user ? '/events' : '/register';
  const primaryLabel = user ? 'Go to your events' : 'Get started';

  return (
    <div className="flex flex-col">
      {/* 2. Hero */}
      <section className="relative overflow-hidden border-b border-border-subtle bg-brand-25 px-4 py-hero md:px-6">
        <div
          ref={glowRef}
          aria-hidden="true"
          className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-brand-500/20 blur-3xl"
        />
        <motion.div
          className="relative mx-auto max-w-[1200px]"
          initial={reduceMotion ? undefined : 'hidden'}
          animate="visible"
          variants={stagger(0.1)}
        >
          <motion.p variants={fadeUp} className="text-eyebrow uppercase text-brand-700">
            Judging, without the spreadsheet
          </motion.p>
          <motion.h1 variants={fadeUp} className="mt-4 max-w-prose text-display text-ink-900">
            From submission to <span className="font-serif italic text-ink-900">verdict.</span> One workspace.
          </motion.h1>
          <motion.p variants={fadeUp} className="mt-4 max-w-prose text-body-lg text-ink-600">
            Teams submit. Judges score against a locked rubric. Normalization cancels out who grades hard.
            Results reveal on a schedule everyone agreed to in advance.
          </motion.p>
          <motion.div variants={fadeUp} className="mt-6 flex flex-wrap items-center gap-3">
            <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
              <Link to={primaryTo}>
                <Button variant="primary">{primaryLabel}</Button>
              </Link>
            </motion.div>
            <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
              <Link to="/gallery">
                <Button variant="ghost">Explore the gallery</Button>
              </Link>
            </motion.div>
          </motion.div>

          <motion.div
            variants={stagger(0.08)}
            className="mt-12 grid gap-6 border-t border-border-subtle pt-8 md:grid-cols-3"
          >
            <motion.div variants={fadeUp} className="h-full">
              <ClaimItem term="Deterministic" description="The same inputs always produce the same judge assignment." />
            </motion.div>
            <motion.div variants={fadeUp} className="h-full">
              <ClaimItem term="Conflict-aware" description="A judge is never assigned a submission from their own team." />
            </motion.div>
            <motion.div variants={fadeUp} className="h-full">
              <ClaimItem term="Policy-controlled" description="Results stay hidden until the reveal time the event set." />
            </motion.div>
          </motion.div>
          <motion.p variants={fadeUp} className="mt-6 text-meta text-ink-500">
            Built for organizers, judges, and the teams building.
          </motion.p>
        </motion.div>
      </section>

      {/* 3. Product proof */}
      <section className="px-4 py-section md:px-6">
        <div className="mx-auto grid max-w-[1200px] gap-8 md:grid-cols-12">
          <Reveal className="md:col-span-4">
            <p className="text-eyebrow uppercase text-ink-400">The decision workspace</p>
            <h2 className="mt-2 text-h2 text-ink-900">Built for the moment a submission becomes a decision.</h2>
            <p className="mt-3 text-body text-ink-600">
              Every entry moves through the same accountable pipeline. Only the rubric and the reveal
              clock decide what gets seen, and when.
            </p>
            <Link to="/events" className="mt-3 inline-block text-label text-brand-500">
              See the current event →
            </Link>
          </Reveal>
          <Reveal className="md:col-span-8" delay={0.1}>
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
          </Reveal>
        </div>
      </section>

      {/* 4. Numbered list */}
      <section className="border-t border-border-subtle bg-surface-100 px-4 py-section md:px-6">
        <div className="mx-auto grid max-w-[1200px] gap-8 md:grid-cols-12">
          <Reveal className="md:col-span-4">
            <p className="text-eyebrow uppercase text-ink-400">How judging stays fair</p>
          </Reveal>
          <Reveal className="md:col-span-8" delay={0.1}>
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
          </Reveal>
        </div>
      </section>

      {/* 5. Timeline / trail (illustrative — the real audit log is organizer/admin only) */}
      <section className="px-4 py-section md:px-6">
        <div className="mx-auto max-w-[1200px]">
          <Reveal>
            <p className="text-eyebrow uppercase text-ink-400">Decision trail</p>
            <p className="mt-2 max-w-prose text-body-lg text-ink-600">
              Every system contribution is timestamped and attributable. Illustrative example below — the
              real trail is in the organizer-only audit log.
            </p>
          </Reveal>
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
              <tbody ref={trailRef}>
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
          <Reveal>
            <p className="text-eyebrow uppercase text-ink-400">What's built</p>
          </Reveal>
          <motion.div
            className="mt-6 flex w-full min-w-0 max-w-full items-stretch gap-4 overflow-x-auto pb-2"
            initial={reduceMotion ? undefined : 'hidden'}
            whileInView="visible"
            viewport={{ once: true, margin: '-80px' }}
            variants={stagger(0.08)}
          >
            <CapabilityCard n="01" lead="Assign fairly." rest="Conflict-aware, load-balanced, deterministic." to="/events" />
            <CapabilityCard n="02" lead="Score consistently." rest="A locked rubric and a live running total." to="/events" />
            <CapabilityCard n="03" lead="Rank honestly." rest="Per-judge normalization, not a raw average." to="/events" />
            <CapabilityCard n="04" lead="Reveal on schedule." rest="Results hidden until everyone can see them at once." to="/gallery" />
          </motion.div>
        </div>
      </section>

      {/* 7. Dashboard preview (illustrative) */}
      <section className="px-4 py-section md:px-6">
        <div className="mx-auto grid max-w-[1200px] gap-8 md:grid-cols-12">
          <Reveal className="md:col-span-4">
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
          </Reveal>
          <Reveal className="md:col-span-8" delay={0.1}>
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
          </Reveal>
        </div>
      </section>

      {/* 8. Accent band */}
      <section ref={stepsRef} className="bg-brand-500 px-4 py-section text-surface-0 md:px-6">
        <div className="mx-auto max-w-[1200px]">
          <Reveal>
            <p className="text-eyebrow uppercase text-surface-0/70">Governed judging, start to finish</p>
          </Reveal>
          <div className="relative mt-8 grid gap-6 pt-8 md:grid-cols-5">
            <div data-role="accent-line" className="absolute left-0 top-0 h-px w-full bg-surface-0/20" />
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
          <Reveal className="md:col-span-4">
            <p className="text-eyebrow uppercase text-ink-400">09 — FAQ</p>
            <h2 className="mt-2 text-h1 text-ink-900">
              Ask. <span className="font-serif italic">Learn.</span> Build.
            </h2>
          </Reveal>
          <Reveal className="md:col-span-8" delay={0.1}>
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
          </Reveal>
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
  // h-full so the md:border-l divider runs the full height of the tallest claim
  // instead of stopping at its own text.
  return (
    <div className="h-full border-t border-border-subtle pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0 first:md:border-l-0 first:md:pl-0">
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
  // The row is `flex items-stretch`, so the item is already stretched to the
  // tallest card — and it must NOT carry `h-full` itself: an explicit height on a
  // flex item defeats the stretch (a flex line's cross-size isn't definite when
  // the percentage resolves), which is what left these four ragged at 255/221/
  // 221/255. The stretch goes on the item, `h-full` goes on the Link inside it,
  // and only then does `justify-between` have spare height to distribute.
  return (
    <motion.div
      variants={fadeUp}
      whileHover={{ y: -6 }}
      transition={{ duration: 0.25, ease: EASE }}
      className="shrink-0"
    >
      <Link
        to={to}
        className="flex h-full w-64 flex-col justify-between rounded-lg border border-border bg-surface-0 p-card shadow-sm transition-shadow duration-base ease-standard hover:shadow-md"
      >
        <p className="text-right font-mono text-meta text-ink-400">{n}</p>
        <div className="mt-4">
          <p className="text-h3">
            <span className="text-brand-500">{lead}</span> <span className="text-ink-800">{rest}</span>
          </p>
        </div>
        <span className="mt-4 text-label text-brand-500">Explore feature →</span>
      </Link>
    </motion.div>
  );
}

function StepItem({ n, label, value, last }: { n: string; label: string; value: string; last?: boolean }) {
  return (
    <div data-role="step" className={last ? '' : 'md:border-r md:border-surface-0/20 md:pr-6'}>
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
 * visually hidden) while expanded. Rows toggle independently. Framer Motion
 * animates the panel's height/opacity instead of popping it in instantly.
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
              <motion.span
                aria-hidden="true"
                animate={{ rotate: open ? 45 : 0 }}
                transition={{ duration: 0.2, ease: EASE }}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border text-ink-600"
              >
                +
              </motion.span>
            </button>
            <AnimatePresence initial={false}>
              {open && (
                <motion.div
                  id={panelId}
                  key="content"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.25, ease: EASE }}
                  className="overflow-hidden"
                >
                  <p className="max-w-prose pb-5 text-body text-ink-600">{item.a}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
