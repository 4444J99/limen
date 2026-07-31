/** The film as declared data — read, validated, and sampled at t.
 *
 * The 2017 score partitions the FRAME: no gaps, no overlaps, every tile inside
 * the bounds. A program partitions TIME by exactly the same rule, and for exactly
 * the same reason — a hole in the partition is a hole in the film, and the offline
 * renderer would render it as one without complaining. `scripts/check-danse.py`
 * checks both with the same arithmetic.
 *
 * Every animated channel is declared as `[from, to]` and interpolated across its
 * movement by `ease`. That split is the whole point: the PROGRAM carries the
 * dramaturgy and the SEED carries the material, so `seed 0x3F2A1C` and
 * `seed 0x9B4E07` are recognisably the same film built from different photographs
 * along different paths. It is what makes the fixed cut's final frame honest.
 *
 * Nothing here holds state. A program is a value, passed to `state(seed, t, program)`.
 */

/** Channels a movement interpolates. Every one is `[from, to]`; a movement that
 *  omits one holds it at zero, which is the flat, on-axis, untreated state. */
export const CHANNELS = ["divergence", "spread", "azimuth", "elevation", "projK", "turnover"];

/** Cuts a movement may name. `black` renders nothing — it exists so the closing
 *  signature is part of the declared partition rather than a special case bolted
 *  onto the end of the renderer. */
export const CUTS = ["solo", "score", "grid", "bands", "figure", "black"];

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

export const EASE = {
  linear: (x) => x,
  smooth: (x) => x * x * (3 - 2 * x),
  in: (x) => x * x,
  out: (x) => 1 - (1 - x) * (1 - x),
};

export async function load(url = "render/program.json") {
  const program = await fetch(url).then((r) => {
    if (!r.ok) throw new Error(`program ${r.status} at ${url}`);
    return r.json();
  });
  validate(program);
  return program;
}

/** Throws on anything that would render silently wrong. Called by `load`, by the
 *  offline renderer before it spends twenty minutes, and by the predicate. */
export function validate(program) {
  const bad = (msg) => {
    throw new Error(`program: ${msg}`);
  };
  if (program.schema !== "danse.program.v1") bad(`unknown schema ${program.schema}`);
  const moves = program.movements;
  if (!Array.isArray(moves) || !moves.length) bad("no movements");

  // The partition. Movements must tile [0, duration) end to end — the same
  // no-gaps/no-overlaps rule the score obeys over the picture plane.
  let cursor = 0;
  for (const m of moves) {
    if (m.t0 !== cursor) bad(`${m.id} starts at ${m.t0}, expected ${cursor} — gap or overlap`);
    if (!(m.t1 > m.t0)) bad(`${m.id} has non-positive duration`);
    if (!CUTS.includes(m.cut)) bad(`${m.id} names unknown cut ${m.cut}`);
    if (!(m.ease in EASE)) bad(`${m.id} names unknown ease ${m.ease}`);
    for (const c of CHANNELS) {
      if (m[c] === undefined) continue;
      if (!Array.isArray(m[c]) || m[c].length !== 2) bad(`${m.id}.${c} must be [from, to]`);
    }
    for (const r of m.reseeds ?? []) {
      if (r < 0 || r >= 1) bad(`${m.id} reseed ${r} outside [0, 1)`);
    }
    cursor = m.t1;
  }
  if (cursor !== program.duration) bad(`movements end at ${cursor}, duration is ${program.duration}`);

  for (const [name, w] of Object.entries(program.windows ?? {})) {
    if (name === "_doc") continue;
    if (w.t0 < 0 || w.t1 > program.duration) bad(`window ${name} runs outside the program`);
    if (!(w.t1 > w.t0)) bad(`window ${name} is empty`);
  }
  return program;
}

/** The movement covering t, and how far into it we are.
 *
 * Clamps rather than returning null: an offline renderer asking for the frame at
 * exactly `duration` must get the last frame, not a crash on the final tick.
 */
export function movementAt(program, t) {
  const moves = program.movements;
  for (let i = 0; i < moves.length; i++) {
    const m = moves[i];
    if (t < m.t1 || i === moves.length - 1) {
      const u = clamp01((t - m.t0) / (m.t1 - m.t0));
      return { movement: m, index: i, u };
    }
  }
  return { movement: moves[0], index: 0, u: 0 };
}

/** One channel of a movement at local progress u, already eased. */
export function channel(movement, name, u) {
  const span = movement[name];
  if (!span) return 0;
  const e = EASE[movement.ease](u);
  return span[0] + (span[1] - span[0]) * e;
}

/** Which reseed epoch we are in. 0 until the first declared reseed passes, so a
 *  movement with no reseeds always reports 0 and leaves the material alone. */
export function epochAt(movement, u) {
  let epoch = 0;
  for (const r of movement.reseeds ?? []) {
    if (u >= r) epoch++;
  }
  return epoch;
}

/** A named delivery window, with its format. `master` is the film itself. */
export function windowOf(program, name = "master") {
  const w = program.windows?.[name];
  if (!w) throw new Error(`program: no window "${name}"`);
  return { name, ...w };
}
