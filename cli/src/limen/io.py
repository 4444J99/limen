from pathlib import Path

import yaml

from limen.models import LimenFile


def load_limen_file(path: Path) -> LimenFile:
    raw = yaml.safe_load(path.read_text())
    return LimenFile.model_validate(raw)


def save_limen_file(path: Path, limen: LimenFile) -> None:
    data = limen.model_dump(mode="json", exclude_none=True)
    path.write_text(yaml.dump(data, sort_keys=False, default_flow_style=False))
