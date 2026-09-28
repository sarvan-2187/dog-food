import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ImageUpload } from '../components/ImageUpload';
import { Button, Card, RoleBadge } from '../components/ui';
import { useAuth } from '../lib/auth-context';

/**
 * Post-login account controls live here, not in the header - the header
 * stays identical to raptors.dev's real one (wordmark + hamburger only)
 * regardless of auth state, per an explicit request. Reached via "Profile"
 * in the hamburger menu, only shown once a user is signed in.
 */
export function ProfilePage() {
  const { user, logout, refresh } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  if (!user) return null; // RequireAuth already redirects; guards against a render race.

  async function onLogout() {
    setLoading(true);
    try {
      await logout();
      navigate('/');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-section">
      <Card title="Your profile">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <RoleBadge role={user.role} />
          </div>
          <ImageUpload
            uploadUrl="/api/users/me/avatar"
            currentUrl={user.avatar_url}
            label="avatar"
            shape="circle"
            responseKey="avatar_url"
            onUploaded={() => refresh()}
          />
          <dl className="flex flex-col gap-3">
            <div>
              <dt className="text-label text-ink-500">Name</dt>
              <dd className="text-body text-ink-800">{user.name}</dd>
            </div>
            <div>
              <dt className="text-label text-ink-500">Email</dt>
              <dd className="text-body text-ink-800">{user.email}</dd>
            </div>
          </dl>
          <Button
            variant="secondary"
            loading={loading}
            loadingLabel="Signing out..."
            onClick={onLogout}
            className="self-start"
          >
            Log out
          </Button>
        </div>
      </Card>
    </div>
  );
}
