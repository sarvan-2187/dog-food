import { useEffect, useState } from 'react';

/**
 * The landing page's raptor runs up the page and "lands" in the nav as you
 * scroll. Both halves of that handoff - the running mascot and the nav's own
 * mark - key off this one point so they swap on the same pixel instead of
 * overlapping or both vanishing for a frame.
 */
export function raptorHandoffPoint(): number {
  if (typeof window === 'undefined') return 420;
  return Math.min(window.innerHeight * 0.55, 520);
}

export function useRaptorHandedOff(active: boolean): boolean {
  const [handedOff, setHandedOff] = useState(true);

  useEffect(() => {
    if (!active) {
      setHandedOff(true);
      return;
    }
    const update = () => setHandedOff(window.scrollY >= raptorHandoffPoint());
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
