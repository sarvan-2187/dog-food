import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth-context';
import type { Role } from '../../types';
import { ErrorState } from '../feedback';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, status } = useAuth();
  if (status === 'loading') return null;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, status } = useAuth();
  if (status === 'loading') return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-section">
        <ErrorState title="You can't view this page" description="This area is limited to organizers and admins." />
      </div>
    );
  }
  return <>{children}</>;
}
