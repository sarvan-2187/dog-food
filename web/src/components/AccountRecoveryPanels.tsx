import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Badge, Button, Card, Input } from './ui';
import { ErrorState, SkeletonRows } from './feedback';
import { ApiError, api } from '../lib/api';
import type { EmailStatus, IssuedResetLink } from '../types';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function minutesLeft(iso: string): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 60000));
}

/**
 * PLAN.md Phase 9.4 - the fallback for when email is off, bounced, or the
 * person can't get into their mailbox. Same copy-and-send handover organizers
 * already know from judge invitations. The link is shown once: the server
 * keeps only a hash, so it can't be fetched again later.
 *
 * Organizers can reset participants and judges; admins can also reset
 * organizers. The server enforces that - this panel just reports its answer.
 */
export function HelpSignInPanel() {
  const [email, setEmail] = useState('');
  const [touched, setTouched] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<IssuedResetLink | null>(null);
  const [copied, setCopied] = useState(false);
  const [, tick] = useState(0);

  // Keep the "expires in N minutes" line honest while the link is on screen.
  useEffect(() => {
    if (!issued) return;
    const id = window.setInterval(() => tick((n) => n + 1), 15000);
    return () => window.clearInterval(id);
  }, [issued]);

  const emailError = touched && !EMAIL_PATTERN.test(email.trim()) ? 'Enter the email address on their account.' : undefined;

  async function create(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!EMAIL_PATTERN.test(email.trim())) return;
    setCreating(true);
    setError(null);
    setIssued(null);
    setCopied(false);
    try {
      setIssued(await api.post<IssuedResetLink>('/api/password-resets', { email: email.trim() }));
      setEmail('');
      setTouched(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create a reset link. Please try again.');
    } finally {
      setCreating(false);
    }
  }

  async function copy() {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Could not reach the clipboard - select the link below and copy it by hand.');
    }
  }

  const left = issued ? minutesLeft(issued.expires_at) : 0;

  return (
    <Card title="Help someone sign in" meta="Reset links">
      <div data-tour="help-sign-in" className="flex flex-col gap-4">
        <p className="text-body text-ink-600">
          If someone can't get into their account and the email reset isn't working for them, create a one-time
          link here and send it through your event's usual channel. It works once, for an hour.
        </p>
        <form className="flex flex-col gap-3 sm:flex-row sm:items-start" onSubmit={create} noValidate>
          <Input
            label="Their email"
            type="email"
            className="sm:w-80"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => email && setTouched(true)}
            error={emailError}
            placeholder="jordan@example.com"
          />
          <Button type="submit" variant="primary" loading={creating} loadingLabel="Creating..." className="sm:mt-7">
            Create reset link
          </Button>
        </form>

        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}

        {issued && (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-surface-100 p-card-sm">
            <p className="text-body text-ink-800">
              Link for <span className="font-medium">{issued.name}</span>{' '}
              <span className="text-ink-500">({issued.email})</span>
            </p>
            <code className="break-all rounded bg-surface-0 px-2 py-1.5 text-meta text-ink-800">{issued.url}</code>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="secondary" size="sm" onClick={copy}>
                {copied ? 'Copied' : 'Copy link'}
              </Button>
              <Badge status={left > 0 ? 'warning' : 'danger'}>
                {left > 0 ? `Expires in ${left} min` : 'Expired - create a new one'}
              </Badge>
            </div>
            <p className="text-meta text-ink-500">
              This is the only time the link is shown. Send it only to the person it's for - anyone holding it can
              set their password.
            </p>
            <span role="status" aria-live="polite" className="sr-only">
              {copied ? 'Link copied' : ''}
            </span>
          </div>
        )}
      </div>
    </Card>
  );
}

/**
 * PLAN.md Phase 9.3 - admin-only. Shows whether password reset emails are on
 * and lets an admin prove the settings work before anyone is locked out. The
 * SMTP password never reaches this page; the API does not return it.
 */
export function EmailDeliveryPanel() {
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  function load() {
    setLoadError(null);
    api
      .get<EmailStatus>('/api/admin/email')
      .then(setStatus)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : 'Could not load email settings.'));
  }

  useEffect(load, []);

  async function sendTest() {
    setSending(true);
    setResult(null);
    try {
      const r = await api.post<{ sent_to: string }>('/api/admin/email/test');
      setResult({ ok: true, message: `Sent to ${r.sent_to}. If it arrives, password reset emails will work.` });
    } catch (err) {
      setResult({ ok: false, message: err instanceof ApiError ? err.message : 'The test email could not be sent.' });
    } finally {
      setSending(false);
    }
  }

  return (
    <Card title="Email delivery" meta={status ? (status.enabled ? 'On' : 'Off') : undefined}>
      <div data-tour="email-delivery" className="flex flex-col gap-4">
        {loadError && <ErrorState description={loadError} onRetry={load} />}
        {!status && !loadError && <SkeletonRows rows={3} cols={2} />}

        {status && !status.enabled && (
          <div className="flex flex-col gap-2 text-body text-ink-600">
            <p>
              Email is <span className="font-medium text-ink-800">off</span>, so HackFlow makes no outbound
              connections. People who forget their password need an organizer to create a reset link for them.
            </p>
            <p className="text-meta text-ink-500">
              To turn on self-service resets, set <code>SMTP_HOST</code> and the other <code>SMTP_*</code> settings
              in a <code>.env</code> file next to <code>docker-compose.yml</code>, then restart the api container.
              The README's "Email (optional)" section has examples for Gmail, Outlook and a local test inbox.
            </p>
          </div>
        )}

        {status?.enabled && (
          <>
            <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1.5 text-meta">
              <dt className="text-ink-500">Server</dt>
              <dd className="break-all text-ink-800">
                {status.host}:{status.port}
              </dd>
              <dt className="text-ink-500">Security</dt>
              <dd className="text-ink-800">
                {status.security === 'none' ? 'None (local test inbox only)' : status.security.toUpperCase()}
              </dd>
              <dt className="text-ink-500">Sends as</dt>
              <dd className="break-all text-ink-800">{status.sender}</dd>
              <dt className="text-ink-500">Login</dt>
              <dd className="text-ink-800">{status.username_set ? 'Set (password hidden)' : 'None'}</dd>
              <dt className="text-ink-500">Links point to</dt>
              <dd className="break-all text-ink-800">{status.base_url}</dd>
            </dl>
            <div>
              <Button variant="secondary" loading={sending} loadingLabel="Sending..." onClick={sendTest}>
                Send test email
              </Button>
            </div>
            {result && (
              <p
                role={result.ok ? 'status' : 'alert'}
                className={result.ok ? 'text-meta text-success-fg' : 'text-meta text-danger-fg'}
              >
                {result.message}
              </p>
            )}
            <p className="text-meta text-ink-500">Changed a setting? Restart the api container for it to apply.</p>
          </>
        )}
      </div>
    </Card>
  );
}
