from __future__ import annotations

import json
import os
from typing import Any

import requests


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeekError(RuntimeError):
    pass


def is_deepseek_enabled() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY"))


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def request_json_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None = None,
    model: str = DEEPSEEK_MODEL,
    timeout: int = 60,
    base_url: str = DEEPSEEK_BASE_URL,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise DeepSeekError("未设置 DEEPSEEK_API_KEY")

    client = session or requests.Session()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 1024,
    }

    response = client.post(
        f"{base_url}/chat/completions",
        headers=build_headers(key),
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    result = response.json()
    try:
        content = result["choices"][0]["message"]["content"]
        if not content:
            raise DeepSeekError("DeepSeek 返回空内容")
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as error:
        raise DeepSeekError(f"DeepSeek 响应解析失败: {error}") from error
