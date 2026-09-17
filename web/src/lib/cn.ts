import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Join conditional class names, resolving Tailwind class conflicts. */
export function cn(...parts: ClassValue[]): string {
  return twMerge(clsx(...parts));
}
