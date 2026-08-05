"""Live readiness checks for explicit task execution requirements.

Completion predicates answer whether work is done.  Execution requirements answer whether the
current control host can start that work at all.  Keeping those contracts separate lets handoff
and every dispatcher use the same live, read-only gate without interpreting task titles, labels,
ids, or prose.

Legacy tasks have no ``execution_requirements`` field and remain ready by default.  Once a task
declares requirements, malformed or unsupported entries fail closed so a typo cannot spend a run
under conditions the owner did not authorize.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionReadiness:
    """Counts-only result safe for dispatch logs and handoff decisions."""

    ready: bool
    blockers: tuple[str, ...] = ()


def _value(source: Mapping[str, Any] | object, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _requirement_mapping(requirement: Mapping[str, Any] | object) -> Mapping[str, Any] | None:
    if isinstance(requirement, Mapping):
        return requirement
    model_dump = getattr(requirement, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="python")
        if isinstance(dumped, Mapping):
            return dumped
    return None


def evaluate_execution_requirements(
    task: Mapping[str, Any] | object,
    *,
    mount_probe: Callable[[str], bool] | None = None,
) -> ExecutionReadiness:
    """Evaluate one task's structured requirements against current control-host state.

    ``mount`` means the exact absolute path must currently be a mount point.  Merely having a
    directory at that path is insufficient: an unmounted external volume can leave or later gain a
    look-alike directory, and dispatch must not write into the laptop under that name.
    """

    raw = _value(task, "execution_requirements", None)
    if raw is None or raw == []:
        return ExecutionReadiness(ready=True)
    if not isinstance(raw, list):
        return ExecutionReadiness(ready=False, blockers=("execution_requirements must be a list",))

    probe = mount_probe or os.path.ismount
    blockers: list[str] = []
    for index, raw_requirement in enumerate(raw):
        requirement = _requirement_mapping(raw_requirement)
        if requirement is None:
            blockers.append(f"execution_requirements[{index}] must be an object")
            continue
        if set(requirement) != {"kind", "path"}:
            blockers.append(f"execution_requirements[{index}] must contain exactly kind/path")
            continue
        kind = requirement.get("kind")
        path = requirement.get("path")
        if kind != "mount":
            blockers.append(f"execution_requirements[{index}] has unsupported kind")
            continue
        if not isinstance(path, str) or not path or "\x00" in path or not os.path.isabs(path):
            blockers.append(f"execution_requirements[{index}] mount path must be absolute")
            continue
        try:
            mounted = bool(probe(path))
        except OSError:
            mounted = False
        if not mounted:
            blockers.append(f"required mount unavailable: {path}")

    return ExecutionReadiness(ready=not blockers, blockers=tuple(blockers))


def task_execution_ready(task: Mapping[str, Any] | object) -> bool:
    """Boolean selector hook shared by handoff and dispatch."""

    return evaluate_execution_requirements(task).ready
