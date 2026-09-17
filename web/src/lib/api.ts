/** Thin fetch wrapper: same-origin cookies, JSON in/out, readable errors. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function extractMessage(body: unknown): string | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const b = body as Record<string, unknown>;
  if (typeof b.detail === 'string') return b.detail;
  if (Array.isArray(b.detail) && b.detail[0] && typeof b.detail[0] === 'object') {
    const first = b.detail[0] as Record<string, unknown>;
    if (typeof first.msg === 'string') return first.msg;
  }
  return undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (res.status === 204) return undefined as T;
  const isJson = res.headers.get('content-type')?.includes('application/json');
  const body = isJson ? await res.json() : undefined;
  if (!res.ok) {
    const message = extractMessage(body);
    if (!message) {
      // Found live in Phase 5.3 (forced 500 by stopping the db container): the old
      // fallback surfaced the raw status code ("Request failed (500)."), which
      // brushes against PLAN.md 4.6's "no jargon like '500 Internal Server Error'".
      // The real code still goes to the console for whoever's debugging.
      console.error(`API request to ${path} failed with status ${res.status}`);
    }
    throw new ApiError(res.status, message ?? 'Something went wrong on our end. Please try again.');
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  /**
   * Trigger a file download. Kept here rather than as a bare <a href> so the
   * caller can show a loading state and surface a role rejection as a readable
   * message instead of the browser navigating to a raw 403 (PLAN.md 4.6).
   */
  async download(path: string, filename: string): Promise<void> {
    const res = await fetch(path, { credentials: 'include' });
    if (!res.ok) {
      let message = 'Could not export this file. Please try again.';
      try {
        const body = await res.json();
        if (typeof body?.detail === 'string') message = body.detail;
        else console.error(`Export ${path} failed with status ${res.status}`);
      } catch {
        console.error(`Export ${path} failed with status ${res.status} (non-JSON body)`);
      }
      throw new ApiError(res.status, message);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
