/**
 * Design tokens - the single source of truth, transcribed from DESIGN_SYSTEM.md.
 * tailwind.config.ts consumes this file; nothing else in the app hardcodes a hex.
 */
export const colors = {
  brand: {
    25: '#F5FAFF',
    50: '#F2F6FF',
    100: '#ECF2FF',
    500: '#2F6BFF',
    600: '#255DF5',
    700: '#2450CF',
  },
  ink: {
    400: '#8B95A6',
    500: '#7B8DA5',
    600: '#64758D',
    700: '#43516A',
    800: '#17283E',
    900: '#171D29',
  },
  surface: {
    0: '#FFFFFF',
    50: '#FCFCFD',
    100: '#F7F9FC',
    200: '#F4F6FA',
  },
  navy: {
    800: '#1F2B42',
    900: '#071936',
  },
  border: {
    subtle: '#EDF0F5',
    DEFAULT: '#E6EBF2',
    strong: '#DCE3EC',
  },
  danger: { bg: '#FFF1EF', fg: '#B42318', solid: '#B42318', hover: '#98180F', active: '#7F1410' },
  warning: { bg: '#FFF7E8', fg: '#B54708' },
  success: { bg: '#ECF8F2', fg: '#177148' },
  info: { bg: '#ECF2FF', fg: '#2450CF' },
} as const;

export const fontFamily = {
  sans: ['Inter', 'Inter var', '-apple-system', 'Segoe UI', 'system-ui', 'sans-serif'],
  serifAccent: ['Instrument Serif', 'Georgia', 'Times New Roman', 'serif'],
  mono: ['JetBrains Mono', 'Consolas', 'ui-monospace', 'monospace'],
} as const;

/** [size, { lineHeight, letterSpacing, fontWeight }] - Tailwind fontSize tuples. */
export const fontSize = {
  display: ['clamp(2.25rem, 4.5vw, 3.5rem)', { lineHeight: '1.05', letterSpacing: '-0.02em', fontWeight: '700' }],
  h1: ['2.125rem', { lineHeight: '1.15', letterSpacing: '-0.015em', fontWeight: '700' }],
  h2: ['1.75rem', { lineHeight: '1.2', letterSpacing: '-0.01em', fontWeight: '600' }],
  h3: ['1.25rem', { lineHeight: '1.3', fontWeight: '600' }],
  'body-lg': ['1.125rem', { lineHeight: '1.6' }],
  body: ['0.9375rem', { lineHeight: '1.55' }],
  label: ['0.8125rem', { lineHeight: '1.4', fontWeight: '500' }],
  meta: ['0.75rem', { lineHeight: '1.4' }],
  eyebrow: ['0.6875rem', { lineHeight: '1.2', letterSpacing: '0.12em', fontWeight: '600' }],
} as const;

export const borderRadius = {
  sm: '6px',
  md: '8px',
  lg: '12px',
  xl: '16px',
  full: '999px',
} as const;

export const boxShadow = {
  sm: '0 1px 2px rgba(7, 25, 54, 0.05)',
  md: '0 4px 16px rgba(7, 25, 54, 0.06)',
  lg: '0 16px 48px rgba(7, 25, 54, 0.10)',
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
