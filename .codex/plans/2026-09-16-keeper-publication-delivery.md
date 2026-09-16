# Keeper publication delivery

Owner: Codex; acceptance owner L-BOARD-PARTITION-DECISION and keeper publication lane.

The existing live canary passed two real status-preserving acceptance amendments against deployment 16fd02e1a72d7ee8d5432d637221938aa94e3cf5 / 4839ca12-ac13-4b48-a215-57b727117243. The keeper recovered its missing publication ref without manual ref writes; consecutive publication commits preserve ancestry. The redacted receipt is docs/receipts/keeper-publication-live-20260916.json. The original amendments had been absent; no previously submitted canary was replayed.

The documented PR adapter then failed shell parsing before PR creation. Its nested command-substitution heredoc is incompatible with the system Bash parser. Write the body directly to a temporary file, preserve Markdown quoting, and use --body-file. Remove the tail pipeline so a failed gh create cannot print success. The trap removes only its own temporary file.

Two isolated executable fixtures verify successful body rendering and failing gh status propagation, temporary-file removal and preservation of caller files. Run python3 scripts/tests/test_publish_board_pr.py, then the implicated scoped batch. No credential/account change, task status transition or manual task projection write is introduced.

Publication branch custody and default-branch landing are separate receipts. After this repair, run the existing adapter once and verify the exact keeper-owned projection head through the board lane before landing.
