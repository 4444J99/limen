"""A matching health response alone is never a singleton identity witness."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from limen.process_ownership import Process, assess
from limen.process_singletons import SERENA_TRAY_COMMAND, exact_loopback_listener, serena_tray_alive


@pytest.mark.parametrize(
    "output",
    [
        b"p99\nn127.0.0.1:24224\n",
        b"p10\nn*:24224\n",
        b"p10\nn[::1]:24224\n",
        b"p10\nn127.0.0.1:24224\nn127.0.0.1:24224\n",
        b"p10\np11\nn127.0.0.1:24224\n",
        b"p10\nn127.0.0.1:242240\n",
        b"\xff",
    ],
)
def test_listener_identity_failures(output):
    assert not exact_loopback_listener(output, 10)


def test_exact_listener():
    assert exact_loopback_listener(b"p10\nf4\nn127.0.0.1:24224\n", 10)


@pytest.mark.parametrize("body", [b'{"status":"dead"}', b'{"status":"alive","extra":1}', b"x" * 257])
def test_wrong_health_fails_closed(body):
    assert not _check(body, ["start", "start"])


def _check(body, identities):
    process = Process(10, 1, 501, "start", ("/vendor/bin/python", "-c", SERENA_TRAY_COMMAND))

    class Response:
        status = 200

        def read(self, limit):
            return body[:limit]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    values = iter(identities)
    listener = SimpleNamespace(returncode=0, stdout=b"p10\nf4\nn127.0.0.1:24224\n")
    with (
        patch("limen.process_singletons.subprocess.run", return_value=listener),
        patch(
            "limen.process_singletons.urllib.request.build_opener",
            return_value=SimpleNamespace(open=lambda *args, **kwargs: Response()),
        ),
    ):
        return serena_tray_alive(process, lambda pid: next(values))


def test_typed_health_and_stable_identity():
    assert _check(b'{"status":"alive"}', ["start", "start"])


def test_pid_reuse_after_health_fails_closed():
    assert not _check(b'{"status":"alive"}', ["start", "replacement"])


@pytest.fixture
def singleton(tmp_path, monkeypatch):
    host = Process(100, 1, 501, "host", ("/codex", "app-server"), cwd=tmp_path)
    peer = Process(101, 100, 501, "peer", ("/serena", "stdio"), cwd=tmp_path)
    tray = Process(10, 1, 501, "tray", ("/vendor/bin/python", "-c", SERENA_TRAY_COMMAND), cwd=tmp_path)
    processes = {p.pid: p for p in (host, peer, tray)}
    backend = {
        "service_id": "serena",
        "argv": list(peer.argv),
        "host_argv": list(host.argv),
        "config_home": str(tmp_path / "home"),
        "contract_sha256": "backend",
    }
    host.env["CODEX_HOME"] = backend["config_home"]
    helper = {
        "service_id": "serena/tray-manager",
        "argv": list(tray.argv),
        "host_argv": list(host.argv),
        "config_home": backend["config_home"],
        "contract_sha256": "helper",
        "singleton_pid": tray.pid,
        "singleton_identity": tray.started,
        "singleton_peer": {
            "pid": peer.pid,
            "identity": peer.started,
            "argv": list(peer.argv),
            "contract_sha256": "backend",
        },
    }
    monkeypatch.setattr("limen.process_singletons.serena_tray_alive", lambda p, i: True)

    def evaluate(**kwargs):
        return assess(
            processes,
            set(),
            tmp_path,
            "subject",
            contracts=[backend, helper],
            identity=lambda pid: processes[pid].started,
            **kwargs,
        )

    return processes, backend, helper, evaluate


def test_older_detached_tray_requires_verified_peer_not_pid_order(singleton):
    _, _, _, evaluate = singleton
    rows = {r["pid"]: r for r in evaluate()["processes"]}
    assert rows[10]["category"] == "shared_service"
    assert rows[10]["service_id"] == "serena/tray-manager"
    assert rows[10]["host_pid"] == 100


@pytest.mark.parametrize("mutation", ["peer_identity", "peer_argv", "peer_uid", "host", "home", "digest"])
def test_peer_binding_cannot_be_expanded(singleton, mutation):
    processes, _, helper, evaluate = singleton
    if mutation == "peer_identity":
        processes[101].started = "replacement"
    elif mutation == "peer_argv":
        processes[101].argv += ("--extra",)
    elif mutation == "peer_uid":
        processes[101].uid += 1
    elif mutation == "host":
        helper["host_argv"] = ["/other", "app-server"]
    elif mutation == "home":
        helper["config_home"] += "/other"
    else:
        helper["singleton_peer"]["contract_sha256"] = "other"
    rows = {r["pid"]: r for r in evaluate()["processes"]}
    assert rows[10]["category"] == "unknown"


def test_conflicting_peer_receipt_does_not_confer_shared_authority(singleton):
    processes, _, _, evaluate = singleton
    from limen.process_ownership import canonical_argv, digest

    claim = {
        "pid": 101,
        "process_identity": "peer",
        "argv_sha256": digest(canonical_argv(processes[101].argv)),
        "service_id": "wrong",
    }
    rows = {r["pid"]: r for r in evaluate(evidence=[claim])["processes"]}
    assert rows[101]["category"] == "unmeasured"
    assert rows[10]["category"] == "unknown"


@pytest.fixture
def vendor(tmp_path):
    from limen.process_services import _serena_singleton_contracts

    environment = tmp_path / "vendor"
    binary = environment / "bin/python"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"python")
    entry = binary.with_name("serena")
    entry.write_bytes(b"entrypoint")
    packages = environment / "lib/python3.13/site-packages"
    module = packages / "serena"
    module.mkdir(parents=True)
    dashboard = module / "dashboard.py"
    dashboard.write_text(SERENA_TRAY_COMMAND + '\nHOST = "127.0.0.1"\nPORT = SerenaPorts.TRAY_MANAGER_PORT\n')
    (module / "constants.py").write_text("TRAY_MANAGER_PORT = 0x5EA0\n")
    metadata = packages / "serena.dist-info/direct_url.json"
    metadata.parent.mkdir()
    metadata.write_text("{}")
    peer = Process(101, 100, 501, "peer", (str(binary), str(entry), "start-mcp-server"))
    tray = Process(10, 1, 501, "tray", (str(binary), "-c", SERENA_TRAY_COMMAND))
    processes = {p.pid: p for p in (peer, tray)}
    contract = {
        "service_id": "serena",
        "argv": list(peer.argv),
        "host_argv": ["/codex", "app-server"],
        "config_home": "home",
        "contract_sha256": "backend",
    }

    def derive():
        return _serena_singleton_contracts(processes, [contract], [(peer, metadata, "home")])

    return processes, dashboard, contract, derive


def test_vendor_candidate_binds_both_native_instances(vendor):
    _, _, _, derive = vendor
    candidates = derive()
    assert len(candidates) == 1
    assert candidates[0]["singleton_pid"] == 10
    assert candidates[0]["singleton_peer"]["pid"] == 101


@pytest.mark.parametrize("mutation", ["vendor", "extra_args", "other_environment", "symlink"])
def test_vendor_shape_and_environment_must_remain_exact(vendor, mutation):
    processes, dashboard, _, derive = vendor
    if mutation == "vendor":
        dashboard.write_text("unrelated code")
    elif mutation == "extra_args":
        processes[10].argv += ("--extra",)
    elif mutation == "other_environment":
        processes[10].argv = ("/another/bin/python", *processes[10].argv[1:])
    else:
        target = dashboard.with_name("original.py")
        dashboard.rename(target)
        dashboard.symlink_to(target)
    assert derive() == []
