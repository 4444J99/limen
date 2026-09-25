from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "arca-release-assets.py"
SPEC = importlib.util.spec_from_file_location("arca_release_assets", MODULE_PATH)
assert SPEC and SPEC.loader
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)
PREFLIGHT_SPEC = importlib.util.spec_from_file_location(
    "preflight_arca_release_assets", MODULE_PATH.parent / "preflight-arca-release-assets.py"
)
assert PREFLIGHT_SPEC and PREFLIGHT_SPEC.loader
preflight = importlib.util.module_from_spec(PREFLIGHT_SPEC)
PREFLIGHT_SPEC.loader.exec_module(preflight)


def _ciphertexts(tmp_path: Path) -> tuple[Path, list[Path]]:
    catalog = tmp_path / "private-names.catalog.enc"
    catalog.write_bytes(b"Salted__opaque encrypted catalog")
    payload = tmp_path / "sensitive-source.tar.enc.part.aa"
    payload.write_bytes(b"opaque encrypted payload")
    return catalog, [payload]


def test_hydration_fetches_only_verified_ciphertext(tmp_path: Path, monkeypatch) -> None:
    catalog = b"opaque catalog ciphertext"
    payload = b"opaque object ciphertext"
    catalog_digest = hashlib.sha256(catalog).hexdigest()
    payload_digest = hashlib.sha256(payload).hexdigest()
    tag = f"arca-objects-{catalog_digest[:32]}"
    names = {f"catalog-{catalog_digest}.enc": catalog, f"object-{payload_digest}.enc": payload}
    destination = tmp_path / "private"
    destination.mkdir(mode=0o700)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {name: tag for name in names})
    monkeypatch.setattr(
        assets, "_release_asset_digests",
        lambda _repo, _tag: {name: (hashlib.sha256(data).hexdigest(), len(data)) for name, data in names.items()},
    )

    def download(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        name = args[args.index("--pattern") + 1]
        Path(args[args.index("--dir") + 1], name).write_bytes(names[name])
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(assets, "_run", download)
    result = assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [payload_digest], destination)
    assert result["state"] == "verified" and result["asset_count"] == 2
    assert sorted(path.read_bytes() for path in destination.glob("*.enc")) == sorted(names.values())
    assert assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [payload_digest], destination) == result
    with pytest.raises(assets.AssetError, match="identity"):
        assets.hydrate_ciphertext("owner/private-vault", 124, catalog_digest, [payload_digest], destination)
    with pytest.raises(assets.AssetError, match="identifiers"):
        assets.hydrate_ciphertext("owner/private-vault", 123, "../escape", [payload_digest], destination)
    (destination / f"object-{payload_digest}.enc").write_bytes(b"changed")
    with pytest.raises(assets.AssetError, match="differs"):
        assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [payload_digest], destination)


def test_hydration_rejects_incomplete_marker_and_unverified_bytes(tmp_path: Path, monkeypatch) -> None:
    catalog_digest = hashlib.sha256(b"catalog").hexdigest()
    payload_digest = hashlib.sha256(b"payload").hexdigest()
    tag = f"arca-objects-{catalog_digest[:32]}"
    catalog_name = f"catalog-{catalog_digest}.enc"
    object_name = f"object-{payload_digest}.enc"
    destination = tmp_path / "private"
    destination.mkdir(mode=0o700)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {object_name: tag})
    with pytest.raises(assets.AssetError, match="catalog marker"):
        assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [payload_digest], destination)
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {catalog_name: tag, object_name: tag})
    monkeypatch.setattr(assets, "_release_asset_digests", lambda _repo, _tag: {
        catalog_name: (catalog_digest, 7), object_name: ("0" * 64, 7)
    })
    with pytest.raises(assets.AssetError, match="digest"):
        assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [payload_digest], destination)
    destination.chmod(0o755)
    with pytest.raises(assets.AssetError, match="private directory"):
        assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [payload_digest], destination)


def test_hydration_limits_are_checked_before_download(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "private"
    destination.mkdir(mode=0o700)
    catalog_digest = "a" * 64
    object_digest = "b" * 64
    tag = f"arca-objects-{catalog_digest[:32]}"
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {
        f"catalog-{catalog_digest}.enc": tag,
        f"object-{object_digest}.enc": f"{tag}-part-0001",
    })
    monkeypatch.setattr(assets, "_release_asset_digests", lambda _repo, release: {
        (f"catalog-{catalog_digest}.enc" if release == tag else f"object-{object_digest}.enc"):
        (catalog_digest if release == tag else object_digest, 100)
    })
    monkeypatch.setattr(assets, "_run", lambda *_args, **_kwargs: pytest.fail("download started"))
    monkeypatch.setattr(assets, "MAX_HYDRATE_OBJECTS", 0)
    with pytest.raises(assets.AssetError, match="object limit"):
        assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [object_digest], destination)
    monkeypatch.setattr(assets, "MAX_HYDRATE_OBJECTS", 16)
    monkeypatch.setattr(assets, "MAX_HYDRATE_RELEASES", 1)
    with pytest.raises(assets.AssetError, match="release limit"):
        assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [object_digest], destination)
    monkeypatch.setattr(assets, "MAX_HYDRATE_RELEASES", 4)
    monkeypatch.setattr(assets, "MAX_HYDRATE_BYTES", 150)
    with pytest.raises(assets.AssetError, match="byte limit"):
        assets.hydrate_ciphertext("owner/private-vault", 123, catalog_digest, [object_digest], destination)
    assert not list(destination.iterdir())


def test_plan_is_neutral_and_has_no_remote_effects(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    monkeypatch.setattr(assets, "_run", lambda *_a, **_k: pytest.fail("dry run called GitHub"))
    result = assets.publish("owner/private-vault", catalog, objects, apply=False)
    assert result["state"] == "planned"
    assert result["asset_count"] == 2
    assert "sensitive-source" not in str(result)
    assert "private-names" not in str(result)


def test_publish_resumes_by_digest_and_verifies_every_readback(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    remote: dict[str, bytes] = {}
    calls: list[list[str]] = []
    authorized: list[str] = []

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "[]\n", "")
        if args[1:3] == ["release", "create"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "[]\n", "")
        if args[1:3] == ["release", "view"]:
            names = "\n".join(remote)
            return subprocess.CompletedProcess(args, 0, names, "")
        if args[1:3] == ["release", "upload"]:
            path = args[4]
            name = Path(path).name
            remote[name] = Path(path).read_bytes()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "download"]:
            name = args[args.index("--pattern") + 1]
            destination = Path(args[args.index("--dir") + 1]) / name
            destination.write_bytes(remote[name])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, _tag: bool(remote))
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_authorize_write", lambda repo: authorized.append(repo))
    result = assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert result["state"] == "verified"
    assert result["asset_count"] == 2
    assert len(remote) == 2
    assert authorized == ["owner/private-vault"] * 3
    assert all(name.startswith(("catalog-", "object-")) for name in remote)
    assert "sensitive-source" not in " ".join(" ".join(call) for call in calls)
    upload_count = sum(call[1:3] == ["release", "upload"] for call in calls)
    resumed = assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert resumed["state"] == "verified"
    assert sum(call[1:3] == ["release", "upload"] for call in calls) == upload_count


@pytest.mark.parametrize("release_limit,expected_groups", [(1000, [4, 1]), (2, [2, 2, 1])])
def test_small_objects_share_uploads_and_catalog_waits_for_readback(
    tmp_path: Path, monkeypatch, release_limit: int, expected_groups: list[int]
) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    monkeypatch.setattr(assets, "MAX_RELEASE_ASSETS", release_limit)
    for index in range(3):
        path = tmp_path / f"private-{index}.enc"
        path.write_bytes(f"opaque encrypted payload {index}".encode())
        objects.append(path)
    remote: dict[str, bytes] = {}
    uploads: list[list[str]] = []
    readbacks: list[str] = []
    download_calls: list[list[str]] = []
    authorized: list[str] = []

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if args[1:3] == ["release", "create"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "upload"]:
            paths = args[4:args.index("--repo")]
            uploads.append([Path(path).name for path in paths])
            if any(Path(path).name.startswith("catalog-") for path in paths):
                assert len(readbacks) == len(objects)
            for path in paths:
                remote[Path(path).name] = Path(path).read_bytes()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "download"]:
            download_calls.append(args)
            for position, value in enumerate(args):
                if value == "--pattern":
                    name = args[position + 1]
                    readbacks.append(name)
                    Path(args[args.index("--dir") + 1], name).write_bytes(remote[name])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, _tag: False)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_authorize_write", lambda repo: authorized.append(repo))
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {})
    assert assets.publish("owner/private-vault", catalog, objects, apply=True)["state"] == "verified"
    assert list(map(len, uploads)) == expected_groups
    assert len(download_calls) == len(expected_groups)
    assert len(authorized) == (3 if release_limit == 1000 else 6)


def test_partial_multi_object_upload_resumes_without_publishing_catalog(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    extra = tmp_path / "extra.enc"
    extra.write_bytes(b"second encrypted payload")
    objects.append(extra)
    remote: dict[str, bytes] = {}
    interrupt = True

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal interrupt
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if args[1:3] == ["release", "create"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "view"]:
            return subprocess.CompletedProcess(args, 0, "\n".join(remote), "")
        if args[1:3] == ["release", "upload"]:
            paths = args[4:args.index("--repo")]
            if interrupt:
                remote[Path(paths[0]).name] = Path(paths[0]).read_bytes()
                interrupt = False
                raise assets.AssetError("interrupted upload")
            for path in paths:
                remote[Path(path).name] = Path(path).read_bytes()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "download"]:
            for position, value in enumerate(args):
                if value == "--pattern":
                    name = args[position + 1]
                    Path(args[args.index("--dir") + 1], name).write_bytes(remote[name])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, _tag: bool(remote))
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_authorize_write", lambda _repo: None)
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {})
    with pytest.raises(assets.AssetError, match="interrupted upload"):
        assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert len(remote) == 1 and all(name.startswith("object-") for name in remote)
    assert assets.publish("owner/private-vault", catalog, objects, apply=True)["state"] == "verified"
    assert len(remote) == 3


def test_shard_failure_keeps_final_catalog_absent_and_resumes(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    extra = tmp_path / "extra.enc"
    extra.write_bytes(b"second encrypted payload")
    objects.append(extra)
    monkeypatch.setattr(assets, "MAX_RELEASE_ASSETS", 1)
    target_tag = assets._preflight(catalog, objects)[1]
    remote: dict[str, dict[str, bytes]] = {}
    fail_second_shard = True

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal fail_second_shard
        if args[1:3] == ["release", "create"]:
            remote[args[3]] = {}
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "view"]:
            return subprocess.CompletedProcess(args, 0, "\n".join(remote[args[3]]), "")
        if args[1:3] == ["release", "upload"]:
            tag = args[3]
            if tag.endswith("part-0002") and fail_second_shard:
                fail_second_shard = False
                raise assets.AssetError("second shard interrupted")
            for path in args[4:args.index("--repo")]:
                remote[tag][Path(path).name] = Path(path).read_bytes()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "download"]:
            tag = args[3]
            for position, value in enumerate(args):
                if value == "--pattern":
                    name = args[position + 1]
                    Path(args[args.index("--dir") + 1], name).write_bytes(remote[tag][name])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, tag: tag in remote)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_authorize_write", lambda _repo: None)
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {
        name: tag for tag, files in remote.items() for name in files
    })
    with pytest.raises(assets.AssetError, match="second shard interrupted"):
        assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert target_tag not in remote
    assert len(remote[f"{target_tag}-part-0001"]) == 1
    assert assets.publish("owner/private-vault", catalog, objects, apply=True)["state"] == "verified"
    assert len(remote[target_tag]) == 1


def test_interrupted_batch_resumes_without_replacing_verified_assets(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    remote: dict[str, bytes] = {}
    fail_payload_once = True

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal fail_payload_once
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "[]\n", "")
        if args[1:3] == ["release", "create"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "view"]:
            return subprocess.CompletedProcess(args, 0, "\n".join(remote), "")
        if args[1:3] == ["release", "upload"]:
            path = args[4]
            name = Path(path).name
            if name.startswith("object-") and fail_payload_once:
                fail_payload_once = False
                raise assets.AssetError("injected upload interruption; source ciphertext retained")
            remote[name] = Path(path).read_bytes()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "download"]:
            name = args[args.index("--pattern") + 1]
            Path(args[args.index("--dir") + 1], name).write_bytes(remote[name])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, _tag: bool(remote))
    monkeypatch.setattr(assets, "_authorize_write", lambda _repo: None)
    with pytest.raises(assets.AssetError, match="source ciphertext retained"):
        assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert remote == {}  # no catalog is visible before the first payload readback
    assert objects[0].exists()

    result = assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert result["state"] == "verified"
    assert len(remote) == 2


def test_unchanged_objects_are_reused_from_earlier_release(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    files, _tag, _size = assets._preflight(catalog, objects)
    old_tag = "arca-objects-" + "a" * 32
    prior = {files[0][1]: objects[0].read_bytes()}
    current: dict[str, bytes] = {}
    uploaded: list[str] = []

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if args[1:3] == ["release", "create"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "view"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "upload"]:
            path = args[4]
            name = Path(path).name
            current[name] = Path(path).read_bytes()
            uploaded.append(name)
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "download"]:
            tag = args[3]
            name = args[args.index("--pattern") + 1]
            source = prior[name] if tag == old_tag else current[name]
            Path(args[args.index("--dir") + 1], name).write_bytes(source)
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, _tag: False)
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {files[0][1]: old_tag})
    monkeypatch.setattr(assets, "_authorize_write", lambda _repo: None)
    result = assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert result["state"] == "verified"
    assert uploaded == [files[1][1]]  # only the new encrypted catalog; the old object was read back in place


def test_existing_asset_requires_uploaded_server_digest_and_size(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    files, _tag, _size = assets._preflight(catalog, objects)
    object_name = files[0][1]
    remote = {object_name: objects[0].read_bytes()}
    downloads: list[str] = []

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["gh", "api"] and "/releases/tags/" in args[2]:
            rows = [{"name": name, "digest": "sha256:" + hashlib.sha256(value).hexdigest(),
                     "size": len(value), "state": "uploaded"} for name, value in remote.items()]
            return subprocess.CompletedProcess(args, 0, json.dumps({"assets": rows}), "")
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if args[1:3] == ["release", "view"]:
            return subprocess.CompletedProcess(args, 0, "\n".join(remote), "")
        if args[1:3] == ["release", "upload"]:
            path = Path(args[4])
            remote[path.name] = path.read_bytes()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ["release", "download"]:
            name = args[args.index("--pattern") + 1]
            downloads.append(name)
            Path(args[args.index("--dir") + 1], name).write_bytes(remote[name])
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, _tag: True)
    monkeypatch.setattr(assets, "_existing_assets", lambda _repo: {})
    monkeypatch.setattr(assets, "_authorize_write", lambda _repo: None)
    result = assets.publish("owner/private-vault", catalog, objects, apply=True,
                            verify_existing_by_server_digest=True)
    assert result["state"] == "verified"
    assert downloads == [files[1][1]]  # new catalog still receives full readback

    remote[object_name] = b"corrupt"
    with pytest.raises(assets.AssetError, match="no matching server digest"):
        assets.publish("owner/private-vault", catalog, objects, apply=True,
                       verify_existing_by_server_digest=True)


def test_wrong_readback_digest_fails_without_mutating_source(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    source_bytes = objects[0].read_bytes()

    def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "[]\n", "")
        if args[1:3] == ["release", "download"]:
            name = args[args.index("--pattern") + 1]
            Path(args[args.index("--dir") + 1], name).write_bytes(b"wrong bytes")
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(assets, "_run", fake_run)
    monkeypatch.setattr(assets, "_release_exists", lambda _repo, _tag: True)
    monkeypatch.setattr(assets, "_canonical_repository", lambda _repo: (77123, "owner/private-vault", "main"))
    monkeypatch.setattr(assets, "_authorize_write", lambda _repo: None)
    with pytest.raises(assets.AssetError, match="readback digest mismatch"):
        assets.publish("owner/private-vault", catalog, objects, apply=True)
    assert objects[0].read_bytes() == source_bytes


def test_rejects_plaintext_named_source_and_assets_over_limit(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    plain = tmp_path / "payload.json"
    plain.write_text("not encrypted")
    with pytest.raises(assets.AssetError, match="identify encrypted"):
        assets.publish("owner/private-vault", catalog, [plain], apply=False)

    monkeypatch.setattr(assets, "MAX_ASSET_BYTES", 10)
    with pytest.raises(assets.AssetError, match="under-2-GiB"):
        assets.publish("owner/private-vault", catalog, objects, apply=False)

    monkeypatch.setattr(assets, "MAX_ASSET_BYTES", 2 * 1024**3 - 1)
    with pytest.raises(assets.AssetError, match="changed after encrypted catalog"):
        assets.publish(
            "owner/private-vault",
            catalog,
            objects,
            apply=False,
            expected_digests={objects[0]: "0" * 64},
        )


def test_plans_shards_above_release_asset_limit_before_remote_effects(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    extra = tmp_path / "extra.enc"
    extra.write_bytes(b"opaque encrypted extra")
    monkeypatch.setattr(assets, "MAX_RELEASE_ASSETS", 2)
    monkeypatch.setattr(assets, "_run", lambda *_a, **_k: pytest.fail("oversized cohort contacted GitHub"))
    result = assets.publish("owner/private-vault", catalog, [*objects, extra], apply=False)
    assert result["release_count"] == 2


def test_object_directory_and_prior_shard_assets_are_discoverable(tmp_path: Path, monkeypatch) -> None:
    directory = tmp_path / "objects"
    directory.mkdir()
    second = directory / "b.gpg"
    first = directory / "a.gpg"
    second.write_bytes(b"cipher B")
    first.write_bytes(b"cipher A")
    assert assets._objects_from_dir(directory) == [first, second]
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(assets.AssetError, match="real directory"):
        assets._objects_from_dir(alias)

    shard = "arca-objects-" + "a" * 32 + "-part-0001"
    base = "arca-objects-" + "b" * 32
    response = f"{shard}\tobject-one.enc\n{base}\tobject-two.enc\nnot-arca\tobject-three.enc\n"
    monkeypatch.setattr(assets, "_run", lambda *_a, **_k: subprocess.CompletedProcess([], 0, response, ""))
    assert assets._existing_assets("owner/private-vault") == {
        "object-one.enc": shard, "object-two.enc": base
    }


def test_failed_github_command_reports_neutral_error_category(monkeypatch) -> None:
    def fail(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, "", "private path: /Users/name/file; HTTP 422 Validation Failed")

    monkeypatch.setattr(assets.subprocess, "run", fail)
    with pytest.raises(assets.AssetError, match=r"HTTP 422\); source ciphertext retained") as error:
        assets._run(["gh", "release", "upload", "tag", "opaque.enc"])
    assert "/Users/name" not in str(error.value)
    assert assets._safe_failure_reason("HTTP 403: You have exceeded a secondary rate limit", 1) == "secondary rate limit"
    assert assets._safe_failure_reason("HTTP 403: Resource not accessible by integration", 1) == "permission denied"


def test_upload_batch_size_is_bounded_before_remote_effects(tmp_path: Path, monkeypatch) -> None:
    catalog, objects = _ciphertexts(tmp_path)
    monkeypatch.setattr(assets, "MAX_UPLOAD_FILES", 0)
    monkeypatch.setattr(assets, "_run", lambda *_a, **_k: pytest.fail("invalid batch contacted GitHub"))
    with pytest.raises(assets.AssetError, match="between 1 and 16"):
        assets.publish("owner/private-vault", catalog, objects, apply=True)


def test_repository_alias_must_resolve_to_one_private_immutable_identity(monkeypatch) -> None:
    responses = iter(
        [
            '{"id":77123,"full_name":"old-owner/vault","private":true,"default_branch":"main"}',
            '{"id":77123,"full_name":"new-owner/vault","private":true,"default_branch":"main"}',
        ]
    )
    monkeypatch.setattr(
        assets,
        "_run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, next(responses), ""),
    )
    with pytest.raises(assets.AssetError, match="identity changed"):
        assets._canonical_repository("old-owner/vault")


def test_preflight_resolves_renamed_repository_by_stable_id(monkeypatch) -> None:
    responses = iter(
        [
            '{"id":77123,"full_name":"new-owner/vault","private":true,"default_branch":"main"}',
            '{"id":77123,"full_name":"new-owner/vault","private":true,"default_branch":"main"}',
        ]
    )
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, next(responses), ""),
    )
    assert preflight.inspect_repository("old-owner/vault") == (77123, "new-owner/vault", "main")
