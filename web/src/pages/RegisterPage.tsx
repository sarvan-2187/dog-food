import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, useAuth } from '../lib/auth-context';
import { Button, Card, Input } from '../components/ui';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = searchParams.get('next') || '/events';
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
    <div className="mx-auto max-w-md px-4 py-section">
      <Card title="Create your account">
        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          <Input
            label="Name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, name: true }))}
            error={nameError}
          />
          <Input label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Input
            label="Password"
            type="password"
            required
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
          <p className="text-meta text-ink-500">
            Already have an account?{' '}
            <Link to="/login" className="text-brand-500">
              Log in
            </Link>
          </p>
        </form>
      </Card>
    </div>
  );
}
