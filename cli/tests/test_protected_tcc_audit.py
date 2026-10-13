"""Native application jobs must remain owned, private and inside existing bounds."""

import json
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest
from limen import protected_tcc_audit as native
from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def native_fixture(tmp_path):
    root = tmp_path / "source"
    shutil.copytree(ROOT / "cli/src/limen", root / "cli/src/limen", ignore=shutil.ignore_patterns("__pycache__"))
    scripts = root / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/protected-tcc-audit.py", scripts / "protected-tcc-audit.py")
    (scripts / "tcc-identity-audit.py").write_text(
        "import json,time,os\nfrom pathlib import Path\n"
        "root=Path(__file__).resolve().parents[1]\nmode=(root/'mode').read_text()\n"
        "if mode=='sleep':\n (root/'worker.pid').write_text(str(os.getpid()))\n time.sleep(60)\n"
        "if mode=='oversize': print('x'*1100000)\n"
        "else: print(json.dumps({'schema':'limen.tcc_identity_audit.v2','status':'blocked',"
        "'failures':['visible_app_management_path_client'],'measured':{'tcc_database':True}}))\n"
        "raise SystemExit(1)\n"
    )
    (root / "mode").write_text("finding")
    host = root / "FakeHost.app/Contents/MacOS/FakeHost"
    host.parent.mkdir(parents=True)
    host.write_text(
        f"#!{sys.executable}\nimport os,sys,subprocess,signal\nfrom pathlib import Path\n"
        f"Path({str(root / 'host.pid')!r}).write_text(str(os.getpid()))\n"
        "child=subprocess.Popen(sys.argv[3:],start_new_session=True)\n"
        "def stop(*_args):\n"
        " try: os.killpg(child.pid,signal.SIGTERM)\n"
        " except ProcessLookupError: pass\n"
        " # Return to the main wait; waiting again inside this signal handler deadlocks Popen's lock.\n"
        "signal.signal(signal.SIGTERM,stop)\nraise SystemExit(child.wait())\n"
    )
    host.chmod(0o755)
    opener = root / "open"
    opener.write_text(
        f"#!{sys.executable}\nimport sys,subprocess,json\nfrom pathlib import Path\n"
        "args=sys.argv[1:]; app=Path(args[args.index('-a')+1]); command=args[args.index('--args')+1:]\n"
        "out=open(args[args.index('--stdout')+1],'ab'); err=open(args[args.index('--stderr')+1],'ab')\n"
        "subprocess.Popen([str(app/'Contents/MacOS/FakeHost'),*command],start_new_session=True,"
        "stdin=subprocess.DEVNULL,stdout=out,stderr=err)\n"
        "# Deliberately return before the application completes, like LaunchServices.\n"
    )
    opener.chmod(0o755)
    scratch = root / "scratch"
    scratch.mkdir(mode=0o700)
    driver = scripts / "launch.py"
    driver.write_text(
        "import sys,json,os\nfrom pathlib import Path\n"
        f"sys.path.insert(0,{str(root / 'cli/src')!r})\n"
        "from limen.protected_tcc_audit import launch,NativeAuditError\n"
        "if os.getpgrp()!=os.getpid(): os.setsid()\n"
        "try:\n"
        f" code,out,err=launch(Path({str(host)!r}),Path({str(scripts / 'tcc-identity-audit.py')!r}),"
        f"opener={str(opener)!r},scratch_root=Path({str(scratch)!r}))\n"
        " print(json.dumps({'code':code,'stdout':out.decode(),'stderr':err.decode()}))\n"
        "except NativeAuditError as exc: print(json.dumps({'error':str(exc)}))\n"
    )
    return root, driver, scratch


def _gone(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
    return result.returncode != 0 or result.stdout.strip().startswith("Z")


def test_launcher_census_failure_keeps_cleanup_and_measurement_unverified(monkeypatch, capfd):
    monkeypatch.setattr(sys, "argv", ["audit", "--launch", "/host", "/implementation"])

    def unavailable(*_args):
        raise BoundedSubprocessError("unavailable", stage="rss_census")

    monkeypatch.setattr(native, "launch", unavailable)
    assert native.main() == 69
    sys.stdout.buffer.flush()
    payload = json.loads(capfd.readouterr().out)
    assert payload["failures"] == ["native_tcc_audit_unavailable"]
    assert payload["measured"]["native_job_cleanup"] is False
    assert payload["native_output_complete"] is False


def test_external_native_job_waits_for_result_and_verified_completion(native_fixture):
    root, driver, scratch = native_fixture
    result = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, timeout=12)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["code"] == 1, value
    assert json.loads(value["stdout"])["measured"]["tcc_database"] is True
    assert json.loads(value["stdout"])["native_output_complete"] is True
    assert _gone(int((root / "host.pid").read_text()))
    assert not list(scratch.iterdir())


def test_native_output_limit_remains_a_visible_failure_and_cleans_host(native_fixture):
    root, driver, scratch = native_fixture
    (root / "mode").write_text("oversize")
    result = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, timeout=12)
    value = json.loads(result.stdout)
    assert value["code"] == 69
    assert "native_tcc_audit_output" in value["stdout"]
    assert json.loads(value["stdout"])["native_output_complete"] is False
    assert _gone(int((root / "host.pid").read_text()))
    assert not list(scratch.iterdir())


def test_requester_cancellation_stops_only_its_owned_native_job(native_fixture):
    root, driver, scratch = native_fixture
    (root / "mode").write_text("sleep")
    parent = subprocess.Popen([sys.executable, str(driver)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while not (root / "worker.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (root / "worker.pid").exists(), [p.read_text() for p in scratch.glob("*/host.stderr")]
        worker = int((root / "worker.pid").read_text())
        host = int((root / "host.pid").read_text())
        parent.send_signal(signal.SIGTERM)
        out, err = parent.communicate(timeout=5)
        assert "native_audit_cancelled" in out, err
        assert _gone(host), [p.read_text() for p in scratch.glob("*/cleanup.json")]
        assert _gone(worker)
        assert not list(scratch.iterdir())
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)


def test_requester_loss_cannot_leave_the_native_worker_running(native_fixture):
    root, driver, _scratch = native_fixture
    (root / "mode").write_text("sleep")
    parent = subprocess.Popen([sys.executable, str(driver)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while not (root / "worker.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert (root / "worker.pid").exists()
        worker = int((root / "worker.pid").read_text())
        host = int((root / "host.pid").read_text())
        parent.kill()
        parent.wait(timeout=3)
        deadline = time.monotonic() + 4
        while (not _gone(host) or not _gone(worker)) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _gone(host) and _gone(worker)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)


def test_forged_claim_cannot_signal_a_foreign_process(native_fixture):
    root, driver, scratch = native_fixture
    victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        opener = root / "open"
        opener.write_text(
            f"#!{sys.executable}\nimport sys,json,os\nfrom pathlib import Path\n"
            f"sys.path.insert(0,{str(root / 'cli/src')!r})\n"
            "from limen.host_admission import process_identity\n"
            "request=Path(sys.argv[-1]); data=json.loads(request.read_text())\n"
            f"pid={victim.pid}\n"
            "claim={'nonce':data['nonce'],'host_pid':pid,'host_identity':process_identity(pid),"
            "'receiver_pid':pid,'receiver_identity':process_identity(pid),'host_verified':True}\n"
            "fd=os.open(request.parent/'bootstrap.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)\n"
            "with os.fdopen(fd,'w') as stream: json.dump(claim,stream)\n"
        )
        driver.write_text(driver.read_text().replace("opener=", "budget_seconds=.5,opener="))
        result = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, timeout=5)
        assert "native_audit_claim_unmeasured" in result.stdout, result.stderr
        assert victim.poll() is None
        evidence = list(scratch.glob("*/cleanup.json"))
        assert evidence and json.loads(evidence[0].read_text())["verified_claim"] is False
    finally:
        victim.terminate()
        victim.wait(timeout=3)


def test_native_evidence_rejects_symlinks_and_nonprivate_files(tmp_path):
    value = tmp_path / "value"
    value.write_bytes(b"{}")
    value.chmod(0o644)
    with pytest.raises(native.NativeAuditError):
        native._read(value, 100)
    value.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(value)
    with pytest.raises(OSError):
        native._read(link, 100)


@pytest.mark.parametrize("extra,kind", [(536870913, "resource"), (-1, "unavailable")])
def test_external_native_rss_is_counted_and_unknown_census_fails_closed(tmp_path, extra, kind):
    with pytest.raises(BoundedSubprocessError) as raised:
        run_bounded_subprocess(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path,
            timeout_seconds=2,
            stdout_ceiling=100,
            stderr_ceiling=100,
            rss_ceiling=536870912,
            additional_rss=lambda: extra,
        )
    assert raised.value.kind == kind
    assert raised.value.root_reaped is True


def test_wrong_implementation_and_extended_budget_are_rejected_before_launch(tmp_path):
    with pytest.raises(native.NativeAuditError, match="implementation_invalid"):
        native.launch(tmp_path / "host", tmp_path / "foreign.py")
    with pytest.raises(native.NativeAuditError, match="budget_invalid"):
        native.launch(tmp_path / "host", ROOT / "scripts/tcc-identity-audit.py", budget_seconds=30)


def test_missing_birth_census_cannot_be_reported_as_process_exit(monkeypatch):
    monkeypatch.setattr(native, "_identity", lambda _pid: None)
    monkeypatch.setattr(native.os, "kill", lambda _pid, _sig: None)
    with pytest.raises(native.NativeAuditError, match="identity_unmeasured"):
        native._alive(12345, "known-birth")


def test_native_import_hang_is_owned_and_cancelled_before_probe_work(native_fixture):
    root, driver, scratch = native_fixture
    module = root / "cli/src/limen/protected_tcc_audit.py"
    module.write_text(
        module.read_text().replace(
            "import ctypes", "import sys,time\nif '--job' in sys.argv: time.sleep(60)\nimport ctypes", 1
        )
    )
    driver.write_text(driver.read_text().replace("opener=", "budget_seconds=2,opener="))
    started = time.monotonic()
    result = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True, timeout=5)
    assert time.monotonic() - started < 4
    assert "native_audit_deadline" in result.stdout, result.stderr
    assert _gone(int((root / "host.pid").read_text()))
    assert not (root / "worker.pid").exists()
    assert not list(scratch.iterdir())


def test_reused_pid_is_not_the_owned_process(monkeypatch):
    monkeypatch.setattr(native, "_identity", lambda _pid: "different-birth")
    assert native._alive(12345, "known-birth") is False


def test_darwin_command_decoder_keeps_exact_arguments_and_empty_values():
    raw = struct.pack("=i", 4) + b"/executable\0\0\0/host with spaces\0run\0\0/job/request.json\0ENV=value\0"
    assert native._darwin_argv(raw) == ["/host with spaces", "run", "", "/job/request.json"]


@pytest.mark.parametrize("raw", [b"", struct.pack("=i", 513) + b"x\0", struct.pack("=i", 2) + b"x\0\0one\0"])
def test_darwin_incomplete_command_census_fails_closed(raw):
    with pytest.raises(native.NativeAuditError, match="command_unmeasured"):
        native._darwin_argv(raw)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin native process ABI")
def test_native_process_inspection_never_spawns_ps_into_measured_group(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("inspection spawned a child in the measured group")

    monkeypatch.setattr(native.subprocess, "run", forbidden)
    assert native._identity(native.os.getpid()).startswith("darwin-proc-start:")
    parent, arguments = native._process_details(native.os.getpid())
    assert parent == native.os.getppid()
    assert arguments and any("python" in argument.lower() for argument in arguments)
