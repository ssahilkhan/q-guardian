"""Generic adapter stub for Q-Guardian.

Placeholder for custom AI framework integrations.
"""

from __future__ import annotations

from typing import Any

from q_guardian.adapters.base import Adapter


class GenericAdapter(Adapter):
    """Generic adapter for custom AI framework integration.

    This is a stub implementation for developers building
    adapters for unsupported frameworks.
    """

    @property
    def name(self) -> str:
        return "generic"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def framework_name(self) -> str:
        return "Generic"

    async def initialize(self, context: Any) -> None:
        pass

    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        msg = "GenericAdapter.connect_agent not yet implemented"
        raise NotImplementedError(msg)

    async def process_prompt(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        msg = "GenericAdapter.process_prompt not yet implemented"
        raise NotImplementedError(msg)

    async def handle_response(self, response: Any) -> dict[str, Any]:
        msg = "GenericAdapter.handle_response not yet implemented"
        raise NotImplementedError(msg)

    async def extract_features(self, data: Any) -> dict[str, Any]:
        msg = "GenericAdapter.extract_features not yet implemented"
        raise NotImplementedError(msg)
