import { useEffect, useState } from 'react';
import { Badge, Button, Card, Input, RoleBadge } from './components/ui';
import {
  EmptyState,
  ErrorState,
  InlineStatus,
  SkeletonRows,
  Toast,
  ToastRegion,
} from './components/feedback';

type Health = 'checking' | 'ok' | 'unreachable';

/**
 * Phase 0 shell: proves the tokens and shared primitives render, and reports
 * API health. Feature pages replace this from Phase 1 onward.
 */
export default function App() {
  const [health, setHealth] = useState<Health>('checking');
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/healthz')
      .then((r) => (r.ok ? 'ok' : 'unreachable'))
      .catch(() => 'unreachable')
      .then((next) => {
        if (!cancelled) setHealth(next as Health);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border-subtle bg-surface-0">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-4 md:px-6">
          <span className="text-h3 text-ink-900">Dogfood 2026</span>
          {health === 'checking' && <Badge status="info">Checking API</Badge>}
          {health === 'ok' && <Badge status="success">API healthy</Badge>}
          {health === 'unreachable' && <Badge status="danger">API unreachable</Badge>}
        </div>
      </header>

      <main className="mx-auto flex max-w-[1200px] flex-col gap-section px-4 py-section md:px-6">
        <section className="flex flex-col gap-4">
          <p className="text-eyebrow uppercase text-ink-400">Phase 0 - bootstrap</p>
          <h1 className="max-w-prose text-h1 text-ink-900">
            Shared primitives are in place. Feature work starts at Phase 1.
          </h1>
          <p className="max-w-prose text-body-lg text-ink-600">
            Every screen from here consumes these components rather than re-solving loading, empty
            and error markup per page.
          </p>
        </section>

        <div className="grid gap-6 md:grid-cols-2">
          <Card title="Buttons" meta="DESIGN_SYSTEM 7.1" footer="One primary action per view.">
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="primary" onClick={() => setToast('Primary action confirmed')}>
                Primary
              </Button>
              <Button>Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="danger">Delete</Button>
              <Button variant="primary" loading>
                Primary
              </Button>
            </div>
          </Card>

          <Card title="Inputs" meta="DESIGN_SYSTEM 7.2">
            <div className="flex flex-col gap-4">
              <Input label="Team name" placeholder="CodeHawk" hint="3-40 characters." />
              <Input
                label="Event slug"
                defaultValue="!!"
                error="Slug must be lowercase letters, numbers and dashes."
              />
            </div>
          </Card>

          <Card title="Badges" meta="DESIGN_SYSTEM 7.5 / 2.6">
            <div className="flex flex-wrap items-center gap-2">
              <Badge status="success">Submitted</Badge>
              <Badge status="warning">Results hidden</Badge>
              <Badge status="danger">Deadline passed</Badge>
              <Badge status="info">Draft</Badge>
              <RoleBadge role="participant" />
              <RoleBadge role="judge" />
              <RoleBadge role="organizer" />
              <RoleBadge role="admin" />
            </div>
          </Card>

          <Card title="Autosave indicator" meta="DESIGN_SYSTEM 7.7">
            <div className="flex flex-wrap items-center gap-4">
              <InlineStatus state="saving" />
              <InlineStatus state="saved" />
              <InlineStatus state="unsaved" />
            </div>
          </Card>

          <Card title="Loading" meta="DESIGN_SYSTEM 7.7">
            <SkeletonRows rows={4} />
          </Card>

          <Card title="Empty and error" meta="DESIGN_SYSTEM 7.7">
            <EmptyState
              title="No submissions yet"
              description="Be the first to submit - your draft saves as you type."
              action={<Button variant="primary">Start a submission</Button>}
            />
            <ErrorState onRetry={() => setToast('Retrying')} />
          </Card>
        </div>
      </main>

      <ToastRegion>
        {toast && <Toast status="success" message={toast} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
