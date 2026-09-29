/**
 * Design tokens - the single source of truth, transcribed from DESIGN_SYSTEM.md.
 * tailwind.config.ts consumes this file; nothing else in the app hardcodes a hex.
 *
 * Palette rebuilt in Phase 5 from a live self-check of raptors.dev's actual
 * DOM (computed styles, not the poster artwork): the real UI chrome is
 * genuinely monochrome (ink-on-cream) — there is no separate saturated brand
 * hue anywhere in its :root custom properties or its buttons/badges. `brand`
 * below is therefore the ink scale itself, used for the primary action —
 * an honest reflection of the reference, not an invented accent color.
 */
export const colors = {
  brand: {
    25: '#F8F9F9',
    50: '#F1F2F2',
    100: '#E7E9E9',
    500: '#1F2426',
    600: '#171B1C',
    700: '#0E1112',
  },
  ink: {
    400: '#8C9294',
    500: '#6F7678',
    600: '#565D5F',
    700: '#3C4344',
    800: '#282D2E',
    900: '#1F2426',
  },
  surface: {
    0: '#FFFFFF',
    50: '#FCFCFC',
    100: '#F1F2F2',
    200: '#F8F9F9',
  },
  navy: {
    800: '#1F2426',
    900: '#12181A',
  },
  border: {
    subtle: '#EAEBEB',
    DEFAULT: '#DEE0E0',
    strong: '#C9CCCC',
  },
  danger: { bg: '#FBEDEC', fg: '#B3271E', solid: '#B3271E', hover: '#93211A', active: '#761A14' },
  warning: { bg: '#FBF2E4', fg: '#9C5B0E' },
  success: { bg: '#EAF3EC', fg: '#2F6B45' },
  info: { bg: '#EBEEEE', fg: '#33393A' },
} as const;

// Sourced from a live self-check of raptors.dev's actual stylesheet (Phase 5):
// its :root declares --sans: "Satoshi Variable" and --serif: "Playfair Display".
// Both are self-hosted under public/fonts/ (PLAN.md section 1 forbids CDN
// requests in the served app) — never add a <link> to fonts.googleapis.com or
// fonts.fontshare.com.
export const fontFamily = {
  sans: ['Satoshi', '-apple-system', 'Segoe UI', 'system-ui', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
  serifAccent: ['Playfair Display', 'Georgia', 'Times New Roman', 'serif'],
  mono: ['Consolas', 'SF Mono', 'ui-monospace', 'monospace'],
} as const;

/**
 * [size, { lineHeight, letterSpacing, fontWeight }] - Tailwind fontSize tuples.
 * display/h2/h3/body-lg are the real measured values from raptors.dev's live
 * DOM (h1 70px/500, h2 40px/500/lh50/-1.2px, h3 24px/500/lh34/-0.72px,
 * p 18px/400/lh30); label/meta/eyebrow are interpolated at the same
 * tight-tracking, weight-500-headings/700-labels convention since the
 * reference has no data-dense UI to sample those from directly. Satoshi was
 * only sourced as static 400/500/700 instances (not the full variable axis),
 * so "weight 600" treatments below use 700, the closest available.
 */
export const fontSize = {
  // Real: 70px/500, marketing hero only.
  display: ['clamp(2.5rem, 6vw, 4.375rem)', { lineHeight: '1.05', letterSpacing: '-0.03em', fontWeight: '500' }],
  // Real: this is the reference's own H2 (40px/500/lh50/-1.2px) — our in-app
  // page-title role matches their section-heading role, since their H1 is
  // used exactly once, in the hero (that's "display" above).
  h1: ['2.5rem', { lineHeight: '1.25', letterSpacing: '-0.03em', fontWeight: '500' }],
  // Interpolated: not directly measured, sits between h1(40px) and h3(24px).
  h2: ['1.75rem', { lineHeight: '1.3', letterSpacing: '-0.03em', fontWeight: '500' }],
  // Real: 24px/500/lh34/-0.72px.
  h3: ['1.5rem', { lineHeight: '1.42', letterSpacing: '-0.03em', fontWeight: '500' }],
  'body-lg': ['1.125rem', { lineHeight: '1.67' }],
  // Not measured directly on the reference (a marketing site with no dense
  // table/form UI to sample) — kept smaller than body-lg so tables and forms
  // stay compact, same density convention as before this rebuild.
  body: ['0.9375rem', { lineHeight: '1.6' }],
  label: ['0.875rem', { lineHeight: '1.4', fontWeight: '700', letterSpacing: '0.03em' }],
  meta: ['0.75rem', { lineHeight: '1.4' }],
  eyebrow: ['0.6875rem', { lineHeight: '1.2', letterSpacing: '0.03em', fontWeight: '700' }],
} as const;

// Real measurements: button 10px radius, badge 50px (a true pill).
export const borderRadius = {
  sm: '6px',
  md: '10px',
  lg: '14px',
  xl: '18px',
  full: '999px',
} as const;

export const boxShadow = {
  sm: '0 1px 2px rgba(31, 36, 38, 0.05)',
  md: '0 4px 16px rgba(31, 36, 38, 0.06)',
  lg: '0 16px 48px rgba(31, 36, 38, 0.10)',
} as const;

export const spacing = {
  card: '24px',
  'card-sm': '16px',
  stack: '12px',
  group: '24px',
  section: '64px',
  hero: '96px',
} as const;

export const screens = {
  sm: '375px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
} as const;

export const transitionDuration = {
  fast: '120ms',
  base: '200ms',
  slow: '320ms',
} as const;

export const transitionTimingFunction = {
  standard: 'cubic-bezier(0.2, 0, 0.2, 1)',
} as const;
