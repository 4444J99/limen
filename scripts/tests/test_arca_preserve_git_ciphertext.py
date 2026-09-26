from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "arca-preserve-git-ciphertext.py"
SPEC = importlib.util.spec_from_file_location("arca_preserve_git_ciphertext", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
preserve = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preserve)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def local_divergence(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(bare)], check=True, capture_output=True)
    root = tmp_path / "arca"
    subprocess.run(["git", "init", "--initial-branch=main", str(root)], check=True, capture_output=True)
    git(root, "config", "user.name", "ARCA test")
    git(root, "config", "user.email", "arca-test@localhost")
    git(root, "remote", "add", "origin", str(bare))
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "base")
    git(root, "push", "-u", "origin", "main")
    (root / "one.tar.enc").write_bytes(b"Salted__first ciphertext")
    (root / "two.tar.enc.part.aa").write_bytes(b"second ciphertext part")
    git(root, "add", "one.tar.enc", "two.tar.enc.part.aa")
    git(root, "commit", "-m", "local ciphertext")
    git(root, "fetch", "origin", "main")
    return root


def test_catalog_covers_local_only_ciphertext_and_publishes_neutral_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = local_divergence(tmp_path)

    def encrypt(source: Path, destination: Path) -> None:
        destination.write_bytes(b"\xc1\x01\x00ENCRYPTED-CATALOG" + source.read_bytes())

    published: dict[str, object] = {}

    def fake_publish(repo: str, catalog: Path, objects: list[Path], *, apply: bool, **_kwargs) -> dict[str, object]:
        published.update(repo=repo, count=len(objects), apply=apply, catalog=catalog)
        return {"state": "planned", "asset_count": len(objects) + 1}

    monkeypatch.setattr(preserve.PRIVATE, "_encrypt_file", encrypt)
    monkeypatch.setattr(preserve.PUBLISHER, "publish", fake_publish)
    catalog = tmp_path / "private" / "catalog.gpg"
    result = preserve.preserve(root, "owner/private-arca", output=catalog)
    assert result["files"] == 2
    assert result["bytes"] == len(b"Salted__first ciphertext") + len(b"second ciphertext part")
    assert published["count"] == 2
    assert published["apply"] is False
    assert catalog.stat().st_mode & 0o777 == 0o600
    assert "one.tar.enc" not in str(result)
    assert "two.tar.enc" not in str(result)
    private_catalog = json.loads(catalog.read_bytes()[len(b"\xc1\x01\x00ENCRYPTED-CATALOG") :])
    assert private_catalog["git_closure_scope"] == "origin-main-excluded-to-head"
    metadata = private_catalog["git_metadata_objects"]
    assert {row["type"] for row in metadata} >= {"commit", "tree"}
    assert all(
        preserve._git_object_oid(
            row["type"],
            base64.b64decode(row["raw_b64"]),
            private_catalog["git_object_format"],
        )
        == row["oid"]
        for row in metadata
    )


def test_plaintext_manifest_is_embedded_only_inside_the_encrypted_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = local_divergence(tmp_path)
    secret_name = "private-store-name"
    (root / "manifest.json").write_text('{"private_store":"' + secret_name + '"}', encoding="utf-8")
    git(root, "add", "manifest.json")
    git(root, "commit", "-m", "metadata")

    def encrypt(source: Path, destination: Path) -> None:
        destination.write_bytes(b"\xc1\x01\x00ENCRYPTED-CATALOG" + source.read_bytes())

    published: list[Path] = []
    monkeypatch.setattr(preserve.PRIVATE, "_encrypt_file", encrypt)
    monkeypatch.setattr(
        preserve.PUBLISHER,
        "publish",
        lambda _repo, catalog, objects, **_k: published.extend(objects) or {"state": "planned"},
    )
    catalog = tmp_path / "private" / "catalog.gpg"
    result = preserve.preserve(root, "owner/private-arca", output=catalog)
    assert result["files"] == 2
    assert len(published) == 2  # manifest bytes are encrypted inside catalog, never an asset
    assert secret_name.encode() not in str(result).encode()
    private_catalog = json.loads(catalog.read_bytes()[len(b"\xc1\x01\x00ENCRYPTED-CATALOG") :])
    assert base64.b64decode(private_catalog["legacy_manifest_json_b64"]) == (root / "manifest.json").read_bytes()
    assert secret_name not in str(result)


def test_unexpected_plaintext_blob_blocks_partial_preservation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = local_divergence(tmp_path)
    (root / "notes.md").write_text("private data", encoding="utf-8")
    git(root, "add", "notes.md")
    git(root, "commit", "-m", "notes")
    monkeypatch.setattr(preserve.PRIVATE, "_encrypt_file", lambda *_: None)
    monkeypatch.setattr(
        preserve.PUBLISHER,
        "publish",
        lambda *_a, **_k: pytest.fail("must not publish partial custody"),
    )
    with pytest.raises(preserve.PreserveError, match="unsupported non-ciphertext"):
        preserve.preserve(root, "owner/private-arca", output=tmp_path / "private" / "catalog.gpg")


def test_isolated_reconstruction_matches_exact_original_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = local_divergence(tmp_path)
    prefix = b"\xc1\x01\x00ENCRYPTED-CATALOG"

    def encrypt(source: Path, destination: Path) -> None:
        destination.write_bytes(prefix + source.read_bytes())

    def decrypt(source: Path, destination: Path) -> None:
        ciphertext = source.read_bytes()
        assert ciphertext.startswith(prefix)
        destination.write_bytes(ciphertext[len(prefix) :])

    monkeypatch.setattr(preserve.PRIVATE, "_encrypt_file", encrypt)
    monkeypatch.setattr(preserve.PRIVATE, "_decrypt_file", decrypt)
    monkeypatch.setattr(preserve.PUBLISHER, "publish", lambda *_a, **_k: {"state": "planned"})
    catalog = tmp_path / "private" / "catalog.gpg"
    preserve.preserve(root, "owner/private-arca", output=catalog)
    private = json.loads(catalog.read_bytes()[len(prefix) :])
    assets = tmp_path / "assets"
    assets.mkdir()
    for row in private["entries"]:
        envelope = row["transport"]
        (assets / f"object-{envelope['sha256']}.enc").write_bytes(prefix + (root / row["path"]).read_bytes())
    reconstructed = tmp_path / "reconstructed.git"
    receipt = preserve.reconstruct(catalog, assets, str(tmp_path / "origin.git"), reconstructed)
    original_head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    recovered_head = subprocess.check_output(
        ["git", "-C", str(reconstructed), "rev-parse", "refs/heads/recovered"],
        text=True,
    ).strip()
    assert receipt["state"] == "reconstructed"
    assert original_head == recovered_head == private["source_commit"]
    resumed = preserve.resume_existing(
        root,
        "owner/private-arca",
        catalog=catalog,
        expected_head=original_head,
        expected_catalog_sha256=preserve._sha256(catalog)[0],
        expected_files=2,
        expected_bytes=sum(row["bytes"] for row in private["entries"]),
    )
    assert resumed["state"] == "planned"
    # Historical unwrapped catalogs remain readable without migration.
    for row in private["entries"]:
        row.pop("transport")
        (assets / f"object-{row['sha256']}.enc").write_bytes((root / row["path"]).read_bytes())
    historical = tmp_path / "historical-catalog.gpg"
    historical.write_bytes(prefix + json.dumps(private).encode())
    assert (
        preserve.reconstruct(historical, assets, str(tmp_path / "origin.git"), tmp_path / "old.git")["state"]
        == "reconstructed"
    )
    private["entries"][0]["sha256"] = "../untrusted"
    bad_catalog = tmp_path / "bad-catalog.gpg"
    bad_catalog.write_bytes(prefix + json.dumps(private).encode())
    bad_destination = tmp_path / "bad-reconstruction.git"
    with pytest.raises(preserve.PreserveError, match="invalid blob identity"):
        preserve.reconstruct(bad_catalog, assets, str(tmp_path / "origin.git"), bad_destination)
    assert not bad_destination.exists()
