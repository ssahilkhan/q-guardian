"""Google ADK adapter stub for Q-Guardian.

Placeholder for future Google ADK integration.
"""

from __future__ import annotations

from typing import Any

from q_guardian.adapters.base import Adapter


class GoogleADKAdapter(Adapter):
    """Adapter for Google ADK integration.

    This is a stub implementation.
    """

    @property
    def name(self) -> str:
        return "google_adk"

    @property
    def version(self) -> str:
        return "0.10.0"

    @property
    def framework_name(self) -> str:
        return "Google ADK"

    async def initialize(self, context: Any) -> None:
        pass

    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        msg = "GoogleADKAdapter.connect_agent not yet implemented"
        raise NotImplementedError(msg)

    async def process_prompt(
        self, prompt: str, context: dict[str, Any]
    ) -> dict[str, Any]:
        msg = "GoogleADKAdapter.process_prompt not yet implemented"
        raise NotImplementedError(msg)

    async def handle_response(self, response: Any) -> dict[str, Any]:
        msg = "GoogleADKAdapter.handle_response not yet implemented"
        raise NotImplementedError(msg)

    async def extract_features(self, data: Any) -> dict[str, Any]:
        msg = "GoogleADKAdapter.extract_features not yet implemented"
        raise NotImplementedError(msg)
