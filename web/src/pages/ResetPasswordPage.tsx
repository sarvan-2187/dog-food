import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AuthLayout } from '../components/auth/AuthLayout';
import { PasswordField } from '../components/auth/PasswordField';
import { SkeletonRows } from '../components/feedback';
import { Button } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { RedeemResult, ResetPreview } from '../types';

const DEAD_LINK: Record<string, string> = {
  used: 'This reset link has already been used.',
  expired: 'This reset link has expired.',
  unknown: "This reset link isn't valid - it may have been copied incompletely.",
};

/**
 * Where every reset link lands - emailed, organizer-issued, or printed by the
 * server CLI (PLAN.md Phase 9). Opening the page only previews the link;
 * nothing is used up until the new password is submitted, because mail
 * scanners open links on their own.
 */
export function ResetPasswordPage() {
  const { token = '' } = useParams();
  const { refresh } = useAuth();
  const [preview, setPreview] = useState<ResetPreview | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<RedeemResult | null>(null);

  useEffect(() => {
    api
      .get<ResetPreview>(`/api/password-resets/${encodeURIComponent(token)}/preview`)
      .then(setPreview)
      .catch(() => setLoadError(true));
  }, [token]);

  const passwordError = touched && password.length < 8 ? 'Use at least 8 characters.' : undefined;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (password.length < 8) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.post<RedeemResult>(`/api/password-resets/${encodeURIComponent(token)}/redeem`, {
        new_password: password,
      });
      await refresh(); // the response set a fresh session cookie
      setDone(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 410) {
        // Used or expired while the page sat open - show the dead-link state.
        const reason = err.message.includes('used') ? 'used' : 'expired';
        setPreview((p) => (p ? { ...p, valid: false, reason } : p));
      } else {
        setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
      }
    } finally {
      setSaving(false);
    }
  }

  const backToLogin = (
    <Link to="/login" className="text-ink-900 underline underline-offset-2">
      Back to log in
    </Link>
  );

  if (done) {
    return (
      <AuthLayout
        title="Password updated"
        subtitle="You're signed in, and every other device has been signed out."
        footer={backToLogin}
      >
        <div className="flex flex-col gap-4 text-body text-ink-700">
          {done.issued_by_name && (
            <p className="text-meta text-ink-500">This reset link was created for you by {done.issued_by_name}.</p>
          )}
          <Link to="/dashboard">
            <Button variant="primary" className="w-full">
              Go to your dashboard
            </Button>
          </Link>
        </div>
      </AuthLayout>
    );
  }

  if (loadError) {
    return (
      <AuthLayout title="Couldn't check this link" subtitle="Something went wrong on our end." footer={backToLogin}>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          Try again
        </Button>
      </AuthLayout>
    );
  }

  if (!preview) {
    return (
      <AuthLayout title="Choose a new password" subtitle="Checking your link..." footer={backToLogin}>
        <SkeletonRows rows={2} cols={1} />
      </AuthLayout>
    );
  }

  if (!preview.valid) {
    return (
      <AuthLayout
        title="This link can't be used"
        subtitle={DEAD_LINK[preview.reason] ?? DEAD_LINK.unknown}
        footer={backToLogin}
      >
        <div className="flex flex-col gap-4 text-body text-ink-700">
          {preview.email_enabled ? (
            <>
              <p>Reset links work once and expire after 30 minutes. You can send yourself a fresh one.</p>
              <Link to="/forgot-password">
                <Button variant="primary" className="w-full">
                  Send a new link
                </Button>
              </Link>
            </>
          ) : (
            <p>Ask your organizer for a new one - it only takes them a moment.</p>
          )}
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle={preview.first_name ? `Resetting the password for ${preview.first_name}.` : 'Pick something you will remember.'}
      footer={backToLogin}
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <PasswordField
          label="New password"
          required
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched(true)}
          error={passwordError}
          hint="At least 8 characters. This signs you out on every other device."
        />
        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" loading={saving} loadingLabel="Saving...">
          Save and sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
