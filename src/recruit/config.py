"""Read the YAML files in config/. Every assumption and scope choice lives there, not in code."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
SQL_DIR = ROOT / "sql"


def load(name: str, config_dir: Path = CONFIG_DIR) -> dict:
    """Load config/<name>.yaml as a dict."""
    with open(Path(config_dir) / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def competition_ids(scope: dict) -> list[int]:
    return [c["competition_id"] for c in scope["competitions"]]
