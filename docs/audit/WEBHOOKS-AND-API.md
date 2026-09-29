# Webhooks and API check (task 5)

## How it was checked

`api/tests/test_webhooks_live.py`, on top of the existing `test_webhooks.py` and
`test_integrations.py`:

- **A real receiver.** A local HTTP server subscribes through the API
  (`POST /api/events/{id}/webhooks`); organizer actions are performed through the
  API; every queued delivery is POSTed to the server for real. Each body is JSON,
  carries the right topic and event, and its Ed25519 signature verifies against the
  key served at `GET /api/public-key`. A tampered body does not verify.
- **Receiver answers.** 200 and 204 record `delivered`; 404, 500 and 302 record
  `failed`, and the 302's `Location` is never followed.
- **Every API route** (all 150+ in the OpenAPI schema), for anonymous, participant,
  judge, organizer and admin callers, with placeholder ids and empty bodies: no 5xx.
  The same sweep of every GET route with the official fixtures seeded and each path
  id pointing at a real row: no 5xx. Every route is in the OpenAPI document except
  the embeddable widget, which is HTML by design.
- **Anonymous writes.** Every mutating route refuses a caller with no identity,
  except the ones that exist to create one (register, login, password reset) or to
  take an anonymous vote where the event allows it.

## Found and fixed

| # | Problem | Fix |
|---|---------|-----|
| W1 | `_deliver` caught only `httpx.HTTPError`. A malformed URL raises `httpx.InvalidURL`, which is not one, so the worker thread died with the error and `last_status` was never written: the organizer saw a stale status. | Any exception is a failed delivery, logged and recorded. |
| W2 | Deleting a webhook recorded `webhook.deleted` before deleting the row, so the removed URL was sent one last signed payload after the organizer removed it. | The row is deleted and flushed first. |
| W3 | Payloads had no unique id, so a receiver could not tell a retry or a replay from a new event. | Every signed record carries a random `delivery_id` (24 hex characters) alongside `issued_at`. |
| W4 | Every payload includes a copy of the public key, and the docs did not say not to trust it. Anyone can sign with their own key and put that key in the body. | The API description now says to pin the key from `GET /api/public-key`, never the copy in the payload. |

Delivery stays best-effort (one attempt, 5 s timeout), as PLAN.md 7.3 decided. The
webhook target itself is a security question (SSRF), covered in
`docs/audit/SECURITY-AUDIT.md`.
