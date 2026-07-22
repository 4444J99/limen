# Progress source registrations

This directory is the tracked discovery root for work-universe source owners.
Each `*.json` file registers one owner report using the
`limen.progress-source-registration.v1` contract documented in
`docs/progress-source-registry.md`.

An empty directory is explicit unknown coverage debt. Add registrations only
with the source owner's durable receipt and executable predicate; never add a
placeholder that claims zero leaves.

