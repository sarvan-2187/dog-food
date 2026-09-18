import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, useAuth } from '../lib/auth-context';
import { AuthLayout } from '../components/auth/AuthLayout';
import { PasswordField } from '../components/auth/PasswordField';
import { Button, Input } from '../components/ui';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = searchParams.get('next') || '/dashboard';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to pick up where your team left off."
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="text-ink-900 underline underline-offset-2">
            Create an account
          </Link>
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
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
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" loading={loading} loadingLabel="Signing in...">
          Log in
        </Button>
      </form>
    </AuthLayout>
  );
}
