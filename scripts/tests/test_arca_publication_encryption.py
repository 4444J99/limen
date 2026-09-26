"""Native envelope tests: these do not mock the publication encryption boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "arca_native_publication", Path(__file__).parents[1] / "arca-release-assets.py"
)
assert SPEC and SPEC.loader
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)


@pytest.fixture(scope="module")
def encrypted(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-arca")
    plain = root / "plain"
    plain.write_bytes(b"private fixture content\n")
    catalog = root / "catalog.gpg"
    payload = root / "payload.gpg"
    # Real public-key encryption with the repository's pinned recipient. No
    # private key, account, credential unlock, network, or remote mutation.
    assets.PRIVATE._encrypt_file(plain, catalog)
    assets.PRIVATE._encrypt_file(plain, payload)
    return catalog, payload


def test_native_envelopes_pass_without_a_private_key(encrypted):
    catalog, payload = encrypted
    batch, _, _ = assets._preflight(catalog, [payload])
    assets._verify_encryption(batch)


@pytest.mark.parametrize("body", [b"private plaintext", b"Salted__not encrypted", b"\xc1\x01\x00"])
def test_renamed_plaintext_and_forged_headers_never_reach_github(tmp_path, encrypted, monkeypatch, body):
    catalog, _ = encrypted
    payload = tmp_path / "secret.enc"
    payload.write_bytes(body)
    monkeypatch.setattr(assets, "_canonical_repository", lambda *_: pytest.fail("remote lookup before proof"))
    monkeypatch.setattr(assets, "_run", lambda *_a, **_k: pytest.fail("remote write before proof"))
    with pytest.raises(assets.AssetError, match="verified pinned-recipient encryption"):
        assets.publish("owner/private", catalog, [payload], apply=True)


def test_valid_envelope_with_plaintext_suffix_is_rejected(tmp_path, encrypted):
    catalog, payload = encrypted
    tainted = tmp_path / "tainted.gpg"
    tainted.write_bytes(payload.read_bytes() + b"private trailing data")
    batch, _, _ = assets._preflight(catalog, [tainted])
    with pytest.raises(assets.AssetError, match="verified pinned-recipient encryption"):
        assets._verify_encryption(batch)


def test_wrong_recipient_fails_closed(encrypted, monkeypatch):
    catalog, payload = encrypted
    monkeypatch.setattr(assets.PRIVATE, "_ciphertext_recipient_keyids", lambda _path: {"0000000000000000"})
    batch, _, _ = assets._preflight(catalog, [payload])
    with pytest.raises(assets.AssetError, match="verified pinned-recipient encryption"):
        assets._verify_encryption(batch)


def test_unavailable_native_verifier_fails_closed(encrypted, monkeypatch):
    def unavailable(*_args):
        raise assets.PRIVATE.VaultError("unavailable")

    catalog, payload = encrypted
    monkeypatch.setattr(assets.PRIVATE, "_ciphertext_failures", unavailable)
    batch, _, _ = assets._preflight(catalog, [payload])
    with pytest.raises(assets.AssetError, match="verification unavailable"):
        assets._verify_encryption(batch)


def test_source_drift_after_preflight_fails(tmp_path, encrypted):
    catalog, payload = encrypted
    changed = tmp_path / "changed.gpg"
    changed.write_bytes(payload.read_bytes())
    batch, _, _ = assets._preflight(catalog, [changed])
    changed.write_bytes(b"plaintext replacement")
    with pytest.raises(assets.AssetError, match="verified pinned-recipient encryption"):
        assets._verify_encryption(batch)
