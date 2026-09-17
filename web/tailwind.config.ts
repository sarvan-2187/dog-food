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

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    screens,
    extend: {
      colors,
      fontFamily: {
        sans: fontFamily.sans,
        serif: fontFamily.serifAccent,
        mono: fontFamily.mono,
      },
      fontSize,
      borderRadius,
      boxShadow,
      spacing,
      transitionDuration,
      transitionTimingFunction,
    },
  },
  plugins: [],
} satisfies Config;
