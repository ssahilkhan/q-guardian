"""OpenAI Agents SDK adapter stub for Q-Guardian.

Placeholder for future OpenAI Agents SDK integration.
"""

from __future__ import annotations

from typing import Any

from q_guardian.adapters.base import Adapter


class OpenAIAgentsAdapter(Adapter):
    """Adapter for OpenAI Agents SDK integration.

    This is a stub implementation.
    """

    @property
    def name(self) -> str:
        return "openai_agents"

    @property
    def version(self) -> str:
        return "0.10.0"

    @property
    def framework_name(self) -> str:
        return "OpenAI Agents SDK"

    async def initialize(self, context: Any) -> None:
        pass

    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        msg = "OpenAIAgentsAdapter.connect_agent not yet implemented"
        raise NotImplementedError(msg)

    async def process_prompt(
        self, prompt: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        msg = "OpenAIAgentsAdapter.process_prompt not yet implemented"
        raise NotImplementedError(msg)

    async def handle_response(self, response: Any) -> dict[str, Any]:
        msg = "OpenAIAgentsAdapter.handle_response not yet implemented"
        raise NotImplementedError(msg)

    async def extract_features(self, data: Any) -> dict[str, Any]:
        msg = "OpenAIAgentsAdapter.extract_features not yet implemented"
        raise NotImplementedError(msg)
