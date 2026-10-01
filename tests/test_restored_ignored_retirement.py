import importlib.util
import subprocess
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "restored_retirement", Path(__file__).parents[1] / "scripts/retire-restored-ignored-payload.py"
)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_byte_mode_and_extra_file_drift_fail_closed(tmp_path):
    payload = tmp_path / "payload"
    payload.mkdir()
    item = payload / "state"
    item.write_text("original")
    expected = adapter.inventory(payload)
    adapter.verify_tree(payload, expected)
    item.write_text("changed")
    with pytest.raises(ValueError, match="drift"):
        adapter.verify_tree(payload, expected)
    item.write_text("original")
    item.chmod(0o600)
    with pytest.raises(ValueError, match="drift"):
        adapter.verify_tree(payload, expected)
    item.chmod(expected["state"]["mode"])
    (payload / "new").write_text("uncaptured")
    with pytest.raises(ValueError, match="drift"):
        adapter.verify_tree(payload, expected)


@pytest.mark.parametrize("name,type_", [("../escape", tarfile.REGTYPE), ("source/link", tarfile.SYMTYPE)])
def test_unsafe_archive_is_rejected(tmp_path, name, type_):
    archive_path = tmp_path / "snapshot.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo(name)
        member.type = type_
        member.linkname = "/outside"
        archive.addfile(member)
    with pytest.raises(ValueError, match="archive"):
        adapter.restore(archive_path, tmp_path / "restore", {})
    assert not (tmp_path / "escape").exists()


def test_payload_selection_never_includes_tracked_parent(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("__pycache__/\n.capsule/\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "tracked.py").write_text("owned source")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore", "tests/tracked.py"], check=True)
    cache = tests / "__pycache__"
    cache.mkdir()
    (cache / "generated.pyc").write_bytes(b"cache")
    capsule = tmp_path / ".capsule"
    capsule.mkdir()
    (capsule / "receipt").write_text("private")
    assert adapter.ignored_directories(tmp_path) == [capsule, cache]
    assert (tests / "tracked.py").exists()
