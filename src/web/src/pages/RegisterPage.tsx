import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, useAuth } from '../lib/auth-context';
import { AuthLayout } from '../components/auth/AuthLayout';
import { PasswordField } from '../components/auth/PasswordField';
import { Button, Input } from '../components/ui';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = searchParams.get('next') || '/dashboard';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const nameError = touched.name && name.trim().length < 2 ? 'Name must be at least 2 characters.' : undefined;
  const passwordError = touched.password && password.length < 8 ? 'Password must be at least 8 characters.' : undefined;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched({ name: true, password: true });
    if (name.trim().length < 2 || password.length < 8) return;
    setError(null);
    setLoading(true);
    try {
      await register(email, password, name);
      navigate(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      title="Create an account"
      subtitle="Join a hackathon, form a team, and ship something this weekend."
      footer={
        <>
          {/* Stated plainly rather than offered as a dead role picker: the API
              creates participants only, by design (src/api/app/auth/router.py). */}
          Signing up creates a <strong className="font-medium text-ink-800">participant</strong> account.
          Judge and organizer access is granted by an event organizer.{' '}
          <Link to="/login" className="text-ink-900 underline underline-offset-2">
            Already have an account?
          </Link>
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <Input
          label="Name"
          required
          autoComplete="name"
          placeholder="Ada Lovelace"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, name: true }))}
          error={nameError}
        />
        <Input
          label="Email"
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <PasswordField
          label="Password"
          required
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onBlur={() => setTouched((t) => ({ ...t, password: true }))}
          error={passwordError}
          hint={passwordError ? undefined : 'At least 8 characters.'}
        />
        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" loading={loading} loadingLabel="Creating account...">
          Sign up
        </Button>
      </form>
    </AuthLayout>
  );
}
