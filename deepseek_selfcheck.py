from __future__ import annotations

import os
import tempfile
from pathlib import Path

from deepseek_client import get_deepseek_api_key, load_dotenv, request_json_completion


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def post(self, url, headers=None, json=None, timeout=None):  # noqa: A002
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"suggested_title":"语言与认知 第01讲","reasoning":"从元数据推断"}'
                        }
                    }
                ]
            }
        )


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        env_path = Path(temp_dir) / ".env"
        env_path.write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")
        loaded = load_dotenv(env_path)
        assert loaded["DEEPSEEK_API_KEY"] == "from-dotenv"
        assert get_deepseek_api_key(env_path) == "from-dotenv"

        os.environ["DEEPSEEK_API_KEY"] = "from-env"
        assert get_deepseek_api_key(env_path) == "from-env"
        del os.environ["DEEPSEEK_API_KEY"]

    result = request_json_completion(
        system_prompt="system",
        user_prompt="user",
        api_key="test-key",
        session=FakeSession(),
    )
    assert result["suggested_title"] == "语言与认知 第01讲"
    print("deepseek selfcheck passed")


if __name__ == "__main__":
    main()
