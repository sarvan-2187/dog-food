import type { EventRecord } from '../types';

/**
 * Cover art for an event card.
 *
 * Events carry an optional `cover_image_url` (set by the organizer, or by the
 * fixtures for the demo events). When one isn't set, fall back to a stable
 * picture from the bundled set rather than a grey box: an events grid with
 * holes in it reads as broken, not as "no image yet". The fallback is keyed off
 * the slug so the same event always gets the same picture across reloads and
 * across machines - a random pick would reshuffle the whole grid on every
 * render.
 *
 * Photos are CC-licensed; see public/images/attribution.json and CREDITS.md.
 */
const FALLBACKS = [
  '/images/covers/cover-ai-agents.jpg',
  '/images/covers/cover-devtools.jpg',
  '/images/covers/cover-climate.jpg',
  '/images/covers/cover-women-in-tech.jpg',
  '/images/covers/cover-fintech.jpg',
  '/images/covers/cover-open-track.jpg',
  '/images/covers/cover-campus-48h.jpg',
  '/images/covers/cover-quantum.jpg',
];

export function eventCover(event: Pick<EventRecord, 'slug'> & { cover_image_url?: string | null }): string {
  if (event.cover_image_url) return event.cover_image_url;
  let hash = 0;
  for (const ch of event.slug) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACKS[hash % FALLBACKS.length];
}
