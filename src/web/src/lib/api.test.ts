import { describe, expect, it, vi, afterEach } from 'vitest';
import { ApiError, api } from './api';

function mockResponse(status: number, body: unknown, contentType = 'application/json') {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: () => contentType },
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => vi.unstubAllGlobals());

describe('api error surfacing', () => {
  it('uses the server detail string as the message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(409, { detail: 'An account with this email already exists.' })));
    await expect(api.post('/api/auth/register', {})).rejects.toThrow('An account with this email already exists.');
  });

  it('pulls the first message out of a FastAPI validation error array', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(422, { detail: [{ msg: 'Team name must be 3-40 characters.' }] })));
    await expect(api.post('/api/teams/join', {})).rejects.toThrow('Team name must be 3-40 characters.');
  });

  it('falls back to a plain-language message, never a bare status code alone', async () => {
    // Found live in Phase 5.3 (forced 500 by stopping the db container): this test's
    // name promised the fallback never leaks a bare status code, but the assertion
    // below only checked the rejection's type, not its message - so it never actually
    // caught the "Request failed (500)." bug it was named after. Asserting the message
    // content now closes that gap.
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(500, undefined, 'text/html')));
    await expect(api.get('/api/events')).rejects.toThrow('Something went wrong on our end. Please try again.');
  });

  it('carries the status so callers can treat 404 and 409 as expected states', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(404, { detail: 'No submission started yet.' })));
    await api.get('/api/teams/1/submission').catch((err) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
    });
  });

  it('returns undefined for 204 rather than trying to parse a body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(204, undefined)));
    await expect(api.post('/api/auth/logout')).resolves.toBeUndefined();
  });
});
