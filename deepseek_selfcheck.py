from __future__ import annotations

from deepseek_client import request_json_completion


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
