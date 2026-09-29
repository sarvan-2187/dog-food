/**
 * The guided tour (src/lib/tour.ts) auto-starts once per role on first login and
 * overlays the page with a spotlight the user must dismiss. Every spec that logs
 * in would otherwise be racing its 700ms start timer: fast specs slip past it,
 * slow ones get their clicks intercepted. That is flakiness by construction, so
 * the suite pre-seeds the tour's own "already seen" flags instead of hoping to
 * out-run it.
 *
 * `tour.spec.ts` deliberately opts back out of this, and is the one place the
 * tour is actually exercised.
 */
const ROLES = ['participant', 'judge', 'organizer', 'admin'] as const;

export function tourSuppressed(origin: string) {
  return {
    cookies: [],
    origins: [
      {
        origin,
        localStorage: ROLES.map((role) => ({
          name: `hackflow.tour.seen.${role}`,
          value: '1',
        })),
      },
    ],
  };
}
