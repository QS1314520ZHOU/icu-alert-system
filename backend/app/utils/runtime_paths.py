from __future__ import annotations

import os
import sys
from pathlib import Path


def _first_existing_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


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
    candidates = [package_root() / "config.yaml"]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(sys._MEIPASS).resolve() / "config.yaml")
    return _first_existing_path(candidates)


def static_dir() -> Path:
    explicit = str(os.environ.get("ICU_FRONTEND_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates = [package_root() / "static"]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(sys._MEIPASS).resolve() / "static")
    return _first_existing_path(candidates)


def knowledge_base_dir() -> Path:
    candidates = [package_root() / "knowledge_base"]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.insert(0, Path(sys._MEIPASS).resolve() / "knowledge_base")
    return _first_existing_path(candidates)


def model_search_roots() -> list[Path]:
    root = package_root()
    return [root / "models", root / "weights", root / "artifacts"]
