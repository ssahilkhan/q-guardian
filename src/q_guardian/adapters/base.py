"""Base adapter class for Q-Guardian AI framework integrations.

Defines the abstract interface that all AI framework adapters
must implement. Adapters bridge Q-Guardian with external
AI agent frameworks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from q_guardian.framework.context import FrameworkContext


class Adapter(ABC):
    """Abstract base class for AI framework adapters.

    Adapters connect Q-Guardian's security framework with
    external AI agent frameworks (LangGraph, CrewAI, etc.).

    Each adapter translates between Q-Guardian's event-driven
    model and the target framework's execution model.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique adapter name identifier."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Adapter version string."""

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Name of the AI framework this adapter connects to."""

    @abstractmethod
    async def initialize(self, context: FrameworkContext) -> None:
        """Initialize the adapter with framework context.

        Args:
            context: The shared framework context.
        """

    @abstractmethod
    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        """Connect an AI agent to the security framework.

        Args:
            agent_config: Configuration for the agent connection.

        Returns:
            Agent connection handle.
        """

    @abstractmethod
    async def process_prompt(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """Process a prompt through the adapter.

        Args:
            prompt: The prompt text to process.
            context: Additional processing context.

        Returns:
            Processing result dictionary.
        """

    @abstractmethod
    async def handle_response(self, response: Any) -> dict[str, Any]:
        """Handle a response from the AI framework.

        Args:
            response: The raw response from the AI framework.

        Returns:
            Processed response dictionary.
        """

    @abstractmethod
    async def extract_features(self, data: Any) -> dict[str, Any]:
        """Extract security-relevant features from framework data.

        Args:
            data: Raw data from the AI framework.

        Returns:
            Extracted features dictionary.
        """

    def health(self) -> dict[str, Any]:
        """Return adapter health status.

        Override to provide custom health information.

        Returns:
            Dictionary with health status.
        """
        return {"status": "healthy", "adapter": self.name}

    async def shutdown(self) -> None:
        """Shut down the adapter and release resources."""
        return None
