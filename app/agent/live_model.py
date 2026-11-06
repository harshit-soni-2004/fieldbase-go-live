from typing import Any, Optional

class LiveModel:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def next_action(self) -> dict[str, Any]:
        raise NotImplementedError("LiveModel will be implemented in Prompt 5")
