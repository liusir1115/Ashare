from __future__ import annotations

from typing import Any

import requests

try:
    from .llm_config import LLMSettings
except ImportError:
    from llm_config import LLMSettings


class DeepSeekAPIError(RuntimeError):
    """Raised when the DeepSeek API request fails."""


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise DeepSeekAPIError("DeepSeek response missing choices.")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)

    raise DeepSeekAPIError("DeepSeek response missing message content.")


def chat_completion(
    settings: LLMSettings,
    *,
    system_prompt: str,
    user_prompt: str,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not settings.enabled:
        raise DeepSeekAPIError("DeepSeek API key is not configured.")

    url = f"{settings.base_url}/chat/completions"
    body: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }

    if response_format:
        body["response_format"] = response_format

    extra_body = {
        "reasoning_effort": settings.reasoning_effort,
        "thinking": {"type": settings.thinking_type},
    }
    body["extra_body"] = extra_body

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=settings.timeout_seconds,
    )

    if not response.ok:
        raise DeepSeekAPIError(
            f"DeepSeek request failed: {response.status_code} {response.text[:500]}"
        )

    payload = response.json()
    return {
        "raw": payload,
        "content": _extract_message_content(payload),
    }


def chat_completion_with_timeout(
    settings: LLMSettings,
    *,
    system_prompt: str,
    user_prompt: str,
    response_format: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if timeout_seconds is None:
        return chat_completion(
            settings,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
        )

    original_timeout = settings.timeout_seconds
    settings.timeout_seconds = timeout_seconds
    try:
        return chat_completion(
            settings,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format=response_format,
        )
    finally:
        settings.timeout_seconds = original_timeout
