import { motion, useScroll, useSpring, useTransform } from 'framer-motion';
import { useEffect, useState } from 'react';
import { prefersReducedMotion, raptorHandoffPoint } from '../lib/mascot';

type Box = { x: number; y: number; w: number };

/**
 * On the landing page the HackFlow wordmark starts out on its own at the top
 * left and slides into the pill nav as you scroll, coming to rest beside the
 * raptor that already lives there.
 *
 * Both ends are real elements - `#wordmark-home-slot` in the header and
 * `#wordmark-nav-slot` inside the pill - so the path stays correct at any
 * breakpoint and whatever the pill's contents happen to be. Both of those
 * slots render the wordmark at full size but invisible: they hold the layout,
 * this component draws the only visible copy and flies it between them. That
 * way nothing reflows at the moment of the handoff - the pill is already wide
 * enough for the wordmark before it arrives.
 *
 * No gait or bob: at the speed scrolling moves it, added motion reads as
 * wobble rather than as travel.
 */
export function WordmarkMerge() {
  const { scrollY } = useScroll();
  const [boxes, setBoxes] = useState<{ from: Box; to: Box } | null>(null);
  const [reduced, setReduced] = useState(prefersReducedMotion);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    const measure = () => {
      const home = document.getElementById('wordmark-home-slot');
      const nav = document.getElementById('wordmark-nav-slot');
      if (!home || !nav) return setBoxes(null);
      const h = home.getBoundingClientRect();
      const n = nav.getBoundingClientRect();
      if (!h.width || !n.width) return setBoxes(null);
      setBoxes({
        // Both are in the sticky header, so both are already viewport-fixed.
        from: { x: h.left, y: h.top, w: h.width },
        to: { x: n.left, y: n.top, w: n.width },
      });
    };
    measure();
    window.addEventListener('resize', measure);
    // Webfonts land after first paint and change the wordmark's width.
    const t = window.setTimeout(measure, 500);
    document.fonts?.ready.then(measure).catch(() => {});
    return () => {
      window.removeEventListener('resize', measure);
      window.clearTimeout(t);
    };
  }, []);

  const end = raptorHandoffPoint();
  const range = [0, end];
  const x = useTransform(scrollY, range, [boxes?.from.x ?? 0, boxes?.to.x ?? 0], { clamp: true });
  const y = useTransform(scrollY, range, [boxes?.from.y ?? 0, boxes?.to.y ?? 0], { clamp: true });
  // Scale rather than animating font-size, so the text never re-lays-out mid-flight.
  const scale = useTransform(scrollY, range, [1, boxes ? boxes.to.w / boxes.from.w : 1], { clamp: true });
  // Ink on the page, white once it is over the dark pill.
  // Flips early: the wordmark crosses the pill's dark edge well before it
  // lands, and ink-on-ink is unreadable for those frames.
  const color = useTransform(scrollY, [end * 0.3, end * 0.55], ['#1F2426', '#F8F9F9']);
  // Hand over to the pill's own (static) copy right at the end.
  const opacity = useTransform(scrollY, [end * 0.94, end], [1, 0], { clamp: true });

  const sx = useSpring(x, { stiffness: 260, damping: 34, mass: 0.5 });
  const sy = useSpring(y, { stiffness: 260, damping: 34, mass: 0.5 });
  const sScale = useSpring(scale, { stiffness: 260, damping: 34, mass: 0.5 });

  if (!boxes || reduced) return null;

  return (
    <motion.span
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-[45] whitespace-nowrap text-h3 tracking-tight will-change-transform"
      style={{ x: sx, y: sy, scale: sScale, originX: 0, originY: 0, color, opacity }}
    >
      Hack<span className="font-serif italic">Flow</span>
    </motion.span>
  );
}
