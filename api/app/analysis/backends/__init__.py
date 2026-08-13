from __future__ import annotations

from .base import ModelBackend
from .classical import ClassicalCVBackend
from .onnx import OnnxBackend, OnnxBackendUnavailable

_classical = ClassicalCVBackend()
_onnx_cache: dict[str, ModelBackend] = {}


def get_backend(
    module: str,
    backend_id: str = "classical_cv",
    artifact_uri: str | None = None,
    version: str = "0.0.0",
) -> ModelBackend:
    """Resolve the backend for a module from its model_registry row.

    Falls back to the classical placeholder if a configured ONNX model cannot
    be loaded, so an operational problem degrades to a working screen rather
    than an outage. The fallback is reported in the analysis payload.
    """
    if backend_id == "onnx" and artifact_uri:
        key = f"{module}:{artifact_uri}:{version}"
        if key not in _onnx_cache:
            _onnx_cache[key] = OnnxBackend(artifact_uri, module, version)
        return _onnx_cache[key]
    return _classical


def classical_backend() -> ModelBackend:
    return _classical


__all__ = [
    "ModelBackend",
    "ClassicalCVBackend",
    "OnnxBackend",
    "OnnxBackendUnavailable",
    "get_backend",
    "classical_backend",
]
