from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "claude-fleet-auth-probe.sh"


def test_claude_fleet_auth_probe_records_redacted_secret_temp_cleanup() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "secret_temp_receipt" in text
    assert ".limen-private" in text
    assert "secret-temp-cleanup" in text
    assert "raw secret-bearing Claude temp config is not archived" in text
    assert "receipt excludes token, content, filenames, and raw path" in text
    assert 'TOK_TO_REDACT="$TOK"' in text
    assert '.replace(os.environ["TOK_TO_REDACT"], "[REDACTED_TOKEN]")' in text
    assert 'rm -rf -- "$tmpcfg"' in text
    assert text.index('receipt_file="$(secret_temp_receipt "$tmpcfg")"') < text.index('rm -rf -- "$tmpcfg"')
