/** One step of the piece. The live page and the film both come through here.
 *
 * This module exists so there is exactly one answer to "what is on screen at
 * (seed, t)". A browser tab at 60fps, an offline renderer walking 23,400 frames
 * out of order across two processes, and a still exported for Instagram all call
 * `step` and all get the same frame — because `step` is a pure function and the
 * clock underneath it has no memory.
 *
 * The only thing the live page does differently is `quantise`, and that is a
 * parameter rather than a fork: casting cells walks 162 index entries per cell,
 * which at 60fps is work nobody can see. Geometry and camera still move every
 * frame; only the CHOICE is held. The film passes 0 and pays for exactness.
 */

import { state } from "./clock.js";
import { cells } from "./grammar.js";

/** What is on screen at (seed, t). `program` null runs the piece free. */
export function step(corpus, seed, t, program = null, { quantise = 0 } = {}) {
  const s = state(seed, t, program);
  // The state is always sampled at the exact t; only the cast may be held.
  const ct = quantise > 0 ? Math.floor(t / quantise) * quantise : t;
  const cast = cells(corpus, s.material, ct, { reveal: s.reveal, cut: s.cut, rate: s.turnover });
  return { state: s, cast };
}

/** Step and draw. Returns the renderer's stats plus the state that produced them. */
export function frameAt(renderer, corpus, seed, t, program = null, opts = {}) {
  const { quantise = 0, ...draw } = opts;
  const { state: s, cast } = step(corpus, seed, t, program, { quantise });
  return { ...renderer.draw(cast, s, { seed, ...draw }), state: s, cells: cast.length };
}

/** The seed as it appears in the film's last frame, in a post caption, and in a
 *  still's filename. One spelling everywhere, so the number a viewer reads off
 *  the screen is the number that reproduces what they saw. */
export function hex(seed) {
  return `0x${(seed >>> 0).toString(16).toUpperCase().padStart(6, "0")}`;
}

/** Fill a program's signature line with the seed that rendered it. */
export function signature(program, seed) {
  const sig = program?.signature;
  if (!sig) return hex(seed);
  return sig.format.replace("%SEED%", hex(seed).replace(/^0x/, ""));
}
