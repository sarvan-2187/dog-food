import type { Config } from 'tailwindcss';
import {
  borderRadius,
  boxShadow,
  colors,
  fontFamily,
  fontSize,
  screens,
  spacing,
  transitionDuration,
  transitionTimingFunction,
} from './src/styles/tokens';

// tokens.ts marks its exports `as const` (readonly) so other consumers get
// literal types; Tailwind's Config wants mutable arrays, so unfreeze here at
// the one place that crosses the boundary rather than losing `as const`
// upstream. Object.fromEntries alone widens the tuples into a union array,
// so the result is annotated explicitly against Tailwind's expected shape.
type FontSizeValue = [string, Partial<{ lineHeight: string; letterSpacing: string; fontWeight: string }>];
const mutableFontSize: Record<string, FontSizeValue> = Object.fromEntries(
  Object.entries(fontSize).map(([key, [size, opts]]): [string, FontSizeValue] => [key, [size, { ...opts }]]),
);

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    screens,
    extend: {
      colors,
      fontFamily: {
        sans: [...fontFamily.sans],
        serif: [...fontFamily.serifAccent],
        mono: [...fontFamily.mono],
      },
      fontSize: mutableFontSize,
      borderRadius,
      boxShadow,
      spacing,
      transitionDuration,
      transitionTimingFunction,
    },
  },
  plugins: [],
} satisfies Config;
