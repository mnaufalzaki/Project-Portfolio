import { Easing, interpolate, spring } from "remotion";
import { FPS } from "./theme";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_IN = Easing.bezier(0.7, 0, 0.84, 0);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);

/** clamped interpolate */
export const lerp = (
  f: number,
  input: number[],
  output: number[],
  easing?: (t: number) => number,
) => interpolate(f, input, output, { ...clamp, easing });

/** bouncy 0→1 spring with overshoot, starting at `start` */
export const pop = (f: number, start: number, damping = 9, stiffness = 170, mass = 0.8) =>
  spring({ frame: f - start, fps: FPS, config: { damping, stiffness, mass } });

/** soft 0→1 spring, no bounce */
export const glide = (f: number, start: number, damping = 200) =>
  spring({ frame: f - start, fps: FPS, config: { damping } });

/**
 * Squash & stretch for a landing at `land`: returns [scaleX, scaleY].
 * Stretch while falling, squash at impact, wobble back to 1.
 */
export const squash = (f: number, land: number, amount = 0.14) => {
  const d = f - land;
  if (d < -6) return [1 - amount * 0.4, 1 + amount * 0.6];
  if (d < 0) {
    const t = (d + 6) / 6;
    return [1 - amount * 0.4 * (1 - t), 1 + amount * 0.6 * (1 - t)];
  }
  const decay = Math.exp(-d / 5);
  const w = Math.cos((d / 7) * Math.PI);
  const s = amount * decay * w;
  return [1 + s, 1 - s];
};

/** hop: 0 at start, rises to 1 at mid, back to 0 at end (parabola) */
export const hop = (f: number, start: number, dur: number) => {
  const t = (f - start) / dur;
  if (t <= 0 || t >= 1) return 0;
  return 4 * t * (1 - t);
};
