from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "op-service-account.sh"


def test_op_service_account_remove_receipts_secret_file_deletion() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "secret_file_removal_receipt" in text
    assert "secret-removals.jsonl" in text
    assert "credential-file-removal" in text
    assert "raw 1Password service-account token is not archived" in text
    assert "receipt excludes token, content, and raw path" in text
    assert 'remove_secret_file "$SA_FILE" || exit 1' in text
    assert text.index('receipt_file="$(secret_file_removal_receipt "$path")"') < text.index('rm -f -- "$path"')
