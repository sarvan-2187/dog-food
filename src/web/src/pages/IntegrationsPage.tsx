import { Copy, KeyRound, Webhook } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { ApiKeyRecord } from '../types';

/**
 * Where an organizer connects HackFlow to everything else: API keys for
 * servers that call in, and pointers to the webhooks that call out.
 */
export function IntegrationsPage() {
  return (
    <RequireRole roles={['organizer', 'admin']}>
      <Integrations />
    </RequireRole>
  );
}

function Integrations() {
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);
  const onToast = (message: string, ok: boolean) => setToast({ message, ok });
  const base = window.location.origin;

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 py-10 md:px-8">
      <header>
        <h1 className="text-h1 text-ink-900">Integrations</h1>
        <p className="mt-2 max-w-2xl text-body-lg text-ink-500">
          Every action in HackFlow is an API endpoint. Connect a Discord bot, a CRM, a results feed or your own
          scripts with an API key, and hear about events as they happen through webhooks.
        </p>
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
          <ApiKeysCard onToast={onToast} />
          <Card title="Call the API" className="rounded-xl" meta="REST · JSON">
            <div className="flex flex-col gap-4 text-body text-ink-600">
              <p>
                Send your key as a bearer token. It acts as you, with your role, so it can do exactly what you can do in
                the app and nothing more.
              </p>
              <pre className="overflow-x-auto rounded-md bg-navy-900 p-4 font-mono text-meta text-surface-0">
                {`curl ${base}/api/events \\\n  -H "Authorization: Bearer hf_your_key"`}
              </pre>
              <p className="flex flex-wrap gap-x-4 gap-y-2">
                <a href="/docs" target="_blank" rel="noreferrer" className="text-ink-900 underline underline-offset-2">
                  Interactive API reference
                </a>
                <a href="/redoc" target="_blank" rel="noreferrer" className="text-ink-900 underline underline-offset-2">
                  Readable API docs
                </a>
                <a href="/openapi.json" target="_blank" rel="noreferrer" className="text-ink-900 underline underline-offset-2">
                  OpenAPI spec (JSON)
                </a>
              </p>
            </div>
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <Card title="Webhooks" className="rounded-xl">
            <div className="flex flex-col gap-3 text-body text-ink-600">
              <Webhook size={20} aria-hidden="true" className="text-ink-500" />
              <p>
                HackFlow can call your URL when a project is submitted, judges are assigned, a score arrives, an
                announcement is posted or results go live.
              </p>
              <p>
                Each event has its own webhooks: open the event, then <strong>Event settings → Webhooks</strong>. Every
                payload is signed, and can be checked against the key at{' '}
                <a href="/api/public-key" className="underline underline-offset-2">/api/public-key</a>.
              </p>
              <Link to="/events" className="text-ink-900 underline underline-offset-2">
                Choose an event
              </Link>
            </div>
          </Card>
          <Card title="Embed the gallery" className="rounded-xl">
            <p className="text-body text-ink-600">
              Put an event's projects on your own site with one line of HTML: <strong>Event settings → Embed on your site</strong>.
            </p>
          </Card>
        </div>
      </div>

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}

function ApiKeysCard({ onToast }: { onToast: (message: string, ok: boolean) => void }) {
  const [keys, setKeys] = useState<ApiKeyRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [fresh, setFresh] = useState<{ name: string; key: string } | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .get<ApiKeyRecord[]>('/api/api-keys')
      .then(setKeys)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load your keys.'));
  }, []);
  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const made = await api.post<ApiKeyRecord & { key: string }>('/api/api-keys', { name });
      setFresh({ name: made.name, key: made.key });
      setName('');
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not create the key.', false);
    } finally {
      setCreating(false);
    }
  }

  async function revoke(k: ApiKeyRecord) {
    if (!window.confirm(`Revoke "${k.name}"? Anything using it stops working immediately.`)) return;
    try {
      await api.del(`/api/api-keys/${k.id}`);
      onToast(`"${k.name}" was revoked.`, true);
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not revoke the key.', false);
    }
  }

  async function copy(key: string) {
    try {
      await navigator.clipboard.writeText(key);
      onToast('Key copied.', true);
    } catch {
      onToast('Copy failed. Select the key and copy it by hand.', false);
    }
  }

  return (
    <Card title="API keys" className="rounded-xl" meta={keys ? `${keys.length} active` : undefined}>
      <div className="flex flex-col gap-5">
        <form onSubmit={create} className="flex flex-col items-start gap-3 sm:flex-row sm:items-end">
          <Input
            label="New key name"
            placeholder="Discord bot"
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
            className="self-stretch sm:flex-1"
          />
          <Button type="submit" variant="primary" loading={creating} loadingLabel="Creating..." disabled={!name.trim()}>
            <KeyRound size={15} aria-hidden="true" /> Create key
          </Button>
        </form>

        {fresh && (
          <div role="status" className="flex flex-col gap-2 rounded-lg border border-border bg-warning-bg p-4">
            <p className="text-label text-warning-fg">Copy "{fresh.name}" now. It won't be shown again.</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded bg-surface-0 px-2 py-1.5 font-mono text-meta text-ink-900">
                {fresh.key}
              </code>
              <Button variant="secondary" size="sm" onClick={() => copy(fresh.key)}>
                <Copy size={14} aria-hidden="true" /> Copy
              </Button>
            </div>
          </div>
        )}

        {error && <ErrorState description={error} onRetry={load} />}
        {!keys && !error && <SkeletonRows rows={2} cols={2} />}
        {keys?.length === 0 && (
          <EmptyState title="No keys yet" description="Create one for each integration, so you can revoke them one at a time." />
        )}
        {keys && keys.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle" aria-label="Your API keys">
            {keys.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <span className="min-w-0">
                  <span className="block text-body text-ink-800">{k.name}</span>
                  <span className="block font-mono text-meta text-ink-500">
                    hf_{k.hint}… · created {new Date(k.created_at).toLocaleDateString()} ·{' '}
                    {k.last_used_at ? `last used ${new Date(k.last_used_at).toLocaleString()}` : 'never used'}
                  </span>
                </span>
                <Button variant="ghost" size="sm" onClick={() => revoke(k)}>
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
