"""CrewAI adapter stub for Q-Guardian.

Placeholder for future CrewAI integration.
"""

from __future__ import annotations

from typing import Any

from q_guardian.adapters.base import Adapter


class CrewAIAdapter(Adapter):
    """Adapter for CrewAI framework integration.

    This is a stub implementation.
    """

    @property
    def name(self) -> str:
        return "crewai"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def framework_name(self) -> str:
        return "CrewAI"

    async def initialize(self, context: Any) -> None:
        pass

    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        msg = "CrewAIAdapter.connect_agent not yet implemented"
        raise NotImplementedError(msg)

    async def process_prompt(
        self, prompt: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        msg = "CrewAIAdapter.process_prompt not yet implemented"
        raise NotImplementedError(msg)

    async def handle_response(self, response: Any) -> dict[str, Any]:
        msg = "CrewAIAdapter.handle_response not yet implemented"
        raise NotImplementedError(msg)

    async def extract_features(self, data: Any) -> dict[str, Any]:
        msg = "CrewAIAdapter.extract_features not yet implemented"
        raise NotImplementedError(msg)
