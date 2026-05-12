from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _configured_leaf(value: str, default_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return default_name
    normalized = cleaned.replace("\\", "/").rstrip("/")
    leaf = normalized.rsplit("/", 1)[-1].strip()
    return leaf or default_name


def local_models_base_dir(config: Any) -> Path:
    env_root = str(os.environ.get("ICU_MODELS_DIR") or "").strip()
    if env_root:
        return Path(env_root)
    ai = (getattr(config, "yaml_cfg", {}) or {}).get("ai_service", {})
    local_models = ai.get("local_models", {}) if isinstance(ai, dict) else {}
    return Path(str(local_models.get("base_dir") or "icu-models"))


def local_model_dir(config: Any, key: str, default_name: str) -> Path:
    base = local_models_base_dir(config)
    ai = (getattr(config, "yaml_cfg", {}) or {}).get("ai_service", {})
    local_models = ai.get("local_models", {}) if isinstance(ai, dict) else {}
    configured = str(local_models.get(key) or "").strip()
    if os.environ.get("ICU_MODELS_DIR"):
        return base / _configured_leaf(configured, default_name)
    if configured and len(configured) >= 2 and configured[1] == ":" and os.name != "nt":
        return base / _configured_leaf(configured, default_name)
    path = Path(configured) if configured else base / default_name
    return path if path.is_absolute() else base / path
