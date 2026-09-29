import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { AuthLayout } from '../components/auth/AuthLayout';
import { SkeletonRows } from '../components/feedback';
import { Button, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * PLAN.md Phase 9.2. With email set up, this is the whole recovery process -
 * no organizer involved. With email off it says so honestly and points at an
 * organizer (9.4) instead of pretending to send something.
 *
 * The confirmation is the same whether or not the address has an account, so
 * this page can't be used to find out who is registered.
 */
export function ForgotPasswordPage() {
  const [emailEnabled, setEmailEnabled] = useState<boolean | null>(null);
  const [email, setEmail] = useState('');
  const [touched, setTouched] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<{ email: boolean }>('/api/auth/recovery-options')
      .then((r) => setEmailEnabled(r.email))
      // If we can't tell, the organizer route always works.
      .catch(() => setEmailEnabled(false));
  }, []);

  const emailError = touched && !EMAIL_PATTERN.test(email.trim()) ? 'Enter the email address you signed up with.' : undefined;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!EMAIL_PATTERN.test(email.trim())) return;
    setSending(true);
    setError(null);
    try {
      const r = await api.post<{ message: string }>('/api/auth/forgot-password', { email: email.trim() });
      setSent(r.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setSending(false);
    }
  }

  const footer = (
    <>
      Remembered it?{' '}
      <Link to="/login" className="text-ink-900 underline underline-offset-2">
        Back to log in
      </Link>
    </>
  );

  if (emailEnabled === null) {
    return (
      <AuthLayout title="Forgot your password?" subtitle="One moment..." footer={footer}>
        <SkeletonRows rows={2} cols={1} />
      </AuthLayout>
    );
  }

  if (!emailEnabled) {
    return (
      <AuthLayout
        title="Forgot your password?"
        subtitle="An organizer can get you back in within a minute."
        footer={footer}
      >
        <div className="flex flex-col gap-3 text-body text-ink-700">
          <p>
            This HackFlow doesn't send email, so there's no link to request here. Ask an organizer at the help
            desk or in your event's channel - they can make you a one-time reset link.
          </p>
          <p className="text-meta text-ink-500">
            The link works once and expires after an hour, so open it as soon as you get it.
          </p>
        </div>
      </AuthLayout>
    );
  }

  if (sent) {
    return (
      <AuthLayout title="Check your email" subtitle={sent} footer={footer}>
        <div className="flex flex-col gap-3 text-body text-ink-700">
          <p>
            Sent to <span className="font-medium text-ink-900">{email.trim()}</span>. Open the link in the email to
            choose a new password.
          </p>
          <p className="text-meta text-ink-500">
            Nothing after a few minutes? Check your spam folder, then try again - or ask an organizer for a reset
            link instead.
          </p>
          <div>
            <Button
              variant="secondary"
              onClick={() => {
                setSent(null);
                setTouched(false);
              }}
            >
              Use a different address
            </Button>
          </div>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Forgot your password?"
      subtitle="Enter your email and we'll send you a link to choose a new one."
      footer={footer}
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Input
          label="Email"
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onBlur={() => setTouched(true)}
          error={emailError}
        />
        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" loading={sending} loadingLabel="Sending...">
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  );
}
