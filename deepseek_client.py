from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
ENV_FILE_NAME = ".env"


class DeepSeekError(RuntimeError):
    pass


def load_dotenv(dotenv_path: str | Path = ENV_FILE_NAME) -> dict[str, str]:
    path = Path(dotenv_path)
    if not path.exists():
        return {}

    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def get_deepseek_api_key(dotenv_path: str | Path = ENV_FILE_NAME) -> str | None:
    env_key = os.getenv("DEEPSEEK_API_KEY")
    if env_key:
        return env_key

    return load_dotenv(dotenv_path).get("DEEPSEEK_API_KEY")


def is_deepseek_enabled() -> bool:
    return bool(get_deepseek_api_key())


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
    key = api_key or get_deepseek_api_key()
    if not key:
        raise DeepSeekError("未设置 DEEPSEEK_API_KEY")

    client = session or requests.Session()
    if hasattr(client, "trust_env"):
        client.trust_env = False
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
