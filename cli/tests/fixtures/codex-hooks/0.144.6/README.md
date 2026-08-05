# Codex 0.144.6 hook fixtures

These fixtures retain only the non-sensitive shape needed by host-admission
tests. The field inventory is grounded in the installed
`codex-cli 0.144.6` hook schema and local lifecycle observations. Session and
turn identifiers are one-way placeholders; transcript paths, prompt text, tool
arguments, and user content are not retained.

- `user-prompt-submit-plan.json` records the observed Plan discriminator.
- `user-prompt-submit-default.json` records an ordinary executable turn.
- `user-prompt-submit-bypass-boundary.json` records an unrecognized non-Plan value.

All three must admit session startup without acquiring a global execution lease. Permission mode
does not turn `UserPromptSubmit` into a serialization boundary; mutation is decided at `PreToolUse`.
