from __future__ import annotations

import os
from typing import Any


def acceleration_mode() -> str:
    raw = str(
        os.environ.get("ICU_ACCELERATION")
        or os.environ.get("ICU_INFERENCE_DEVICE")
        or "auto"
    ).strip().lower()
    if raw in {"gpu", "cuda"}:
        return "gpu"
    if raw in {"cpu", "off"}:
        return "cpu"
    return "auto"


def torch_device_name() -> str:
    mode = acceleration_mode()
    if mode == "cpu":
        return "cpu"
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def sentence_transformer_kwargs() -> dict[str, Any]:
    return {"device": torch_device_name()}


def onnx_providers() -> list[str]:
    mode = acceleration_mode()
    try:
        import onnxruntime as ort  # type: ignore

        available = set(ort.get_available_providers())
    except Exception:
        return ["CPUExecutionProvider"]

    preferred: list[str] = []
    if mode != "cpu" and "CUDAExecutionProvider" in available:
        preferred.append("CUDAExecutionProvider")
    if "CPUExecutionProvider" in available:
        preferred.append("CPUExecutionProvider")
    return preferred or ["CPUExecutionProvider"]
