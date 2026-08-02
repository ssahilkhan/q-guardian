"""LangGraph adapter stub for Q-Guardian.

Placeholder for future LangGraph integration.
"""

from __future__ import annotations

from typing import Any

from q_guardian.adapters.base import Adapter


class LangGraphAdapter(Adapter):
    """Adapter for LangGraph framework integration.

    This is a stub implementation. The full implementation will
    be provided in a future module.
    """

    @property
    def name(self) -> str:
        return "langgraph"

    @property
    def version(self) -> str:
        return "0.10.0"

    @property
    def framework_name(self) -> str:
        return "LangGraph"

    async def initialize(self, context: Any) -> None:
        pass

    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        msg = "LangGraphAdapter.connect_agent not yet implemented"
        raise NotImplementedError(msg)

    async def process_prompt(
        self, prompt: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        msg = "LangGraphAdapter.process_prompt not yet implemented"
        raise NotImplementedError(msg)

    async def handle_response(self, response: Any) -> dict[str, Any]:
        msg = "LangGraphAdapter.handle_response not yet implemented"
        raise NotImplementedError(msg)

    async def extract_features(self, data: Any) -> dict[str, Any]:
        msg = "LangGraphAdapter.extract_features not yet implemented"
        raise NotImplementedError(msg)
