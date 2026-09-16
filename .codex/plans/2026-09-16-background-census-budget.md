# Background census nested budget repair

Owner: Codex; IRF-SYS-257 heartbeat acceptance.

Native receipt 4ddb85f25a254e06ac32fd5cc10ef926 recorded a 30-second background-items-census timeout and unknown descendant cleanup. Its inner sfltool timeout equaled the outer probe deadline. Replace subprocess.run with the existing bounded subprocess runner, give the child 15 seconds within the existing 30-second outer limit, and cap stdout/stderr at 256 KiB/16 KiB. The runner terminates and reaps only the process group it creates.

Unavailable or overflowed BTM captures report status unmeasured and total null. Declaration-parity checks remain separate; missing advisory BTM data does not imply zero identifiers. No plist, TCC setting, launchd state or existing process is changed.

Twelve focused tests pass, including a real isolated sleeping child whose PID is gone before the outer deadline, and an oversized-output child whose partial identifiers are not accepted. The full scoped batch and live bounded observation must be recorded separately. Source landing does not establish adoption by the immutable installed runtime.

## Verification receipt

Code head 8f6dffa64 passed scripts/verify-scoped.sh --base origin/main: ten cheap gates, 7,748 CLI tests (two skipped), and 52 API tests. The live observation process output was unavailable after context recovery and is not counted as evidence. Installed-runtime adoption remains a separate acceptance obligation.
