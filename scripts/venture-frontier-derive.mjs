#!/usr/bin/env node
// venture-frontier-derive — derive each phase's TRUE blocking class from the nodes underneath it,
// then compare against the declared phase.status label.
//
// Provenance: this is the prototype that found the 2026-08-15 scope defect
// (docs/plans/2026-08-15-venture-ladder-derived-frontier-heal.md). It lands here so the evidence
// is reproducible; T1 of that plan ports this logic into the vendored engine as check K, after
// which THIS FILE SHOULD BE DELETED — the engine is the canonical surface, not scripts/.
//
// Truth model (all of it already present in each ladder):
//   lever-blocked  : phase.gate set, or any epic/leaf carries blocked_on: <lever>
//   dep-blocked    : some epic/leaf depends_on a node that is not done
//   buildable-now  : neither — every real prerequisite is built and no human lever applies
//
// phase.depends_on is DELIBERATELY IGNORED: it is a version-ordering declaration, not a work
// dependency. Conflating the two is the bug this exists to catch.
//
// Exit 0 if every declared label matches its derived class; exit 1 on any mismatch.
// Usage: node scripts/venture-frontier-derive.mjs [workspace-root]

import { readFileSync } from 'node:fs'

const ROOT = process.argv[2] ?? '/Users/4jp/Workspace'
const REPOS = ['post-dsp-platform', 'the-consulate', 'new-ancients-social']
const load = (r, f) => JSON.parse(readFileSync(`${ROOT}/${r}/roadmap/${f}`, 'utf8'))

let mismatches = 0

for (const repo of REPOS) {
  const ladder = load(repo, 'ladder.json')

  const statusOf = new Map()
  for (const ph of ladder.phases) {
    for (const ep of ph.epics ?? []) {
      statusOf.set(ep.id, ep.status)
      for (const lf of ep.leaves ?? []) statusOf.set(lf.id, lf.status)
    }
  }
  const phaseStatus = new Map(ladder.phases.map((p) => [p.id, p.status]))
  const doneNode = (id) => statusOf.get(id) === 'done' || phaseStatus.get(id) === 'done'

  console.log(`\n${'='.repeat(76)}\n${repo}\n${'='.repeat(76)}`)

  for (const ph of ladder.phases) {
    if (ph.status === 'done') continue

    const levers = new Set()
    if (ph.gate) levers.add(`${ph.gate} (phase.gate)`)
    const unmet = []
    let nodeCount = 0

    for (const ep of ph.epics ?? []) {
      nodeCount++
      if (ep.blocked_on) levers.add(`${ep.blocked_on} (${ep.id})`)
      for (const d of ep.depends_on ?? []) {
        if (!doneNode(d)) unmet.push([ep.id, d])
      }
      for (const lf of ep.leaves ?? []) {
        nodeCount++
        if (lf.blocked_on) levers.add(`${lf.blocked_on} (${lf.id})`)
        for (const d of lf.depends_on ?? []) {
          if (!doneNode(d)) unmet.push([lf.id, d])
        }
      }
    }

    // a dep only blocks the PHASE if it points outside the phase; intra-phase deps are ordering
    const external = unmet.filter(([, target]) => !target.startsWith(ph.id))

    const derived = levers.size ? 'LEVER-BLOCKED' : external.length ? 'DEP-BLOCKED' : 'BUILDABLE-NOW'
    const agree =
      (derived === 'LEVER-BLOCKED' && ph.status === 'GATED') ||
      (derived === 'DEP-BLOCKED' && ph.status === 'gate-dependent') ||
      (derived === 'BUILDABLE-NOW' && ph.status === 'buildable')
    if (!agree) mismatches++

    console.log(`\n${ph.id}  v${ph.version}  "${ph.title}"`)
    console.log(`   declared: ${ph.status.padEnd(15)} derived: ${derived}   ${agree ? 'AGREE' : '*** MISMATCH ***'}`)
    console.log(`   phase.depends_on: ${JSON.stringify(ph.depends_on ?? [])}   (ordering only — not a work dep)`)
    console.log(`   nodes: ${nodeCount}`)
    for (const l of levers) console.log(`     lever  ${l}`)
    for (const [from, to] of external.slice(0, 8)) {
      console.log(`     unmet  ${from} -> ${to} [${statusOf.get(to) ?? phaseStatus.get(to) ?? '?'}]`)
    }
    if (!levers.size && !external.length) console.log(`     -> nothing blocks this. every prerequisite is built.`)
  }
}

console.log(`\n${mismatches} declared/derived mismatch(es)\n`)
process.exit(mismatches ? 1 : 0)
