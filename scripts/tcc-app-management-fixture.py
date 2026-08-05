#!/usr/bin/env python3
"""Exercise App Management through renamed descendants of DomusAgentHost.

The fixture creates one uniquely named disposable application outside the host,
updates it through four renamed executable paths beneath ``ensure``, and then
deletes only that validated fixture through the same hosted boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "limen.tcc_app_management_fixture.v1"
FIXTURE_PREFIX = "LimenTCCFixture-"
RUNNER_LABELS = ("uvx-renamed", "node-renamed", "python-renamed", "portable-ruby-renamed")
RUNNER_SOURCE = r'''
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static const char *labels[] = {
    "uvx-renamed",
    "node-renamed",
    "python-renamed",
    "portable-ruby-renamed",
};

static int path_for(char *out, size_t size, const char *app, const char *suffix) {
    int written = snprintf(out, size, "%s/%s", app, suffix);
    return written > 0 && (size_t)written < size;
}

static int valid_label(const char *candidate) {
    size_t count = sizeof(labels) / sizeof(labels[0]);
    for (size_t i = 0; i < count; i++) {
        if (strcmp(candidate, labels[i]) == 0) return 1;
    }
    return 0;
}

static int validate(const char *app, const char *nonce) {
    const char *home = getenv("HOME");
    char prefix[PATH_MAX];
    char marker[PATH_MAX];
    char observed[128];
    if (!home || snprintf(prefix, sizeof(prefix), "%s/Applications/LimenTCCFixture-", home) <= 0) {
        return 0;
    }
    size_t app_length = strlen(app);
    if (strncmp(app, prefix, strlen(prefix)) != 0 || app_length < 4 ||
        strcmp(app + app_length - 4, ".app") != 0) {
        return 0;
    }
    if (!path_for(marker, sizeof(marker), app, "Contents/Resources/.limen-tcc-fixture")) {
        return 0;
    }
    FILE *stream = fopen(marker, "r");
    if (!stream) return 0;
    char *read_result = fgets(observed, sizeof(observed), stream);
    fclose(stream);
    if (!read_result) return 0;
    observed[strcspn(observed, "\r\n")] = '\0';
    return strcmp(observed, nonce) == 0;
}

static int update_fixture(const char *app, const char *label) {
    char target[PATH_MAX];
    char suffix[256];
    if (!valid_label(label) || snprintf(suffix, sizeof(suffix), "Contents/Resources/%s", label) <= 0 ||
        !path_for(target, sizeof(target), app, suffix)) {
        return 0;
    }
    FILE *stream = fopen(target, "w");
    if (!stream) return 0;
    int ok = fprintf(stream, "%s\n", label) > 0 && fclose(stream) == 0;
    return ok;
}

static int delete_fixture(const char *app) {
    char target[PATH_MAX];
    char suffix[256];
    size_t count = sizeof(labels) / sizeof(labels[0]);
    for (size_t i = 0; i < count; i++) {
        if (snprintf(suffix, sizeof(suffix), "Contents/Resources/%s", labels[i]) <= 0 ||
            !path_for(target, sizeof(target), app, suffix) || unlink(target) != 0) {
            return 0;
        }
    }
    const char *files[] = {
        "Contents/Resources/.limen-tcc-fixture",
        "Contents/Info.plist",
    };
    for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); i++) {
        if (!path_for(target, sizeof(target), app, files[i]) || unlink(target) != 0) return 0;
    }
    const char *directories[] = {"Contents/Resources", "Contents", ""};
    for (size_t i = 0; i < sizeof(directories) / sizeof(directories[0]); i++) {
        if (directories[i][0] == '\0') {
            if (rmdir(app) != 0) return 0;
        } else if (!path_for(target, sizeof(target), app, directories[i]) || rmdir(target) != 0) {
            return 0;
        }
    }
    return 1;
}

int main(int argc, char **argv) {
    if (argc != 5 || !validate(argv[2], argv[3])) return 64;
    if (strcmp(argv[1], "update") == 0) return update_fixture(argv[2], argv[4]) ? 0 : 1;
    if (strcmp(argv[1], "delete") == 0) return delete_fixture(argv[2]) ? 0 : 1;
    return 64;
}
'''


class FixtureError(RuntimeError):
    """The bounded fixture could not establish its acceptance result."""


def _fixture_path(home: Path) -> tuple[Path, str]:
    applications = home / "Applications"
    applications.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        nonce = secrets.token_hex(6)
        candidate = applications / f"{FIXTURE_PREFIX}{nonce}.app"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate, nonce
    raise FixtureError("could not allocate a unique disposable application")


def _create_fixture(home: Path) -> tuple[Path, str, str]:
    application, nonce = _fixture_path(home)
    contents = application / "Contents"
    resources = contents / "Resources"
    resources.mkdir(parents=True)
    bundle_id = f"org.organvm.limen.tcc-fixture.{nonce}"
    with (contents / "Info.plist").open("wb") as stream:
        plistlib.dump(
            {
                "CFBundleIdentifier": bundle_id,
                "CFBundleName": "Limen TCC Fixture",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": "1",
                "CFBundleVersion": "1",
            },
            stream,
        )
    (resources / ".limen-tcc-fixture").write_text(nonce + "\n", encoding="utf-8")
    return application, nonce, bundle_id


def _validate_fixture(application: Path, home: Path, nonce: str) -> None:
    expected_parent = (home / "Applications").resolve(strict=True)
    if application.parent.resolve(strict=True) != expected_parent:
        raise FixtureError("fixture escaped the user Applications directory")
    if not application.name.startswith(FIXTURE_PREFIX) or application.suffix != ".app":
        raise FixtureError("fixture name is outside the deletion contract")
    marker = application / "Contents/Resources/.limen-tcc-fixture"
    if marker.read_text(encoding="utf-8").strip() != nonce:
        raise FixtureError("fixture ownership marker is missing or mismatched")


def _run_hosted(
    host: Path,
    runner: Path,
    operation: str,
    application: Path,
    nonce: str,
    label: str,
) -> None:
    completed = subprocess.run(
        [
            str(host),
            "ensure",
            "--",
            str(runner),
            operation,
            str(application),
            nonce,
            label,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "hosted command failed").strip()
        raise FixtureError(f"{runner.name} failed: {detail[:200]}")


def exercise(home: Path, host: Path) -> dict[str, Any]:
    if not host.is_file() or not os.access(host, os.X_OK):
        raise FixtureError("domus-agent-host wrapper is unavailable")

    application, nonce, bundle_id = _create_fixture(home)
    runner_root = Path(tempfile.mkdtemp(prefix="limen-tcc-renamed-runners-"))
    runners: list[Path] = []
    try:
        source = runner_root / "fixture-runner.c"
        source.write_text(RUNNER_SOURCE, encoding="utf-8")
        compiler = shutil.which("clang") or shutil.which("cc")
        if compiler is None:
            raise FixtureError("a C compiler is required for renamed native fixtures")
        for label in RUNNER_LABELS:
            runner = runner_root / label
            compiled = subprocess.run(
                [compiler, "-Os", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(runner)],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if compiled.returncode != 0:
                detail = (compiled.stderr or compiled.stdout or "compiler failed").strip()
                raise FixtureError(f"renamed fixture compiler failed: {detail[:200]}")
            runners.append(runner)

        for runner in runners:
            _validate_fixture(application, home, nonce)
            _run_hosted(
                host,
                runner,
                "update",
                application,
                nonce,
                runner.name,
            )
            marker = application / "Contents/Resources" / runner.name
            if marker.read_text(encoding="utf-8").strip() != runner.name:
                raise FixtureError(f"{runner.name} did not update the fixture")

        _validate_fixture(application, home, nonce)
        _run_hosted(
            host,
            runners[-1],
            "delete",
            application,
            nonce,
            runners[-1].name,
        )
        if application.exists():
            raise FixtureError("hosted delete left the disposable application behind")
    finally:
        shutil.rmtree(runner_root)

    return {
        "schema": SCHEMA,
        "ok": True,
        "fixture_bundle_id": bundle_id,
        "fixture_deleted": True,
        "runner_labels": list(RUNNER_LABELS),
        "host_interface": "ensure",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="~/.local/bin/domus-agent-host",
        help="deployed Domus host wrapper",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
    host = Path(args.host).expanduser()
    try:
        result = exercise(home, host)
    except (FixtureError, OSError, subprocess.SubprocessError) as exc:
        result = {"schema": SCHEMA, "ok": False, "error": str(exc)}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("TCC App Management fixture: " + ("ok" if result["ok"] else "FAILED"))
        if not result["ok"]:
            print(f"  {result['error']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
