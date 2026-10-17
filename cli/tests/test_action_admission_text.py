"""Read-only argument text must not become a heavy executable invocation."""

import pytest

from limen.action_admission import classify_bash


@pytest.mark.parametrize(
    "command",
    [
        "cat scripts/verify-scoped.sh",
        "rg -n 'pytest cli/tests' docs",
        "sed -n '1,110p' scripts/verify-scoped.sh",
        "printf '%s\\n' 'npm run build'",
        "echo 'verify-whole.sh is documentation'",
        "head -n 20 scripts/verify-scoped.sh",
    ],
)
def test_heavy_word_readers_are_observations(command: str) -> None:
    assert classify_bash(command).category == "observe"


@pytest.mark.parametrize(
    "command",
    [
        "bash scripts/verify-scoped.sh",
        "python -m pytest cli/tests",
        "rg --pre verify-scoped.sh text",
        "sed -n 'w /tmp/verify-scoped.sh' input",
        "sed -n 1p -e 'w /tmp/verify-scoped.sh' input",
        "cat scripts/verify-scoped.sh > result",
        "printf '%s' verify-scoped.sh | sh",
    ],
)
def test_heavy_word_readers_do_not_hide_executions_or_writes(command: str) -> None:
    assert classify_bash(command).category != "observe"
