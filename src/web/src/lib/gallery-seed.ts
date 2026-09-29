/**
 * One shuffle seed per browser session.
 *
 * PLAN.md Phase 3 asks that randomised ordering not cause layout jank on repeat
 * visits within a session. Generating the seed per render would reshuffle the
 * grid every time; sessionStorage keeps it stable for the tab's lifetime and
 * lets a new session see a genuinely different order.
 *
 * sessionStorage can throw (private mode, blocked site data), so a failure falls
 * back to a per-load seed rather than breaking the gallery.
 */
const KEY = 'dogfood.gallerySeed';

let memorySeed: number | null = null;

export function gallerySeed(): number {
  if (memorySeed !== null) return memorySeed;
  try {
    const stored = window.sessionStorage.getItem(KEY);
    if (stored !== null) {
      const parsed = Number(stored);
      if (Number.isFinite(parsed)) {
        memorySeed = parsed;
        return parsed;
      }
    }
  } catch {
    // storage unavailable; fall through to a fresh seed
  }

  const seed = Math.floor(Math.random() * 2_000_000_000);
  memorySeed = seed;
  try {
    window.sessionStorage.setItem(KEY, String(seed));
  } catch {
    // not persistable this session; the in-memory value still keeps one render stable
  }
  return seed;
}
