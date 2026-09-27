import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, useAuth } from '../lib/auth-context';
import { Button, Card, Input } from '../components/ui';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = searchParams.get('next') || '/events';
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
    <div className="mx-auto max-w-md px-4 py-section">
      <Card title="Log in">
        <form className="flex flex-col gap-4" onSubmit={onSubmit}>
          <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Input label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && (
            <p role="alert" className="text-meta text-danger-fg">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" loading={loading} loadingLabel="Signing in...">
            Log in
          </Button>
          <p className="text-meta text-ink-500">
            No account?{' '}
            <Link to="/register" className="text-brand-500">
              Sign up
            </Link>
          </p>
        </form>
      </Card>
    </div>
  );
}
