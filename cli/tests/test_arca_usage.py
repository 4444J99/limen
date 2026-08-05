"""scripts/arca.sh must never start a backup because someone asked it what it does.

`CMD="${1:-backup}"` meant a bare invocation swept every ~/Workspace/_*-private store, encrypted it,
and pushed ciphertext to a private remote — and there was no `--help`, so the natural way to ask
"what are the verbs?" was the one input that ran that path. Found 2026-07-29 by doing exactly that.

These tests run the real script. They are safe *because* of the fix: every case asserted here exits
before `ensure_vault`, so nothing touches the vault, the keychain, or the network.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCA = ROOT / "scripts" / "arca.sh"


def run(*args):
    return subprocess.run(["bash", str(ARCA), *args], capture_output=True, text=True, check=False, timeout=30)


def test_a_bare_invocation_refuses_instead_of_backing_up():
    proc = run()
    assert proc.returncode == 2, "a bare invocation must refuse — it used to START A BACKUP"
    # stderr + nonzero so a caller relying on the old implicit default fails LOUDLY rather than
    # silently doing nothing, which would be a quieter bug than the one being fixed.
    assert "A VERB IS REQUIRED" in proc.stderr
    assert "backup" in proc.stderr and "restore" in proc.stderr


@pytest.mark.parametrize("flag", ["-h", "--help", "help"])
def test_help_is_reachable_and_succeeds(flag):
    """There was no --help at all; asking for it hit the unknown-verb `die`."""
    proc = run(flag)
    assert proc.returncode == 0, f"{flag} must succeed"
    assert "A VERB IS REQUIRED" in proc.stdout


def test_an_unknown_verb_still_fails_loudly():
    proc = run("definitely-not-a-verb")
    assert proc.returncode != 0
    assert "unknown verb" in proc.stderr


def test_the_beat_still_has_its_verb():
    """metabolize.sh:115 is the only estate caller and passes `backup` explicitly.

    Asserted against the source rather than by running a backup: if that call ever loses its verb,
    the beat would start failing at exit 2, and this names why.
    """
    beat = (ROOT / "scripts" / "metabolize.sh").read_text()
    assert "arca.sh" in beat
    assert 'arca.sh" backup' in beat, "the beat's arca call lost its explicit verb — it would now refuse"
