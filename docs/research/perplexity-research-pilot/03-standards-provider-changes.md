# Perplexity pilot run 3 — rejected before submission

## Terminal disposition

This run is `rejected`. The attended browser bridge exposed no controllable
Chrome session, so the request was not submitted and no Perplexity result was
produced.

## Failed predicate

The attended `pro_research` lane must expose a controllable private browser
session before any prompt is submitted. The documented bridge bootstrap
requires explicit operator approval to open one fresh Chrome window; that
approval was not available during this bounded run.

This is a control-plane capability failure. It does not claim that the
Perplexity subscription, authentication, or Research surface is unavailable.

## Evidence and custody

- Provider requests submitted: 0
- Variable spend: USD 0
- Computer, API, connectors, scheduling, sharing, and billing mutations: none
- Raw Markdown export: not produced or retained
- Provider and model: not observed
- Source-verifier and output-sanitization attestations: not created because no
  export existed; inventing an export hash would be false evidence

## Resume action

After explicit operator approval, open one fresh Chrome window for the active
profile, retry the bridge once, and create a new research run. Do not reopen
this terminal receipt.
