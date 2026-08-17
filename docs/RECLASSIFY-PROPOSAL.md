# Reclassify needs_human — 2026-07-13

`needs_human` holds **444** tasks. By signal (not by hand-picked id) they split into:

- **KEEP — 58** genuinely need your hand (secret / account / admin / merge gate / irreversible cutover / Cloudflare-credential-gated deploy).
- **FLIP — 316** are fleet-buildable code/docs parked behind a false gate. `--apply` flips these to `open` so the fleet does them. Reversible.
- **STALE — 1** precondition already met — recommend close, don't re-queue.
- **REVIEW — 69** one quick triage call (skip vs *kill* — kill is irreversible, never auto-flipped).

> `--apply` changes ONLY the FLIP bucket; KEEP / STALE / REVIEW are never auto-touched. Flipping `needs_human -> open` only lets the fleet *attempt* the work — fully reversible.

## FLIP — fleet-buildable code/docs — no human-only signal

| id | type | repo | title |
|---|---|---|---|
| `GH-meta-organvm-meta-organvm-superproject-6` | code | organvm/meta-organvm--superproject | Omega #15: Flip — portfolio validation page is LIVE |
| `GH-organvm-ii-poiesis-organvm-ii-poiesis-superproject-2` | code | organvm/organvm-ii-poiesis--superproject | Add README for performance-sdk |
| `GH-organvm-iii-ergon-sign-signal-voice-synth-3` | code | organvm/sign-signal--voice-synth | Implement Layer 1: Dialogue Looping Tracker (60 tasks) |
| `GH-organvm-iv-taxis-organvm-iv-taxis-github-io-1` | code | organvm/organvm-iv-taxis.github.io | EV Activation Audit: ship-now — ORGAN-IV landing page live (HTTP 200) |
| `GH-organvm-v-logos-organvm-v-logos-github-io-1` | code | organvm/organvm-v-logos.github.io | EV Activation Audit: ship-now — org landing page live (HTTP 200) |
| `GH-organvm-vi-koinonia-organvm-vi-koinonia-github-io-1` | code | organvm/organvm-vi-koinonia.github.io | EV Activation Audit: ship-now — org landing page live (HTTP 200) |
| `GH-organvm-vii-kerygma-organvm-vii-kerygma-github-io-1` | code | organvm/organvm-vii-kerygma.github.io | EV Activation Audit: ship-now — org landing page live (HTTP 200) |
| `GH-organvm-vii-kerygma-organvm-vii-kerygma-superproject-5` | code | organvm/organvm-vii-kerygma--superproject | Epic: Kerygma Pipeline Activation (POSSE Distribution) |
| `GH-organvm-vii-kerygma-organvm-vii-kerygma-superproject-2` | code | organvm/organvm-vii-kerygma--superproject | Add missing READMEs for kerygma-pipeline and kerygma-profiles |
| `GH-organvm-i-theoria-atomic-substrata-1` | code | organvm/atomic-substrata | EV Activation Audit: ship-soon — UAKS pipeline operational but unrelea |
| `GEN-meta-organvm-meta-organvm.github.io-test-coverage-0620` | code | organvm/meta-organvm.github.io | Raise test coverage in meta-organvm/meta-organvm.github.io |
| `GEN-meta-organvm-meta-organvm--superproject-test-coverage-0620` | code | organvm/meta-organvm--superproject | Raise test coverage in meta-organvm/meta-organvm--superproject |
| `GEN-organvm-ii-poiesis-organvm-ii-poiesis--superproject-test-coverage-0620` | code | organvm/organvm-ii-poiesis--superproject | Raise test coverage in organvm-ii-poiesis/organvm-ii-poiesis--superpro |
| `GEN-organvm-iii-ergon-sign-signal--voice-synth-test-coverage-0620` | code | organvm/sign-signal--voice-synth | Raise test coverage in organvm-iii-ergon/sign-signal--voice-synth |
| `GEN-a-organvm-my-knowledge-base-ci-green-0620` | code | organvm/my-knowledge-base | Make a-organvm/my-knowledge-base CI green |
| `GEN-a-organvm-the-actual-news-ci-green-0620` | code | organvm/the-actual-news | Make a-organvm/the-actual-news CI green |
| `GEN-organvm-i-theoria-sovereign--ground-ci-green-0620` | code | organvm/sovereign--ground | Make organvm-i-theoria/sovereign--ground CI green |
| `GEN-organvm-fetch-familiar-friends-test-coverage-0620` | code | organvm/fetch-familiar-friends | Raise test coverage in organvm/fetch-familiar-friends |
| `GEN-organvm-enterprise-plugin-test-coverage-0620` | code | organvm/enterprise-plugin | Raise test coverage in organvm/enterprise-plugin |
| `GH-4444j99-hokage-chess-49` | code | organvm/hokage-chess | [V-C] Phase 4 — conductor MCP scope-binding (require client param when |
| `GH-4444j99-hokage-chess-15` | code | organvm/hokage-chess | [AF-4] Update PRT-048 IRF row to reflect DONE-474 (skill exists) |
| `GH-organvm-public-process-22` | code | organvm/public-process | [STRANGER-TEST] Session 10: Security Researcher |
| `GEN-organvm-styx-test-coverage-0624` | code | organvm/styx | Raise test coverage in organvm/styx |
| `GEN-organvm-styx-ci-green-0624` | code | organvm/styx | Make organvm/styx CI green |
| `GEN-organvm-styx-docs-0624` | code | organvm/styx | Real usage docs for organvm/styx |
| `GEN-organvm-styx-security-0624` | code | organvm/styx | Security hardening pass on organvm/styx |
| `GEN-organvm-universal-mail--automation-simplify-0624` | code | organvm/universal-mail--automation | Reduce complexity in organvm/universal-mail--automation |
| `GEN-organvm-styx-simplify-0624` | code | organvm/styx | Reduce complexity in organvm/styx |
| `GEN-organvm-styx-typing-0624` | code | organvm/styx | Tighten types in organvm/styx |
| `GH-organvm-limen-264` | code | organvm/limen | needs-human (L-MODEL-TIER): Stop the interactive Claude burn at the so |
| `GH-organvm-limen-263` | code | organvm/limen | needs-human (L-IANVA-CLOUD): Stop the claude.ai connector 'needs authe |
| `GH-organvm-limen-262` | code | organvm/limen | needs-human (L-IANVA-LOCAL): Kill the per-agent MCP re-auth for every  |
| `GH-organvm-limen-260` | code | organvm/limen | needs-human (L-EDU-PERTERM): The per-term recapitulation ritual is aut |
| `GH-organvm-limen-259` | code | organvm/limen | needs-human (L-ENC1102-GRADEBOOK): Resolve the ENC1102 D2L gradebook w |
| `GH-organvm-limen-258` | code | organvm/limen | needs-human (L-ENC1101-GOLIVE): Take ENC1101 Summer 2026 (771624) live |
| `GH-organvm-limen-257` | code | organvm/limen | needs-human (L-BRANCH-PROTECT-072): Branch-protection across the organ |
| `GEN-organvm-public-record-data-scrapper-test-coverage-0626` | code | organvm/public-record-data-scrapper | Raise test coverage in organvm/public-record-data-scrapper |
| `GEN-organvm-portfolio-security-0626` | code | organvm/portfolio | Security hardening pass on organvm/portfolio |
| `GEN-organvm-a-i-chat--exporter-security-0626` | code | organvm/a-i-chat--exporter | Security hardening pass on organvm/a-i-chat--exporter |
| `GEN-organvm-a-i-chat--exporter-typing-0626` | code | organvm/a-i-chat--exporter | Tighten types in organvm/a-i-chat--exporter |
| `GEN-organvm-public-record-data-scrapper-typing-0626` | code | organvm/public-record-data-scrapper | Tighten types in organvm/public-record-data-scrapper |
| `GEN-organvm-universal-mail--automation-security-0627` | code | organvm/universal-mail--automation | Security hardening pass on organvm/universal-mail--automation |
| `GEN-organvm-limen-security-0627` | code | organvm/limen | Security hardening pass on organvm/limen |
| `GEN-organvm-portfolio-simplify-0627` | code | organvm/portfolio | Reduce complexity in organvm/portfolio |
| `GEN-organvm-a-i-chat--exporter-simplify-0627` | code | organvm/a-i-chat--exporter | Reduce complexity in organvm/a-i-chat--exporter |
| `GEN-organvm-the-invisible-ledger-simplify-0627` | code | organvm/the-invisible-ledger | Reduce complexity in organvm/the-invisible-ledger |
| `GEN-organvm-the-invisible-ledger-docs-0627` | code | organvm/the-invisible-ledger | Real usage docs for organvm/the-invisible-ledger |
| `GEN-organvm-portfolio-docs-0627` | code | organvm/portfolio | Real usage docs for organvm/portfolio |
| `GEN-organvm-public-record-data-scrapper-docs-0627` | code | organvm/public-record-data-scrapper | Real usage docs for organvm/public-record-data-scrapper |
| `GEN-organvm-domus-genoma-typing-0627` | code | organvm/domus-genoma | Tighten types in organvm/domus-genoma |
| `GEN-organvm-mirror-mirror-typing-0627` | code | organvm/mirror-mirror | Tighten types in organvm/mirror-mirror |
| `GEN-organvm-the-invisible-ledger-typing-0627` | code | organvm/the-invisible-ledger | Tighten types in organvm/the-invisible-ledger |
| `GEN-organvm-mirror-mirror-test-coverage-0628` | code | organvm/mirror-mirror | Raise test coverage in organvm/mirror-mirror |
| `GEN-organvm-universal-mail--automation-test-coverage-0628` | code | organvm/universal-mail--automation | Raise test coverage in organvm/universal-mail--automation |
| `GEN-organvm-a-i-chat--exporter-test-coverage-0628` | code | organvm/a-i-chat--exporter | Raise test coverage in organvm/a-i-chat--exporter |
| `GEN-organvm-the-invisible-ledger-test-coverage-0628` | code | organvm/the-invisible-ledger | Raise test coverage in organvm/the-invisible-ledger |
| `GEN-organvm-domus-genoma-ci-green-0628` | code | organvm/domus-genoma | Make organvm/domus-genoma CI green |
| `GEN-organvm-session-meta-ci-green-0628` | code | organvm/session-meta | Make organvm/session-meta CI green |
| `GEN-organvm-a-i-chat--exporter-ci-green-0628` | code | organvm/a-i-chat--exporter | Make organvm/a-i-chat--exporter CI green |
| `GEN-organvm-public-record-data-scrapper-ci-green-0628` | code | organvm/public-record-data-scrapper | Make organvm/public-record-data-scrapper CI green |
| `GEN-organvm-the-invisible-ledger-security-0628` | code | organvm/the-invisible-ledger | Security hardening pass on organvm/the-invisible-ledger |
| `GEN-organvm-limen-simplify-0628` | code | organvm/limen | Reduce complexity in organvm/limen |
| `GEN-organvm-portfolio-typing-0628` | code | organvm/portfolio | Tighten types in organvm/portfolio |
| `GEN-organvm-domus-genoma-docs-0628` | code | organvm/domus-genoma | Real usage docs for organvm/domus-genoma |
| `GEN-organvm-public-record-data-scrapper-simplify-0628` | code | organvm/public-record-data-scrapper | Reduce complexity in organvm/public-record-data-scrapper |
| `GEN-organvm-universal-mail--automation-docs-0629` | code | organvm/universal-mail--automation | Real usage docs for organvm/universal-mail--automation |
| `GEN-organvm-portfolio-test-coverage-0630` | code | organvm/portfolio | Raise test coverage in organvm/portfolio |
| `GEN-organvm-the-invisible-ledger-ci-green-0630` | code | organvm/the-invisible-ledger | Make organvm/the-invisible-ledger CI green |
| `GEN-organvm-limen-docs-0630` | code | organvm/limen | Real usage docs for organvm/limen |
| `GEN-organvm-domus-genoma-simplify-0630` | code | organvm/domus-genoma | Reduce complexity in organvm/domus-genoma |
| `GEN-organvm-session-meta-security-0701` | code | organvm/session-meta | Security hardening pass on organvm/session-meta |
| `GEN-organvm-domus-genoma-security-0701` | code | organvm/domus-genoma | Security hardening pass on organvm/domus-genoma |
| `GEN-organvm-mirror-mirror-security-0701` | code | organvm/mirror-mirror | Security hardening pass on organvm/mirror-mirror |
| `GEN-organvm-public-record-data-scrapper-security-0701` | code | organvm/public-record-data-scrapper | Security hardening pass on organvm/public-record-data-scrapper |
| `GH-organvm-limen-534` | code | organvm/limen | needs-human (L-PII-SWEEP-CONTAIN): Contain the org-wide personal-data  |
| `GH-organvm-limen-533` | code | organvm/limen | needs-human (L-SOCIAL-SEND): Pull the actual PUBLISH |
| `GH-organvm-limen-531` | code | organvm/limen | needs-human (L-TCC-PHOTOS-AUTOMATION): Grant Automation permission to  |
| `GH-organvm-limen-530` | code | organvm/limen | needs-human (L-AUDIO-BLACKHOLE): FALLBACK ONLY |
| `GH-organvm-limen-529` | code | organvm/limen | needs-human (L-TCC-RECORDER): Grant Screen Recording + Microphone perm |
| `GH-organvm-limen-538` | code | organvm/limen | needs-human (L-STUDIO-GOLIVE): Take Object Lessons Studio public — the |
| `GEN-organvm-universal-mail--automation-ci-green-0702` | code | organvm/universal-mail--automation | Make organvm/universal-mail--automation CI green |
| `GH-organvm-limen-563` | code | organvm/limen | needs-human (L-CARTRIDGE-REPOINT): Re-plug the chezmoi cartridge into  |
| `GH-organvm-domus-genoma-170` | code | organvm/domus-genoma | chezmoi apply globally broken: allowed_signers.tmpl wants missing ssh_ |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-721` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-cifix-organvm-peer-audited--behavioral-blockchain-727` | code | organvm/peer-audited--behavioral-blockchain | fix failing CI on organvm/peer-audited--behavioral-blockchain#727 |
| `HEAL-cifix-organvm-peer-audited--behavioral-blockchain-730` | code | organvm/peer-audited--behavioral-blockchain | fix failing CI on organvm/peer-audited--behavioral-blockchain#730 |
| `HEAL-cifix-organvm-peer-audited--behavioral-blockchain-744` | code | organvm/peer-audited--behavioral-blockchain | fix failing CI on organvm/peer-audited--behavioral-blockchain#744 |
| `HEAL-cifix-organvm-petasum-super-petasum-148` | code | organvm/petasum-super-petasum | fix failing CI on organvm/petasum-super-petasum#148 |
| `HEAL-cifix-organvm-petasum-super-petasum-149` | code | organvm/petasum-super-petasum | fix failing CI on organvm/petasum-super-petasum#149 |
| `TASK-LED-rev-organvm/public-recor` | code | organvm/public-record-data-scrapper | Heal insight: waste on revenue repo: organvm/public-record-data-scrapp |
| `TASK-LED-rev-organvm/universal-ma` | code | organvm/universal-mail--automation | Heal insight: waste on revenue repo: organvm/universal-mail--automatio |
| `HEAL-cifix-organvm-organvm-ontologia-10` | code | organvm/organvm-ontologia | fix failing CI on organvm/organvm-ontologia#10 |
| `HEAL-rebase-4444j99-hokage-chess-89` | code | organvm/hokage-chess | rebase/resolve conflicts on 4444J99/hokage-chess#89 |
| `HEAL-rebase-organvm-a-i-chat--exporter-30` | code | organvm/a-i-chat--exporter | rebase/resolve conflicts on organvm/a-i-chat--exporter#30 |
| `HEAL-rebase-organvm-a-i-chat--exporter-31` | code | organvm/a-i-chat--exporter | rebase/resolve conflicts on organvm/a-i-chat--exporter#31 |
| `HEAL-cifix-organvm-a-i-chat--exporter-49` | code | organvm/a-i-chat--exporter | fix failing CI on organvm/a-i-chat--exporter#49 |
| `HEAL-rebase-organvm-a-i-chat--exporter-66` | code | organvm/a-i-chat--exporter | rebase/resolve conflicts on organvm/a-i-chat--exporter#66 |
| `HEAL-cifix-organvm-limen-422` | code | organvm/limen | fix failing CI on organvm/limen#422 |
| `HEAL-cifix-organvm-limen-423` | code | organvm/limen | fix failing CI on organvm/limen#423 |
| `HEAL-cifix-organvm-limen-426` | code | organvm/limen | fix failing CI on organvm/limen#426 |
| `HEAL-cifix-organvm-limen-428` | code | organvm/limen | fix failing CI on organvm/limen#428 |
| `HEAL-cifix-organvm-limen-429` | code | organvm/limen | fix failing CI on organvm/limen#429 |
| `HEAL-cifix-organvm-limen-430` | code | organvm/limen | fix failing CI on organvm/limen#430 |
| `HEAL-cifix-organvm-limen-431` | code | organvm/limen | fix failing CI on organvm/limen#431 |
| `HEAL-cifix-organvm-limen-435` | code | organvm/limen | fix failing CI on organvm/limen#435 |
| `HEAL-cifix-organvm-limen-436` | code | organvm/limen | fix failing CI on organvm/limen#436 |
| `HEAL-cifix-organvm-limen-437` | code | organvm/limen | fix failing CI on organvm/limen#437 |
| `HEAL-cifix-organvm-limen-438` | code | organvm/limen | fix failing CI on organvm/limen#438 |
| `HEAL-cifix-organvm-limen-439` | code | organvm/limen | fix failing CI on organvm/limen#439 |
| `HEAL-cifix-organvm-limen-440` | code | organvm/limen | fix failing CI on organvm/limen#440 |
| `HEAL-cifix-organvm-limen-442` | code | organvm/limen | fix failing CI on organvm/limen#442 |
| `HEAL-cifix-organvm-limen-443` | code | organvm/limen | fix failing CI on organvm/limen#443 |
| `HEAL-cifix-organvm-limen-445` | code | organvm/limen | fix failing CI on organvm/limen#445 |
| `HEAL-cifix-organvm-limen-446` | code | organvm/limen | fix failing CI on organvm/limen#446 |
| `HEAL-cifix-organvm-public-process-28` | code | organvm/public-process | fix failing CI on organvm/public-process#28 |
| `HEAL-cifix-organvm-public-process-33` | code | organvm/public-process | fix failing CI on organvm/public-process#33 |
| `HEAL-cifix-organvm-public-process-34` | code | organvm/public-process | fix failing CI on organvm/public-process#34 |
| `HEAL-cifix-organvm-public-record-data-scrapper-315` | code | organvm/public-record-data-scrapper | fix failing CI on organvm/public-record-data-scrapper#315 |
| `HEAL-rebase-organvm-rules-system-bound-6` | code | organvm/rules-system-bound | rebase/resolve conflicts on organvm/rules-system-bound#6 |
| `HEAL-rebase-organvm-rules-system-bound-10` | code | organvm/rules-system-bound | rebase/resolve conflicts on organvm/rules-system-bound#10 |
| `HEAL-cifix-organvm-schema-definitions-7` | code | organvm/schema-definitions | fix failing CI on organvm/schema-definitions#7 |
| `HEAL-cifix-organvm-domus-genoma-141` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#141 |
| `HEAL-cifix-organvm-domus-genoma-142` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#142 |
| `HEAL-cifix-organvm-domus-genoma-149` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#149 |
| `HEAL-cifix-organvm-domus-genoma-154` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#154 |
| `HEAL-cifix-organvm-domus-genoma-159` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#159 |
| `HEAL-cifix-organvm-domus-genoma-160` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#160 |
| `HEAL-cifix-organvm-mirror-mirror-71` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#71 |
| `HEAL-cifix-organvm-mirror-mirror-73` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#73 |
| `HEAL-cifix-organvm-mirror-mirror-77` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#77 |
| `HEAL-cifix-organvm-mirror-mirror-86` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#86 |
| `HEAL-cifix-organvm-mirror-mirror-90` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#90 |
| `HEAL-cifix-organvm-mirror-mirror-94` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#94 |
| `HEAL-cifix-organvm-mirror-mirror-95` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#95 |
| `HEAL-cifix-organvm-mirror-mirror-100` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#100 |
| `HEAL-cifix-organvm-my--father-mother-21` | code | organvm/my--father-mother | fix failing CI on organvm/my--father-mother#21 |
| `HEAL-cifix-organvm-narratological-algorithmic-lenses-36` | code | organvm/narratological-algorithmic-lenses | fix failing CI on organvm/narratological-algorithmic-lenses#36 |
| `HEAL-cifix-organvm-tab-bookmark-manager-28` | code | organvm/tab-bookmark-manager | fix failing CI on organvm/tab-bookmark-manager#28 |
| `HEAL-cifix-organvm-the-invisible-ledger-31` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#31 |
| `HEAL-cifix-organvm-the-invisible-ledger-39` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#39 |
| `HEAL-cifix-organvm-the-invisible-ledger-41` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#41 |
| `HEAL-cifix-organvm-the-invisible-ledger-43` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#43 |
| `HEAL-cifix-organvm-the-invisible-ledger-46` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#46 |
| `HEAL-cifix-organvm-the-invisible-ledger-47` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#47 |
| `HEAL-cifix-organvm-the-invisible-ledger-53` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#53 |
| `HEAL-cifix-organvm-the-invisible-ledger-57` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#57 |
| `HEAL-cifix-organvm-the-invisible-ledger-59` | code | organvm/the-invisible-ledger | fix failing CI on organvm/the-invisible-ledger#59 |
| `HEAL-rebase-organvm-the-invisible-ledger-64` | code | organvm/the-invisible-ledger | rebase/resolve conflicts on organvm/the-invisible-ledger#64 |
| `HEAL-cifix-organvm-universal-mail--automation-118` | code | organvm/universal-mail--automation | fix failing CI on organvm/universal-mail--automation#118 |
| `HEAL-rebase-organvm-universal-mail--automation-119` | code | organvm/universal-mail--automation | rebase/resolve conflicts on organvm/universal-mail--automation#119 |
| `HEAL-cifix-organvm-growth-auditor-13` | code | organvm/growth-auditor | fix failing CI on organvm/growth-auditor#13 |
| `HEAL-rebase-organvm-kerygma-profiles-7` | code | organvm/kerygma-profiles | rebase/resolve conflicts on organvm/kerygma-profiles#7 |
| `HEAL-rebase-organvm-limen-367` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#367 |
| `HEAL-rebase-organvm-limen-377` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#377 |
| `HEAL-rebase-organvm-limen-379` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#379 |
| `HEAL-rebase-stale-organvm-limen-383` | code | organvm/limen | rebase organvm/limen#383 onto current base — stale base touches the da |
| `HEAL-cifix-organvm-limen-384` | code | organvm/limen | fix failing CI on organvm/limen#384 |
| `HEAL-cifix-organvm-limen-385` | code | organvm/limen | fix failing CI on organvm/limen#385 |
| `HEAL-cifix-organvm-limen-386` | code | organvm/limen | fix failing CI on organvm/limen#386 |
| `HEAL-rebase-organvm-limen-387` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#387 |
| `HEAL-rebase-organvm-limen-394` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#394 |
| `HEAL-rebase-stale-organvm-peer-audited--behavioral-blockchain-712` | code | organvm/peer-audited--behavioral-blockchain | rebase organvm/peer-audited--behavioral-blockchain#712 onto current ba |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-713` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-stale-organvm-peer-audited--behavioral-blockchain-715` | code | organvm/peer-audited--behavioral-blockchain | rebase organvm/peer-audited--behavioral-blockchain#715 onto current ba |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-717` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-stale-organvm-peer-audited--behavioral-blockchain-718` | code | organvm/peer-audited--behavioral-blockchain | rebase organvm/peer-audited--behavioral-blockchain#718 onto current ba |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-728` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-729` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-cifix-organvm-atomic-substrata-4` | code | organvm/atomic-substrata | fix failing CI on organvm/atomic-substrata#4 |
| `HEAL-cifix-organvm-bountyscope-8` | code | organvm/bountyscope | fix failing CI on organvm/bountyscope#8 |
| `HEAL-cifix-organvm-bountyscope-9` | code | organvm/bountyscope | fix failing CI on organvm/bountyscope#9 |
| `HEAL-cifix-organvm-bountyscope-13` | code | organvm/bountyscope | fix failing CI on organvm/bountyscope#13 |
| `HEAL-cifix-organvm-bountyscope-14` | code | organvm/bountyscope | fix failing CI on organvm/bountyscope#14 |
| `HEAL-rebase-organvm-organvm-corpvs-testamentvm-491` | code | organvm/organvm-corpvs-testamentvm | rebase/resolve conflicts on organvm/organvm-corpvs-testamentvm#491 |
| `HEAL-rebase-organvm-organvm-corpvs-testamentvm-496` | code | organvm/organvm-corpvs-testamentvm | rebase/resolve conflicts on organvm/organvm-corpvs-testamentvm#496 |
| `HEAL-rebase-organvm-organvm-corpvs-testamentvm-505` | code | organvm/organvm-corpvs-testamentvm | rebase/resolve conflicts on organvm/organvm-corpvs-testamentvm#505 |
| `HEAL-cifix-organvm-organvm-engine-101` | code | organvm/organvm-engine | fix failing CI on organvm/organvm-engine#101 |
| `HEAL-cifix-organvm-organvm-engine-108` | code | organvm/organvm-engine | fix failing CI on organvm/organvm-engine#108 |
| `HEAL-cifix-organvm-organvm-engine-110` | code | organvm/organvm-engine | fix failing CI on organvm/organvm-engine#110 |
| `HEAL-cifix-organvm-organvm-engine-111` | code | organvm/organvm-engine | fix failing CI on organvm/organvm-engine#111 |
| `GH-organvm-limen-651` | code | organvm/limen | needs-human (L-FLEET-DISPATCH): The whole board is partitioned + route |
| `HEAL-rebase-stale-organvm-universal-mail--automation-129` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#129 onto current base — bran |
| `HEAL-rebase-stale-organvm-universal-mail--automation-137` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#137 onto current base — bran |
| `GH-organvm-limen-657` | code | organvm/limen | needs-human (L-LAVREA-LAUNCH): Post the LAVREA launch kit under your o |
| `HEAL-cifix-organvm-limen-402` | code | organvm/limen | fix failing CI on organvm/limen#402 |
| `HEAL-cifix-organvm-limen-406` | code | organvm/limen | fix failing CI on organvm/limen#406 |
| `HEAL-cifix-organvm-limen-407` | code | organvm/limen | fix failing CI on organvm/limen#407 |
| `HEAL-cifix-organvm-limen-408` | code | organvm/limen | fix failing CI on organvm/limen#408 |
| `HEAL-cifix-organvm-limen-409` | code | organvm/limen | fix failing CI on organvm/limen#409 |
| `HEAL-cifix-organvm-limen-411` | code | organvm/limen | fix failing CI on organvm/limen#411 |
| `HEAL-cifix-organvm-limen-413` | code | organvm/limen | fix failing CI on organvm/limen#413 |
| `HEAL-cifix-organvm-limen-415` | code | organvm/limen | fix failing CI on organvm/limen#415 |
| `HEAL-cifix-organvm-limen-417` | code | organvm/limen | fix failing CI on organvm/limen#417 |
| `HEAL-cifix-organvm-limen-418` | code | organvm/limen | fix failing CI on organvm/limen#418 |
| `HEAL-cifix-organvm-limen-419` | code | organvm/limen | fix failing CI on organvm/limen#419 |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-757` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-cifix-organvm-peer-audited--behavioral-blockchain-771` | code | organvm/peer-audited--behavioral-blockchain | fix failing CI on organvm/peer-audited--behavioral-blockchain#771 |
| `HEAL-cifix-organvm-portfolio-146` | code | organvm/portfolio | fix failing CI on organvm/portfolio#146 |
| `HEAL-rebase-organvm-portfolio-157` | code | organvm/portfolio | rebase/resolve conflicts on organvm/portfolio#157 |
| `HEAL-cifix-organvm-portfolio-175` | code | organvm/portfolio | fix failing CI on organvm/portfolio#175 |
| `HEAL-cifix-organvm-portfolio-178` | code | organvm/portfolio | fix failing CI on organvm/portfolio#178 |
| `HEAL-cifix-organvm-domus-genoma-103` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#103 |
| `HEAL-cifix-organvm-domus-genoma-109` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#109 |
| `HEAL-cifix-organvm-domus-genoma-118` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#118 |
| `HEAL-cifix-organvm-domus-genoma-125` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#125 |
| `HEAL-rebase-organvm-session-meta-135` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#135 |
| `HEAL-rebase-organvm-session-meta-143` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#143 |
| `HEAL-rebase-organvm-session-meta-146` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#146 |
| `HEAL-cifix-organvm-session-meta-149` | code | organvm/session-meta | fix failing CI on organvm/session-meta#149 |
| `HEAL-cifix-organvm-system-governance-framework-43` | code | organvm/system-governance-framework | fix failing CI on organvm/system-governance-framework#43 |
| `HEAL-rebase-stale-organvm-universal-mail--automation-124` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#124 onto current base — bran |
| `HEAL-rebase-stale-organvm-universal-mail--automation-127` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#127 onto current base — bran |
| `HEAL-rebase-stale-organvm-universal-mail--automation-128` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#128 onto current base — bran |
| `HEAL-cifix-organvm-limen-449` | code | organvm/limen | fix failing CI on organvm/limen#449 |
| `HEAL-cifix-organvm-limen-450` | code | organvm/limen | fix failing CI on organvm/limen#450 |
| `HEAL-cifix-organvm-limen-452` | code | organvm/limen | fix failing CI on organvm/limen#452 |
| `HEAL-cifix-organvm-limen-453` | code | organvm/limen | fix failing CI on organvm/limen#453 |
| `HEAL-cifix-organvm-limen-455` | code | organvm/limen | fix failing CI on organvm/limen#455 |
| `HEAL-cifix-organvm-limen-456` | code | organvm/limen | fix failing CI on organvm/limen#456 |
| `HEAL-cifix-organvm-limen-457` | code | organvm/limen | fix failing CI on organvm/limen#457 |
| `HEAL-rebase-organvm-session-meta-82` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#82 |
| `HEAL-rebase-stale-organvm-session-meta-95` | code | organvm/session-meta | rebase organvm/session-meta#95 onto current base — branched far behind |
| `HEAL-rebase-organvm-session-meta-106` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#106 |
| `HEAL-rebase-organvm-session-meta-112` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#112 |
| `HEAL-rebase-organvm-session-meta-128` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#128 |
| `HEAL-rebase-organvm-session-meta-133` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#133 |
| `HEAL-cifix-organvm-domus-genoma-172` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#172 |
| `HEAL-cifix-organvm-domus-genoma-174` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#174 |
| `HEAL-cifix-organvm-domus-genoma-175` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#175 |
| `HEAL-rebase-organvm-session-meta-164` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#164 |
| `HEAL-cifix-organvm-mirror-mirror-106` | code | organvm/mirror-mirror | fix failing CI on organvm/mirror-mirror#106 |
| `HEAL-rebase-stale-organvm-the-invisible-ledger-46` | code | organvm/the-invisible-ledger | rebase organvm/the-invisible-ledger#46 onto current base — branched fa |
| `HEAL-drain-lock-scope-0707` | code | organvm/limen | Move drain writers out of heartbeat queue-lock starvation path |
| `HEAL-storage-reclaim-scale-0707` | code | organvm/limen | Make worktree and scratch reclaim fast enough to protect local SSD |
| `HEAL-rebase-organvm-domus-genoma-153` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#153 |
| `HEAL-rebase-stale-organvm-the-invisible-ledger-31` | code | organvm/the-invisible-ledger | rebase organvm/the-invisible-ledger#31 onto current base — branched fa |
| `GH-organvm-limen-688` | code | organvm/limen | Build external estate custody implementation receipt |
| `HEAL-rebase-stale-organvm-limen-434` | code | organvm/limen | rebase organvm/limen#434 onto current base — stale base touches the da |
| `HEAL-rebase-organvm-mirror-mirror-95` | code | organvm/mirror-mirror | rebase/resolve conflicts on organvm/mirror-mirror#95 |
| `GH-organvm-domus-genoma-203` | code | organvm/domus-genoma | Remove checked-in .git-task Git directory from Limen PR #187 |
| `GH-organvm-universal-mail-automation-150` | code | organvm/universal-mail--automation | Clean generated and merge-residue files from Limen repair PRs |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-712` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-organvm-domus-genoma-138` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#138 |
| `HEAL-rebase-organvm-domus-genoma-141` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#141 |
| `HEAL-rebase-organvm-domus-genoma-142` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#142 |
| `HEAL-rebase-organvm-domus-genoma-176` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#176 |
| `HEAL-rebase-organvm-domus-genoma-185` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#185 |
| `HEAL-rebase-organvm-domus-genoma-163` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#163 |
| `HEAL-rebase-organvm-domus-genoma-172` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#172 |
| `HEAL-rebase-organvm-domus-genoma-178` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#178 |
| `HEAL-rebase-organvm-domus-genoma-179` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#179 |
| `EXCAV-0708-TABULARIUS-665` | code | organvm/limen | Land the TABULARIUS/VLTIMA single-writer kernel (PR#665) |
| `EXCAV-0708-SCRATCH-REAP` | code | organvm/limen | Reap the standing scratch debt: ~22G gemini antigravity scratch + ~37G |
| `EXCAV-0708-BURIED-SWEEP` | code | organvm/limen | Adversarially verify the 16 unchecked buried-treasure candidates |
| `ORIGIN-0708-ARC4N-CELLULAR` | code | organvm/linguistic-atomization-framework | ARC4N cellular text-atomization as a distinct engine (letters/words/se |
| `HEAL-rebase-organvm-limen-617` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#617 |
| `HEAL-rebase-organvm-limen-623` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#623 |
| `HEAL-rebase-organvm-the-invisible-ledger-38` | code | organvm/the-invisible-ledger | rebase/resolve conflicts on organvm/the-invisible-ledger#38 |
| `HEAL-rebase-organvm-the-invisible-ledger-39` | code | organvm/the-invisible-ledger | rebase/resolve conflicts on organvm/the-invisible-ledger#39 |
| `HEAL-rebase-stale-organvm-the-invisible-ledger-41` | code | organvm/the-invisible-ledger | rebase organvm/the-invisible-ledger#41 onto current base — branched fa |
| `HEAL-rebase-organvm-the-invisible-ledger-53` | code | organvm/the-invisible-ledger | rebase/resolve conflicts on organvm/the-invisible-ledger#53 |
| `HEAL-rebase-organvm-the-invisible-ledger-55` | code | organvm/the-invisible-ledger | rebase/resolve conflicts on organvm/the-invisible-ledger#55 |
| `HEAL-rebase-organvm-domus-genoma-120` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#120 |
| `GH-organvm-limen-719` | code | organvm/limen | L-ARCA-KEY-ESCROW: escrow the ARCA vault key off-machine (his-hand) |
| `GH-organvm-limen-764` | code | organvm/limen | censor: Recurring friction across 3 insights reports: Hollow premature |
| `GH-organvm-limen-763` | code | organvm/limen | censor: Recurring friction across 2 insights reports: Premature or hol |
| `HEAL-rebase-organvm-session-meta-142` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#142 |
| `HEAL-rebase-stale-organvm-universal-mail--automation-125` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#125 onto current base — bran |
| `HEAL-rebase-stale-organvm-universal-mail--automation-135` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#135 onto current base — bran |
| `HEAL-rebase-stale-organvm-universal-mail--automation-138` | code | organvm/universal-mail--automation | rebase organvm/universal-mail--automation#138 onto current base — bran |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-714` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-727` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-733` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-752` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `HEAL-rebase-organvm-peer-audited--behavioral-blockchain-775` | code | organvm/peer-audited--behavioral-blockchain | rebase/resolve conflicts on organvm/peer-audited--behavioral-blockchai |
| `GH-organvm-limen-766` | code | organvm/limen | censor: Recurring friction across 3 insights reports: Closeout stall l |
| `HEAL-rebase-organvm-domus-genoma-135` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#135 |
| `HEAL-rebase-organvm-domus-genoma-140` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#140 |
| `aw-agy-scratch-preserve-0709` | code | organvm/limen | Archive-first preservation of Antigravity scratch roots (22 GiB prompt |
| `GH-organvm-limen-774` | code | organvm/limen | Land the dispatch-admission lane preserved on heal/live-main-snapshot- |
| `GH-organvm-limen-790` | code | organvm/limen | needs-human (L-ESTATE-MOUNT-4444J99): MOUNT the 4444J99 SSD to recover |
| `GH-organvm-limen-789` | code | organvm/limen | needs-human (L-MONETA-LAUNCH): Post the MONETA Mint-as-a-Service launc |
| `GH-organvm-manumissio-9` | code | organvm/manumissio | Phase 3: hardware sizing dossier (gauge-gated — do not buy early) |
| `GH-organvm-manumissio-5` | code | organvm/manumissio | Phase 1: arm the first floor classes when the parity gate passes |
| `GH-organvm-manumissio-4` | code | organvm/manumissio | Phase 1-2: candidate weights worth owning — the acquisition ledger |
| `GH-organvm-limen-827` | code | organvm/limen | [his-hand] Arm the Fable interactive-guard settings snippet |
| `HEAL-cifix-organvm-domus-genoma-231` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#231 |
| `GH-organvm-universal-mail-automation-157` | code | organvm/universal-mail--automation | Waste triage 2026-07-09: closed 6 stale PRs, 3 green PRs ready to merg |
| `HEAL-rebase-organvm-session-meta-149` | code | organvm/session-meta | rebase/resolve conflicts on organvm/session-meta#149 |
| `HEAL-rebase-organvm-universal-mail--automation-138` | code | organvm/universal-mail--automation | rebase/resolve conflicts on organvm/universal-mail--automation#138 |
| `HEAL-rebase-organvm-a-i-chat--exporter-49` | code | organvm/a-i-chat--exporter | rebase/resolve conflicts on organvm/a-i-chat--exporter#49 |
| `HEAL-rebase-organvm-a-i-chat--exporter-54` | code | organvm/a-i-chat--exporter | rebase/resolve conflicts on organvm/a-i-chat--exporter#54 |
| `HEAL-rebase-organvm-a-i-chat--exporter-115` | code | organvm/a-i-chat--exporter | rebase/resolve conflicts on organvm/a-i-chat--exporter#115 |
| `HEAL-rebase-organvm-domus-genoma-124` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#124 |
| `HEAL-rebase-organvm-domus-genoma-173` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#173 |
| `HEAL-rebase-organvm-domus-genoma-184` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#184 |
| `HEAL-rebase-organvm-domus-genoma-230` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#230 |
| `HEAL-rebase-organvm-domus-genoma-233` | code | organvm/domus-genoma | rebase/resolve conflicts on organvm/domus-genoma#233 |
| `GH-organvm-limen-894` | code | organvm/limen | routine-freshness: a delta-gated routine that is healthy-but-silent mu |
| `HEAL-rebase-organvm-limen-680` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#680 |
| `HEAL-rebase-organvm-limen-682` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#682 |
| `HEAL-rebase-organvm-limen-696` | code | organvm/limen | rebase/resolve conflicts on organvm/limen#696 |
| `HEAL-rebase-stale-organvm-limen-812` | code | organvm/limen | rebase organvm/limen#812 onto current base — stale base touches the da |
| `HEAL-rebase-stale-organvm-limen-815` | code | organvm/limen | rebase organvm/limen#815 onto current base — branched far behind |
| `HEAL-cifix-organvm-manumissio-18` | code | organvm/manumissio | fix failing CI on organvm/manumissio#18 |
| `HEAL-cifix-organvm-manumissio-20` | code | organvm/manumissio | fix failing CI on organvm/manumissio#20 |
| `HEAL-cifix-organvm-manumissio-24` | code | organvm/manumissio | fix failing CI on organvm/manumissio#24 |
| `HEAL-rebase-organvm-mirror-mirror-125` | code | organvm/mirror-mirror | rebase/resolve conflicts on organvm/mirror-mirror#125 |
| `GH-organvm-limen-961` | code | organvm/limen | needs-human (L-OBSERVATORY-ACTIVATE): Activate OBSERVATORY (the legibi |
| `GH-organvm-limen-960` | code | organvm/limen | needs-human (L-MAIL-AUTOMATION-GRANT): Grant macOS Automation permissi |
| `GH-organvm-limen-928` | code | organvm/limen | needs-human (L-OPENCODE-AUTH): optionally authorize OpenCode catalog a |
| `GH-organvm-limen-927` | code | organvm/limen | needs-human (L-IDENTITY-POPULATE): Populate the core personal-fact ato |
| `GH-organvm-limen-926` | code | organvm/limen | needs-human (L-FABLE-GUARD-ARM): Arm the Fable interactive-guard setti |
| `GH-organvm-limen-910` | code | organvm/limen | needs-human (L-LIMENBOT-INSTALL): Create + install the limen[bot] GitH |
| `HEAL-rebase-organvm-the-invisible-ledger-31` | code | organvm/the-invisible-ledger | rebase/resolve conflicts on organvm/the-invisible-ledger#31 |
| `HEAL-cifix-organvm-domus-genoma-300` | code | organvm/domus-genoma | fix failing CI on organvm/domus-genoma#300 |

## STALE — precondition already satisfied (daemon already dispatching) — recommend close

| id | type | repo | title |
|---|---|---|---|
| `ASK-7-dispatch-drain-open` | code | — | Live-dispatch across all 6 vendors to clear the 255 open tasks; keep o |

## REVIEW — irreversible/ambiguous (skip-vs-kill) — one human triage pass

| id | type | repo | title |
|---|---|---|---|
| `GH-organvm-iv-taxis-organvm-iv-taxis-superproject-6` | code | organvm/organvm-iv-taxis--superproject | ACTIVATION AUDIT: skip |
| `GH-organvm-iv-taxis-organvm-iv-taxis-superproject-5` | code | organvm/organvm-iv-taxis--superproject | ACTIVATION AUDIT: kill |
| `GH-organvm-v-logos-organvm-v-logos-superproject-6` | code | organvm/organvm-v-logos--superproject | ACTIVATION AUDIT: kill |
| `GH-organvm-vi-koinonia-organvm-vi-koinonia-superproject-3` | code | organvm/organvm-vi-koinonia--superproject | ACTIVATION AUDIT: kill |
| `DISCOVER-organvm-parlor-games--ephemera-engine` | research | organvm/parlor-games--ephemera-engine | Discover the latent value of organvm/parlor-games--ephemera-engine |
| `DISCOVER-organvm-gamified-coach-interface` | research | organvm/gamified-coach-interface | Discover the latent value of organvm/gamified-coach-interface |
| `DISCOVER-organvm-visual-substrate-inquiry` | research | organvm/visual-substrate-inquiry | Discover the latent value of organvm/visual-substrate-inquiry |
| `studium-corpus-shahnameh` | content | organvm/limen | Fetch Shahnameh original (ganjoor.net) → corpus arabic-persian/shahnam |
| `studium-film-divine-comedy` | content | organvm/limen | Divine Comedy film companion (descent/ascent/beatitude) |
| `studium-film-heike` | content | organvm/limen | Tale of the Heike film companion (mono no aware) |
| `DISCOVER-organvm-my--father-mother` | research | organvm/my--father-mother | Discover the latent value of organvm/my--father-mother |
| `EDU-summer-live-date-handoff` | ops | organvm/edu-organism | Assemble the summer-2026 live-D2L date paste-list + drafted student re |
| `ASK-quicken-d2l` | ops | — | the D2L go-live click + cadence confirm (your login + judgment) |
| `ORG-media-organ-deepen-0630` | content | organvm/limen | Deepen the media organ toward a usable institution |
| `ORG-social-organ-kernel-0630` | content | organvm/limen | Map the VLTIMA 5-primitive kernel to the social organ |
| `DISCOVER-organvm-my-knowledge-base` | research | organvm/my-knowledge-base | Discover the latent value of organvm/my-knowledge-base |
| `DISCOVER-organvm-the-actual-news` | research | organvm/the-actual-news | Discover the latent value of organvm/the-actual-news |
| `DISCOVER-organvm-glyph-cascade-tapes` | research | organvm/glyph-cascade-tapes | Discover the latent value of organvm/glyph-cascade-tapes |
| `DISCOVER-organvm-sovereign-systems--layer-above-hokage` | research | organvm/sovereign-systems--layer-above-hokage | Discover the latent value of organvm/sovereign-systems--layer-above-ho |
| `DISCOVER-organvm-metasystem-master` | research | organvm/metasystem-master | Discover the latent value of organvm/metasystem-master |
| `DISCOVER-organvm-schema-definitions` | research | organvm/schema-definitions | Discover the latent value of organvm/schema-definitions |
| `DISCOVER-organvm-radix-recursiva-solve-coagula-redi` | research | organvm/radix-recursiva-solve-coagula-redi | Discover the latent value of organvm/radix-recursiva-solve-coagula-red |
| `DISCOVER-organvm-a-recursive-root` | research | organvm/a-recursive-root | Discover the latent value of organvm/a-recursive-root |
| `DISCOVER-organvm-dot-github--poiesis` | research | organvm/dot-github--poiesis | Discover the latent value of organvm/dot-github--poiesis |
| `DISCOVER-organvm-auto-revision-epistemic-engine` | research | organvm/auto-revision-epistemic-engine | Discover the latent value of organvm/auto-revision-epistemic-engine |
| `ORG-media-organ-selffeed-0701` | content | organvm/limen | Wire the media organ to advance autonomously |
| `DISCOVER-organvm-styx-behavioral-art` | research | organvm/styx-behavioral-art | Discover the latent value of organvm/styx-behavioral-art |
| `ASK-quicken-delete` | ops | — | approve the irreversible delete/clear (archived reversibly; purge is y |
| `DISCOVER-organvm-fetch-familiar-friends` | research | organvm/fetch-familiar-friends | Discover the latent value of organvm/fetch-familiar-friends |
| `ORG-financial-organ-deepen-0703` | content | organvm/limen | Deepen the financial organ toward a usable institution |
| `ORG-education-organ-face-0703` | content | organvm/limen | Make the education organ's macro + micro face excellent |
| `ORG-legal-organ-charter-0703` | content | organvm/limen | Charter the legal organ as an institution rivaling a top-tier litigati |
| `ORG-social-organ-charter-0703` | content | organvm/limen | Charter the social organ as an institution rivaling a civic/community  |
| `ORG-legal-organ-firstslice-0703` | content | organvm/limen | Build the first working vertical slice of the legal organ |
| `ORG-consulting-organ-face-0704` | content | organvm/limen | Make the consulting organ's macro + micro face excellent |
| `ORG-health-organ-kernel-0704` | content | organvm/limen | Map the VLTIMA 5-primitive kernel to the health organ |
| `ORG-social-organ-charter-0704` | content | organvm/limen | Charter the social organ as an institution rivaling a civic/community  |
| `ORG-hr-organ-kernel-0704` | content | organvm/limen | Map the VLTIMA 5-primitive kernel to the hr organ |
| `ORG-hr-organ-charter-0704` | content | organvm/limen | Charter the hr organ as an institution rivaling a Fortune-500 people o |
| `ORG-hr-organ-firstslice-0704` | content | organvm/limen | Build the first working vertical slice of the hr organ |
| `ORG-contributions-organ-selffeed-0704` | content | organvm/limen | Wire the contributions organ to advance autonomously |
| `ASK-quicken-send` | ops | — | send the drafted message (never auto-send) |
| `ORG-social-organ-firstslice-0704` | content | organvm/limen | Build the first working vertical slice of the social organ |
| `ORG-legal-organ-kernel-0705` | content | organvm/limen | Map the VLTIMA 5-primitive kernel to the legal organ |
| `ORG-health-organ-charter-0705` | content | organvm/limen | Charter the health organ as an institution rivaling a concierge medica |
| `ORG-hr-organ-kernel-0705` | content | organvm/limen | Map the VLTIMA 5-primitive kernel to the hr organ |
| `ORG-hr-organ-charter-0705` | content | organvm/limen | Charter the hr organ as an institution rivaling a Fortune-500 people o |
| `ORG-contributions-organ-face-0705` | content | organvm/limen | Make the contributions organ's macro + micro face excellent |
| `DISCOVER-organvm-pages--theoria-copy--logos` | research | organvm/pages--theoria-copy--logos | Discover the latent value of organvm/pages--theoria-copy--logos |
| `DISCOVER-organvm-pages--theoria-copy--meta-organvm` | research | organvm/pages--theoria-copy--meta-organvm | Discover the latent value of organvm/pages--theoria-copy--meta-organvm |
| `DISCOVER-organvm-sovereign--ground--4444j99` | research | organvm/sovereign--ground--4444j99 | Discover the latent value of organvm/sovereign--ground--4444j99 |
| `DISCOVER-organvm-studium-generale--4444j99` | research | organvm/studium-generale--4444j99 | Discover the latent value of organvm/studium-generale--4444j99 |
| `DISCOVER-organvm-browser-state` | research | organvm/browser-state | Discover the latent value of organvm/browser-state |
| `DISCOVER-organvm-cind-and-sol-foundation` | research | organvm/cind-and-sol-foundation | Discover the latent value of organvm/cind-and-sol-foundation |
| `DISCOVER-organvm-quaestor` | research | organvm/quaestor | Discover the latent value of organvm/quaestor |
| `DISCOVER-organvm-palimpsest` | research | organvm/palimpsest | Discover the latent value of organvm/palimpsest |
| `DISCOVER-organvm-gens` | research | organvm/gens | Discover the latent value of organvm/gens |
| `AW-VALUE-REPOS` | coordination | organvm/a-i-chat--exporter,organvm/my-knowledge-base,organvm/public-record-data-scrapper,organvm/mirror-mirror,organvm/universal-mail--automation | Assign revenue/value repo work from existing ledgers |
| `ASK-quicken-escalate-4a4c2aa8` | ops | — | finish stalled session 'Build alchemical synthesizer for audio sampl'  |
| `ASK-quicken-escalate-e0f151ab` | ops | — | finish stalled session 'bash permission config investigation' (breathe |
| `ASK-lane-starved-agy` | ops | — | Lane 'agy' starved: silent >42.5h with open queue + ok budget |
| `ASK-lane-starved-gemini` | ops | — | Lane 'gemini' starved: silent >47.8h with open queue + ok budget |
| `ASK-lane-starved-opencode` | ops | — | Lane 'opencode' starved: silent >42.4h with open queue + ok budget |
| `ORG-sovereignty-organ-deepen-0709` | content | organvm/manumissio | Deepen the sovereignty organ toward a usable institution |
| `ORG-sovereignty-organ-selffeed-0709` | content | organvm/manumissio | Wire the sovereignty organ to advance autonomously |
| `ASK-quicken-escalate-6a48ce1d` | ops | — | finish stalled session 'Design movement ontology and workout composi'  |
| `ASK-quicken-escalate-0bd3a5ed` | ops | — | finish stalled session 'Design movement ontology and workout composi'  |
| `SOVEREIGN-0708-GPG-UID` | ops | organvm/limen | Add the later recourse.email UID to the current GPG identity |
| `ASK-quicken-escalate-9feaa902` | ops | organvm/limen | finish stalled session 'Complete chat tasks with appropriate model a'  |

## KEEP — real human atom (secret/account/admin/merge-gate/cutover/credential-gated deploy)

| id | type | repo | title |
|---|---|---|---|
| `LIMEN-072` | docs | organvm/organvm-engine | descent: expand branch protection to all organs |
| `LIMEN-077` | docs | organvm/organvm-engine | Fix soak-test LaunchAgent — gh CLI auth fails under launchd |
| `LIMEN-091` | docs | organvm/public-record-data-scrapper | PR #234 security gate prerequisites (JWT_SECRET, org_id) |
| `BLD2-a-i-chat--exporter-deploy` | code | organvm/a-i-chat--exporter | a-i-chat--exporter: deploy |
| `BLD2-public-record-data-scrapper-deploy` | code | organvm/public-record-data-scrapper | public-record-data-scrapper: deploy |
| `BLD2-mirror-mirror-deploy` | code | organvm/mirror-mirror | mirror-mirror: deploy |
| `BLD2-universal-mail--automation-deploy` | code | organvm/universal-mail--automation | universal-mail--automation: deploy |
| `BLD2-peer-audited--behavioral-blockchain-deploy` | code | organvm/peer-audited--behavioral-blockchain | peer-audited--behavioral-blockchain: deploy |
| `BLD2-the-invisible-ledger-deploy` | code | organvm/the-invisible-ledger | the-invisible-ledger: deploy |
| `BLD2-promptscope-deploy` | code | organvm/promptscope | promptscope: deploy |
| `BLD2-writelens-deploy` | code | organvm/writelens | writelens: deploy |
| `BLD2-edgarflash-deploy` | code | organvm/edgarflash | edgarflash: deploy |
| `BLD2-trendpulse-deploy` | code | organvm/trendpulse | trendpulse: deploy |
| `BLD2-essay-pipeline-deploy` | code | organvm/essay-pipeline | essay-pipeline: deploy |
| `BLD2-tab-bookmark-manager-deploy` | code | organvm/tab-bookmark-manager | tab-bookmark-manager: deploy |
| `BLD2-narratological-algorithmic-lenses-deploy` | code | organvm/narratological-algorithmic-lenses | narratological-algorithmic-lenses: deploy |
| `BLD2-card-trade-social-deploy` | code | organvm/card-trade-social | card-trade-social: deploy |
| `BLD2-bountyscope-deploy` | code | organvm/bountyscope | bountyscope: deploy |
| `BLD2-vulnpulse-deploy` | code | organvm/vulnpulse | vulnpulse: deploy |
| `ASK-2-one-container-cutover` | code | — | Run the gated one-container cutover (container/migrate.sh S4-S13) unde |
| `ASK-5-open-merge-gate` | code | — | Open the merge gate: parallel merge pass on the ~111 merge-ready PRs,  |
| `ASK-20-container-relocate-state` | code | — | Extend container/manifest.tsv to relocate bulky agent state dirs (~/.c |
| `REV-organvm-styx-revenue-ship-0623` | code | organvm/styx | Drive Styx to deploy-ready |
| `REV-organvm-styx-revenue-readiness-0623` | code | organvm/styx | First-paying-customer readiness pass on Styx |
| `ASK-quicken-login` | ops | — | one login/identity step (your hand: browser/OAuth/portal) |
| `REVENUE-exporter-first-dollar` | ops | — | Drive live ChatGPT Exporter to first-$ rail (Sponsors + Pro tier) |
| `GH-organvm-limen-265` | code | organvm/limen | needs-human (L-FLEET-CAPACITY): Re-mint the 3 fleet credentials — they |
| `GH-organvm-limen-255` | code | organvm/limen | needs-human (L-CONTAINER-CUTOVER): One-container cutover |
| `GH-organvm-limen-254` | code | organvm/limen | needs-human (L-CLOUDFLARE-DEPLOY): Cloudflare deploy auth |
| `GH-organvm-limen-253` | code | organvm/limen | needs-human (L-REVENUE-ACCT): Revenue first-dollar accounts |
| `ASK-quicken-credential` | ops | — | land the credential/secret (your account/identity) |
| `REV-organvm-a-i-chat--exporter-revenue-funding-0628` | code | organvm/a-i-chat--exporter | Stage the donation funnel for ChatGPT Exporter |
| `REV-organvm-public-record-data-scrapper-revenue-ship-0628` | code | organvm/public-record-data-scrapper | Drive Public Record Data Scraper to deploy-ready |
| `REV-organvm-a-i-chat--exporter-revenue-pro-tier-0628` | code | organvm/a-i-chat--exporter | Make the Pro-tier checkout merge-ready for ChatGPT Exporter |
| `REV-organvm-universal-mail--automation-revenue-readiness-0628` | code | organvm/universal-mail--automation | First-paying-customer readiness pass on Universal Mail Automation |
| `REV-organvm-the-invisible-ledger-revenue-readiness-0628` | code | organvm/the-invisible-ledger | First-paying-customer readiness pass on The Invisible Ledger |
| `REV-organvm-a-i-chat--exporter-revenue-landing-0628` | code | organvm/a-i-chat--exporter | Ship a landing page for ChatGPT Exporter |
| `REV-organvm-a-i-chat--exporter-revenue-launch-post-0628` | code | organvm/a-i-chat--exporter | Draft the build-in-public launch post for ChatGPT Exporter |
| `REV-organvm-public-record-data-scrapper-revenue-readiness-0629` | code | organvm/public-record-data-scrapper | First-paying-customer readiness pass on Public Record Data Scraper |
| `REV-organvm-universal-mail--automation-revenue-ship-0630` | code | organvm/universal-mail--automation | Drive Universal Mail Automation to deploy-ready |
| `REV-organvm-the-invisible-ledger-revenue-ship-0630` | code | organvm/the-invisible-ledger | Drive The Invisible Ledger to deploy-ready |
| `REV-organvm-mirror-mirror-revenue-readiness-0630` | code | organvm/mirror-mirror | First-paying-customer readiness pass on Mirror Mirror |
| `GH-organvm-limen-535` | code | organvm/limen | needs-human (L-GCP-DEPLOY-SA): media-ark hosted go-live — a HUMAN HOST |
| `GH-organvm-limen-532` | code | organvm/limen | needs-human (L-SOCIAL-OAUTH): Create the developer apps + mint first a |
| `ORG-governance-organ-deepen-0703` | content | organvm/limen | Deepen the governance organ toward a usable institution |
| `ORG-governance-organ-selffeed-0703` | content | organvm/limen | Wire the governance organ to advance autonomously |
| `REVIEW-peer-audited-726-thread-remediation-0707` | code | organvm/peer-audited--behavioral-blockchain | Address live review blockers on peer-audited#726 before merge |
| `REV-organvm-mirror-mirror-revenue-ship-0707` | code | organvm/mirror-mirror | Drive Mirror Mirror to deploy-ready |
| `GH-organvm-limen-686` | code | organvm/limen | Add historical token tombstone audit to the credential wall |
| `RETRO-0708-CODEX-BUDGET-RESET` | code | organvm/limen | Codex per-task budget reset + pre-dispatch uncached-token cap |
| `ASK-quicken-escalate-0305e50a` | ops | — | finish stalled session 'Audit Codex handoff and validate token-accou'  |
| `GH-organvm-limen-791` | code | organvm/limen | needs-human (L-DAILY-ENGINE-PHONE-SETUP): Daily-engine phone setup |
| `REV-organvm-mirror-mirror-revenue-ship-0709` | code | organvm/mirror-mirror | Drive Mirror Mirror to deploy-ready |
| `GH-organvm-limen-934` | code | organvm/limen | needs-human (L-INTEGRATION-RENOVATE): install Renovate on organvm + tr |
| `GH-organvm-limen-933` | code | organvm/limen | needs-human (L-INTEGRATION-CODERABBIT): install CodeRabbit on organvm  |
| `GH-organvm-limen-912` | code | organvm/limen | needs-human (L-STORAGE-DRAIN-PUSHED): Flip LIMEN_RECLAIM_PUSHED_OK=1 i |
| `SOVEREIGN-0708-GPG-ESCROW` | ops | organvm/limen | Escrow the current GPG private material off-machine |
| `SOVEREIGN-0708-GPG-DISCOVERABILITY` | ops | organvm/limen | Publish the current GPG public key to a discoverable surface |

---
*Generated by `scripts/reclassify-needs-human.py`. Re-run `--apply` to flip the FLIP bucket, or say the word and I will.*
