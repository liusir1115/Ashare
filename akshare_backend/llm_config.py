from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class LLMSettings:
    provider: str
    api_key: str
    base_url: str
    model: str
    reasoning_effort: str
    thinking_type: str
    timeout_seconds: float

    @property
    def enabled(self) -> bool:
        return bool(self.api_key.strip())


def load_llm_settings() -> LLMSettings:
    local_values: dict[str, object] = {}
    try:
        from . import deepseek_runtime_local as local_runtime
    except ImportError:
        try:
            import deepseek_runtime_local as local_runtime  # type: ignore
        except ImportError:
            local_runtime = None  # type: ignore

    if local_runtime is not None:
        local_values = {
            "api_key": getattr(local_runtime, "DEEPSEEK_API_KEY", ""),
            "base_url": getattr(local_runtime, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "model": getattr(local_runtime, "DEEPSEEK_MODEL", "deepseek-v4-flash"),
            "reasoning_effort": getattr(local_runtime, "DEEPSEEK_REASONING_EFFORT", "minimal"),
            "thinking_type": getattr(local_runtime, "DEEPSEEK_THINKING_TYPE", "disabled"),
            "timeout_seconds": getattr(local_runtime, "DEEPSEEK_TIMEOUT_SECONDS", 90.0),
        }

    return LLMSettings(
        provider="deepseek",
        api_key=(os.getenv("DEEPSEEK_API_KEY", "") or str(local_values.get("api_key", ""))).strip(),
        base_url=(os.getenv("DEEPSEEK_BASE_URL", "") or str(local_values.get("base_url", "https://api.deepseek.com"))).rstrip("/"),
        model=(os.getenv("DEEPSEEK_MODEL", "") or str(local_values.get("model", "deepseek-v4-flash"))).strip() or "deepseek-v4-flash",
        reasoning_effort=(os.getenv("DEEPSEEK_REASONING_EFFORT", "") or str(local_values.get("reasoning_effort", "minimal"))).strip() or "minimal",
        thinking_type=(os.getenv("DEEPSEEK_THINKING_TYPE", "") or str(local_values.get("thinking_type", "disabled"))).strip() or "disabled",
        timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "").strip() or local_values.get("timeout_seconds", 90.0)),
    )
