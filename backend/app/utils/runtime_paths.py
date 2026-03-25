from __future__ import annotations

import os
import sys
from pathlib import Path


def package_root() -> Path:
    explicit = str(os.environ.get("ICU_APP_ROOT") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    explicit = str(os.environ.get("ICU_CONFIG_PATH") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return package_root() / "config.yaml"


def static_dir() -> Path:
    explicit = str(os.environ.get("ICU_FRONTEND_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return package_root() / "static"


def knowledge_base_dir() -> Path:
    return package_root() / "knowledge_base"


def model_search_roots() -> list[Path]:
    root = package_root()
    return [root / "models", root / "weights", root / "artifacts"]
