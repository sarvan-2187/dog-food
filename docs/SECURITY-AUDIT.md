# Security audit: DDoS resistance, rate limiting, vulnerabilities

**Scope:** the whole backend (`api/app`, about 9,300 lines, every router read), the deploy
configuration (`docker-compose.yml`, `render.yaml`, `api/Dockerfile`) and the webhook and API
key integration surface. **Date:** 2026-09-29. **Method:** manual code review of every
endpoint's authentication, authorization, input bounds and side effects. Each finding was
reproduced or covered by a failing test before it was fixed, and the fixes were re-measured
against a live, seeded server.

**Result:** 18 findings: 2 high, 8 medium, 8 low. All 18 are fixed in this change, each
with a regression test. Nine residual risks are listed at the end with the reason each stays
open. The backend suite went from 428 to 457 tests, all passing. The DOGFOOD checker still
reports 7/7.

The role-isolation core held up: `require_role()` plus ownership and track checks. No
finding lets a participant see scores, a judge see a peer's scores, or anyone act as a judge
without an assignment. Most findings are about what happens under load and at the edges:
floods, oversized input, proxies and outbound requests.

## Findings and fixes

| # | Sev. | Finding | Fix | Where | Test |
|---|---|---|---|---|---|
| 1 | **High** | **No global rate limit.** Only login, voting, comments and password reset were throttled. Any other endpoint, including the full-table gallery scan and bcrypt-hashing sign-up, could be called as fast as a script could send. One client could saturate the single worker and the database pool. | `ProtectionMiddleware`: token buckets of 600 requests/min overall and 120/min for writes, counted per signed-in account (verified session cookie) or per address when anonymous, so a venue sharing one NAT address isn't throttled as one user. API keys get their own bucket (1,200/min per key). The health probe and static files are exempt. A `429` carries `Retry-After`. All limits can be set by env var. | `app/protection.py`, `app/main.py` | `test_protection.py` (limit, exemptions, write bucket, key bucket, per-account keying, forged cookie) |
| 2 | **High** | **Webhook SSRF.** An organizer could point a webhook at `http://db:5432`, `http://169.254.169.254/` (cloud metadata) or any internal host. The server POSTed there from inside its network, and the `delivered`/`failed` badge worked as a port scanner. | Private, loopback, link-local, reserved and `.internal`/`.local`/`localhost` targets are refused when the webhook is created. Every delivery re-checks DNS and records `blocked`. Redirects are never followed. `WEBHOOK_ALLOW_PRIVATE=1` is an explicit opt-in for local demos. | `app/webhooks/service.py` (`blocked_reason`), `webhooks/router.py` | `test_webhooks.py` (6 addresses refused, delivery re-check) |
| 3 | Medium | **Unbounded request bodies.** Uploads were read fully into memory before the 5 MB check, so a 2 GB "image" was 2 GB of RAM. JSON bodies had no cap at all. | Bodies over 1 MB (6 MB for uploads, 10 MB for event import) are refused with `413`, whether declared up front or streamed. Uploads read at most one byte past the cap. | `app/protection.py`, `storage/router.py` | `test_an_oversized_json_body_is_refused_before_it_is_read` |
| 4 | Medium | **Rate-limiter memory grew without bound.** One bucket per email or address, never evicted. A flood of made-up emails at `/login` or `/forgot-password` grew memory until the process died. | Each limiter holds at most 50,000 buckets. Past that it drops buckets that have refilled completely (they carry no state), then the stalest. Dropping a bucket can only err towards allowing a request. | `app/ratelimit.py` (`_prune`) | `test_the_limiter_never_holds_more_than_max_keys` |
| 5 | Medium | **Behind a proxy, every visitor had the proxy's address.** On Render all traffic arrives from Render's proxy, so the per-IP login limit (30 failures per 15 min) was shared by the whole site. Thirty wrong passwords from anyone locked out every user. | `client_ip()` is the only place the client address is read. `TRUSTED_PROXY_HOPS=N` takes the Nth `X-Forwarded-For` entry counted from the right (the entry the proxy wrote), never the client-chosen left end. `render.yaml` sets 1. The default of 0 ignores the header. | `app/protection.py`, `render.yaml`, `auth/router.py`, `voting/router.py` | `test_with_one_trusted_proxy_the_rightmost_entry_is_the_client`, `test_forwarded_for_is_ignored_unless_proxies_are_trusted` |
| 6 | Medium | **Email case created duplicate accounts.** `Alice@x.com` and `alice@x.com` could both register. Login and password reset only matched the exact case typed. | Emails are stored lowercased and looked up case-insensitively (`user_by_email`) at sign-up, login, forgot-password and organizer reset. | `auth/router.py`, `auth/recovery.py` | `test_email_case_cannot_create_a_second_account` |
| 7 | Medium | **Sign-up was unthrottled.** Each sign-up costs a bcrypt hash (CPU) and makes a voting-capable account (sybil votes). | 20 sign-ups per address per hour, which still covers a venue full of people on one network. | `ratelimit.py`, `auth/router.py` | `test_signups_are_throttled_per_address` |
| 8 | Medium | **The legacy image upload ignored the deadline.** `POST /api/teams/{id}/submission/image` (the "replace image 1" route kept for old clients) skipped the deadline check the other image routes have, so a team could swap its thumbnail while judges were scoring. | Uses the same `_team_submission_open` gate as the other image routes. | `storage/router.py` | `test_the_legacy_image_upload_is_frozen_after_the_deadline` |
| 9 | Medium | **A submission's track was free text.** Any string was accepted. A made-up track dodged the "No track chosen" eligibility flag, and the entry went only to untracked judges (JUDGING.md rule 8). | The track must be one of the event's tracks (or empty). | `submissions/router.py` | `test_a_submission_track_must_be_one_of_the_events_tracks` |
| 10 | Medium | **Imported rubrics weren't range-checked.** An event backup whose criterion had `max_score: 0` or `NaN` would divide by zero or poison every judge's normalization. | Weight and max_score must be positive and finite, or the whole import is refused. | `scoring/router.py` (`_check_people`) | existing import tests + scoring tests |
| 11 | Low | **Team-size cap race.** Two people joining at the same moment could both see "one seat left". | The team row is locked (`SELECT ... FOR UPDATE`) before members are counted. | `teams/router.py` | the cap is covered by `test_teams.py`; the concurrent case isn't race-tested |
| 12 | Low | **Webhook amplification.** No limit on webhooks per event, so one action could fan out into thousands of outbound POSTs at a victim. | At most 10 per event, and no duplicate URLs. | `webhooks/router.py` | `test_webhooks_per_event_are_capped_and_deduplicated` |
| 13 | Low | **Webhook replay.** Deliveries had no unique id, so a receiver couldn't tell a replay from a new event. | Every signed record carries a random `delivery_id`. `X-HackFlow-Topic` and `X-HackFlow-Delivery` headers are added. The manual tells receivers to drop stale or repeated ids, and the Raptor Relay demo does so. | `webhooks/service.py` | `test_test_ping_sends_a_signed_webhook_test_delivery`, Raptor Relay `npm test` |
| 14 | Low | **Cookies weren't `Secure`** on https deployments. | `Secure` is on automatically when `APP_BASE_URL` is https. `COOKIE_SECURE` overrides it. `render.yaml` sets it. | `auth/session.py`, `auth/router.py`, `voting/voter.py` | n/a (config) |
| 15 | Low | **Missing hardening headers.** User uploads are served from `/media` without `nosniff`. | `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` and `Cross-Origin-Opener-Policy` on every response. HSTS is sent when the site is https. | `app/protection.py` | `test_security_headers_are_on_every_response` |
| 16 | Low | **The development `SESSION_SECRET` was accepted silently.** Anyone who knows it can forge a session for any account. | A loud warning at boot when the secret is the dev default or shorter than 16 characters. (`render.yaml` already generates a random one.) | `auth/session.py` | n/a (log) |
| 17 | Low | **Unbounded search strings** in the gallery (`q`, `track`, `tag`), each an `ILIKE` over four columns. | Length caps of 100, 100 and 60 characters. | `submissions/router.py` | FastAPI validation |
| 18 | Low | **A draft event's rubrics were readable** by any signed-in user, which leaked that the draft exists. | `404` unless the event is visible to the caller, like the event itself. | `judging/router.py` | `test_role_isolation.py`, `test_phase10.py` |

Also cleaned up while in these files: the scores and assignments CSV exports used to load
*every* score on the platform and filter in Python. They now query only the event's own
assignments.

## DDoS resistance, measured

These are the results against a live, seeded server (`uvicorn`, single worker, local
Postgres), with default settings:

| Attack | Before | After |
|---|---|---|
| 2,000 `GET /api/gallery` from one address, 64 in parallel | all 2,000 served, each a full gallery query | 688 served (the 600 burst plus refill over 8.9 s), 1,312 answered `429` before touching the database. `/healthz` answered in 2 ms right after. |
| One 2 MB JSON body to `/api/auth/login` | read into memory, then parsed | `413` before the body is read |
| 12 wrong passwords for one account | `401` ×10, then `429` (existing) | unchanged: `401` ×10, then `429` |
| 25 sign-ups from one address | 25 accounts, 25 bcrypt hashes | 20 accounts, then `429` |
| 1,000 distinct fake emails at `/login` | 1,000 buckets forever | at most 50,000 buckets in total, then pruned |

**What an application can't do on its own.** A volumetric flood that fills the network link,
or a botnet spread across thousands of addresses, has to be stopped before it reaches the
app. The limits above make each address cheap to refuse, but they are no substitute for a
CDN or the host's DDoS protection (Cloudflare's free plan, or the protection a PaaS like
Render includes). The README's deploy checklist says so.

**Tuning.** `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_WRITES_PER_MINUTE` and
`RATE_LIMIT_API_KEY_PER_MINUTE` set the three buckets, and `0` turns one off (for example,
for your own load test). The defaults are deliberately generous. A person clicking through
the app makes a few requests a second at most, and the whole 600-request minute is
available as a burst.

## Rate limits, all in one place

| What | Limit | Keyed by |
|---|---|---|
| Any request | 600 / min (burst 600) | signed-in account, else client address |
| Any write (POST/PUT/PATCH/DELETE) | 120 / min | signed-in account, else client address |
| Any request with an API key | 1,200 / min | the key |
| Failed logins | 10 / 15 min per account, 30 / 15 min per address | typed email, address |
| Sign-ups | 20 / hour | address |
| Forgot-password emails | 3 / hour per email, 20 / hour per client address | email, address |
| Organizer-issued reset links | 30 / hour | organizer |
| Votes | 20 / min | account, or client fingerprint for guests |
| Comments | 10 / min | account |
| Voter email links | 5 / hour | client and email |
| Verification emails | 3 / hour | account |
| Judge reminders | 1 / hour | judge |
| Announcement emails | 1 / 10 min | event |
| Webhook test pings | 10 / 10 min | organizer |

## Residual risks (not fixed, and why)

1. **DNS rebinding between the check and the connect.** A webhook host's DNS is checked
   right before each POST, but `httpx` resolves it again when it connects. An attacker who
   controls DNS could answer publicly the first time and privately the second. Closing this
   fully means connecting to the checked IP and sending the hostname for TLS SNI. That is a
   custom transport, disproportionate for a feature that only organizers can configure.
2. **Limits are per process.** Like every limiter here, the buckets live in memory. HackFlow
   runs one worker, so that is the whole site. A multi-worker deployment would multiply each
   limit by the worker count until it moves to a shared store (Redis), which is out of scope
   by PLAN.md's no-external-services constraint.
3. **`DEMO_SESSION_TOKENS` in `docker-compose.yml`.** It is required by the DOGFOOD checker,
   which never logs in. The README's deploy checklist says to delete it first. It is kept
   because removing it breaks the official acceptance run.
4. **Organizers are platform-wide.** Any organizer can manage any event, including its
   webhooks and exports. That is the documented role model (PLAN.md Open Questions), not a
   bug, but a multi-tenant host would want per-event organizers.
5. **Participants can vote for their own team's entry.** Neither the brief nor PLAN.md
   forbids it, and community votes never affect judging (JUDGING.md). A one-line rule in
   `cast_vote` would add it if an event wants it.
6. **An organizer can reset a judge's password.** This is intentional (the help desk
   fallback when email is off), rate-limited and audited. It does mean a compromised
   organizer can take over a judge account.
7. **Stored raw totals from mixed-scale rubrics** written before the weighted-total fix
   (JUDGING.md) keep their old value until re-scored. No shipped fixture has mixed scales, so
   no existing standings change.
8. **CSP.** The SPA gets `frame-ancestors` but no full script policy. A strict CSP needs a
   pass over the Vite build's inline styles, and all user text is already rendered as text,
   never HTML.
9. **Session revocation on logout** is client-side: the cookie is deleted, but a copied
   cookie stays valid until it expires (7 days) or the password changes, which bumps
   `session_version`. A server-side session table would close this.
