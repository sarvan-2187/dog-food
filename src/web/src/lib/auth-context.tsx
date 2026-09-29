import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, ApiError } from './api';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  status: 'loading' | 'ready';
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Re-read the session. Needed when the server changes the current user's
   *  role mid-session (accepting a judge invitation), since the nav is
   *  role-aware and would otherwise keep rendering the old role. */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready'>('loading');

  useEffect(() => {
    api
      .get<User>('/api/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setStatus('ready'));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setUser(await api.post<User>('/api/auth/login', { email, password }));
  }, []);

  const register = useCallback(async (email: string, password: string, name: string) => {
    setUser(await api.post<User>('/api/auth/register', { email, password, name }));
  }, []);

  const logout = useCallback(async () => {
    await api.post('/api/auth/logout');
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.get<User>('/api/auth/me'));
    } catch {
      // A failed refresh means the session is gone; reflect that rather than
      // leaving a stale user on screen.
      setUser(null);
    }
  }, []);

  return <AuthContext.Provider value={{ user, status, login, register, logout, refresh }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export { ApiError };
