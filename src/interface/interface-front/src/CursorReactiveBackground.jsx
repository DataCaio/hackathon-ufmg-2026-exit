import { useEffect, useRef } from 'react';

const MAX_TILT_DEG = 8.5;
const PARALLAX_PX = 18;
const LERP = 0.08;

export function CursorReactiveBackground() {
  const rootRef = useRef(null);
  const stageRef = useRef(null);
  const targetRef = useRef({ x: 0, y: 0 });
  const currentRef = useRef({ x: 0, y: 0 });
  const lookTargetRef = useRef({ x: 0.5, y: 0.5 });
  const lookCurrentRef = useRef({ x: 0.5, y: 0.5 });
  const rafRef = useRef(0);

  useEffect(() => {
    const root = rootRef.current;
    const stage = stageRef.current;
    if (!root || !stage) return;

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (motionQuery.matches) {
      stage.style.transform = 'perspective(1400px) rotateX(0deg) rotateY(0deg) translate3d(0, 0, 0)';
      return undefined;
    }

    const onMove = (e) => {
      const cx = window.innerWidth * 0.5;
      const cy = window.innerHeight * 0.5;
      targetRef.current.x = Math.max(-1, Math.min(1, (e.clientX - cx) / cx));
      targetRef.current.y = Math.max(-1, Math.min(1, (e.clientY - cy) / cy));
      lookTargetRef.current.x = e.clientX / window.innerWidth;
      lookTargetRef.current.y = e.clientY / window.innerHeight;
    };

    const tick = () => {
      const t = targetRef.current;
      const c = currentRef.current;
      c.x += (t.x - c.x) * LERP;
      c.y += (t.y - c.y) * LERP;

      const lt = lookTargetRef.current;
      const lk = lookCurrentRef.current;
      lk.x += (lt.x - lk.x) * LERP;
      lk.y += (lt.y - lk.y) * LERP;

      const rx = -c.y * MAX_TILT_DEG;
      const ry = c.x * MAX_TILT_DEG;
      const tx = c.x * PARALLAX_PX;
      const ty = c.y * PARALLAX_PX;

      stage.style.transform = `perspective(1400px) rotateX(${rx}deg) rotateY(${ry}deg) translate3d(${tx}px, ${ty}px, 0)`;

      const shiftX = `${(lk.x - 0.5) * 28}px`;
      const shiftY = `${(lk.y - 0.5) * 28}px`;
      root.style.setProperty('--spot-x', `${lk.x * 100}%`);
      root.style.setProperty('--spot-y', `${lk.y * 100}%`);
      root.style.setProperty('--parallax-shift-x', shiftX);
      root.style.setProperty('--parallax-shift-y', shiftY);
      root.style.setProperty('--subtilt-x', String(-c.y * 3.2));
      root.style.setProperty('--subtilt-y', String(c.x * 3.2));

      rafRef.current = requestAnimationFrame(tick);
    };

    window.addEventListener('mousemove', onMove, { passive: true });
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener('mousemove', onMove);
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <div ref={rootRef} className="cursor-bg-3d" aria-hidden>
      <div className="cursor-bg-3d-spotlight" />
      <div ref={stageRef} className="cursor-bg-3d-stage">
        <div className="cursor-bg-3d-plane cursor-bg-3d-plane-deep" />
        <div className="cursor-bg-3d-plane cursor-bg-3d-plane-grid" />
        <div className="cursor-bg-3d-plane cursor-bg-3d-plane-glow" />
      </div>
    </div>
  );
}
