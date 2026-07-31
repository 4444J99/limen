/** Where the piece is at time t. Pure, seeded, and with no memory.
 *
 * Everything the renderer needs for a frame is `state(seed, t)`. Nothing
 * accumulates, so seeking to 4:31 costs the same as seeking to 0:01, an offline
 * renderer and a browser tab agree exactly, and two projectors driven from the
 * same seed stay in lock without talking to each other.
 *
 * The dramaturgy comes out of the probe's third result — that the flattening is
 * the CAMERA, not the arrangement. Stand where the camera stood on 20 June 2017
 * and the picture collapses back into the 2017 composite no matter how far the
 * planes have swung apart. So `divergence` is the whole reveal, and it is built
 * to RETURN to zero rather than to rise once:
 *
 *   divergence  0 ─╮      ╭──────╮      ╭─  the still is not a beginning, it is
 *                  ╰──────╯      ╰──────╯   a recurring event in the animation
 *
 * At every trough the room folds back into the photograph he made. The piece
 * keeps arriving at its own origin and leaving again.
 */

import { range } from "./rng.js";

/** Seconds for one full departure-and-return. Long enough that the return reads
 *  as recognition rather than as a pulse. */
export const PERIOD = 74;

/** How long a plane holds one photograph before crossing to the next. Prime
 *  against PERIOD so the two cycles never phase-lock into a visible pattern. */
export const HOLD = 11;

/** Fraction of HOLD spent cross-fading. The dissolve is not a transition effect —
 *  it is the same two-layer compositing the 2017 piece already needed for its 77
 *  translucent tiles, run over time instead of over the picture plane. */
export const CROSSFADE = 0.34;

const TAU = Math.PI * 2;

/** Smooth, monotone 0→1. Used for the reveal so it eases out of and back into
 *  the flat state rather than arriving at it with a velocity. */
const smooth = (x) => x * x * (3 - 2 * x);

/** A trough-and-crest that spends real time at 0. `rest` is the fraction of the
 *  cycle held flat, which is what makes the 2017 composite legible as an image
 *  rather than as a moment passed through. */
function dwell(phase, rest = 0.16) {
  const p = phase - Math.floor(phase);
  if (p < rest / 2 || p > 1 - rest / 2) return 0;
  const t = (p - rest / 2) / (1 - rest);
  return smooth(Math.sin(t * Math.PI)); // 0 → 1 → 0
}

/** The state of the piece at (seed, t). Everything downstream reads this. */
export function state(seed, t) {
  const phase = t / PERIOD;
  const reveal = dwell(phase);

  // Azimuth and elevation drift on their own slow, seed-dependent periods, so
  // successive departures leave in different directions and no two returns are
  // approached from the same side.
  const aPeriod = range(0.31, 0.53, seed, 101);
  const ePeriod = range(0.17, 0.29, seed, 102);
  const aPhase = range(0, 1, seed, 103);
  const ePhase = range(0, 1, seed, 104);

  return {
    t,
    reveal,
    // The camera leaves the projector's eye. This alone un-flattens the picture.
    divergence: reveal * range(0.55, 0.95, seed, 105),
    azimuth: Math.sin((phase * aPeriod + aPhase) * TAU) * 0.85,
    elevation: Math.sin((phase * ePeriod + ePhase) * TAU) * 0.34,
    // Geometry departs slightly AHEAD of the camera, so the arrangement is
    // already built by the time the move begins to disclose it — invisible while
    // on-axis, which is exactly what the probe proved is possible.
    spread: dwell(phase + 0.045),
    // 0 = every plane is a window onto the room. Held there: `projK = 1` makes
    // each plane carry its own crop, which duplicates the poster row. That is a
    // real state of the piece, but it is a departure from the room, not the room.
    projK: 0,
  };
}

/** Which photograph a cell is showing at time t, and what it is crossing to.
 *
 * Each cell gets its own phase offset from its id, so the corpus turns over
 * continuously across the picture rather than all at once — the room is always
 * partly changing and never entirely.
 */
export function turnover(id, seed, t) {
  const offset = range(0, 1, seed, id, 201);
  const p = t / HOLD + offset;
  const epoch = Math.floor(p);
  const frac = p - epoch;

  if (frac < 1 - CROSSFADE) return { epoch, next: epoch + 1, mix: 0 };
  return { epoch, next: epoch + 1, mix: smooth((frac - (1 - CROSSFADE)) / CROSSFADE) };
}
