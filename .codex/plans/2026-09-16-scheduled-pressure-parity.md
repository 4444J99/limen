# Scheduled pressure probe parity

Owner: Limen #2664. PR #2665 updated the observer command but missed the separate
scheduled-process contract. The 16:38:34 scheduled receipt at source 6440c9f
still reported the legacy finding; invoking the new mode with that installed
runtime interpreter returned current measurement successfully.

Add --on-demand to the scheduled command and bind command arguments and timeout
to the observer in a regression test. Preserve scheduling and read-only bounds.
Use the verified signed GitHub API route for publication to avoid another local
signer/SSH prompt. Verify exact content/tree, signature and normal PR integration.
Source acceptance and actual scheduled runtime acceptance remain separate.
