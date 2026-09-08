from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class DeviceError(RuntimeError):
    pass


class RetryExhaustedError(RuntimeError):
    def __init__(self, attempts: int):
        super().__init__(f"generation failed after {attempts} attempts")
        self.attempts = attempts


def require_cuda(torch_module: Any) -> str:
    if not torch_module.cuda.is_available():
        raise DeviceError("CUDA is unavailable; CPU fallback is forbidden")
    return "cuda"


def run_with_bounded_retry(
    generate: Callable[[], str | dict[str, Any]],
    *,
    max_attempts: int,
    validate: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            raw = generate()
            parsed = raw if isinstance(raw, dict) else json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("model response is not a JSON object")
            if validate is not None:
                validate(parsed)
            return parsed
        except (TypeError, ValueError) as exc:
            last_error = exc
    raise RuntimeError(
        f"generation failed after {max_attempts} attempts: "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error
