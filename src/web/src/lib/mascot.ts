import { useEffect, useState } from 'react';

/**
 * The landing page's HackFlow wordmark slides into the pill nav as you scroll.
 * Every piece of that handoff - the flying copy, the pill's berth opening up,
 * the pill's own static copy fading in - keys off this one point, so they stay
 * in step instead of finishing at slightly different scroll positions.
 */
export function wordmarkHandoffPoint(): number {
  if (typeof window === 'undefined') return 420;
  return Math.min(window.innerHeight * 0.55, 520);
}

export function useWordmarkHandedOff(active: boolean): boolean {
  const [handedOff, setHandedOff] = useState(true);

  useEffect(() => {
    if (!active) {
      setHandedOff(true);
      return;
    }
    const update = () => setHandedOff(window.scrollY >= wordmarkHandoffPoint());
    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [active]);

  return handedOff;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
