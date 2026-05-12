from __future__ import annotations

import os
from pathlib import Path
from typing import Any


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
        return base / (Path(configured).name if configured else default_name)
    path = Path(configured) if configured else base / default_name
    return path if path.is_absolute() else base / path
