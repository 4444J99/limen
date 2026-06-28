# Limen Workstream Lanes

These lanes are project/product workstreams, not Limen `target_agent` values.
They let future sessions route work by domain while still using the existing agent
fleet (`codex`, `claude`, `opencode`, `agy`, `gemini`, `jules`, `copilot`,
`warp`, `oz`, or `any`).

When a task belongs to one of these lanes:

- keep `repo` pointed at the real project repo;
- keep `target_agent` in the canonical agent set;
- add the lane handle as a task label;
- name the allowed files, stop condition, and verification command in the task;
- leave a receipt in the lane doc or the project repo before handing off.

Current lane receipts:

- [`rob-game`](rob-game.md) - Micro Tato, the newer personal game with Rob and John F.
