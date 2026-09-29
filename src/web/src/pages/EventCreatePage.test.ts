import { describe, expect, it } from 'vitest';
import { slugify } from './EventCreatePage';

describe('slugify', () => {
  it('makes a URL-safe slug the API accepts', () => {
    expect(slugify('HackFlow Hackathon 2026!')).toBe('hackflow-hackathon-2026');
    expect(slugify('  Café   Crème -- Jam  ')).toBe('cafe-creme-jam');
    expect(slugify('!!!')).toBe('');
    expect(slugify('AI/ML & Data: Round #2')).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
  });
});
