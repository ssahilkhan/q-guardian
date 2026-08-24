"""Adapter system for Q-Guardian.

Provides base adapter interface and stubs for AI framework
integrations (LangGraph, CrewAI, AutoGen, etc.).
"""

from q_guardian.adapters.base import Adapter
from q_guardian.adapters.langgraph import LangGraphAdapter, create_langgraph_adapter

__all__ = ["Adapter", "LangGraphAdapter", "create_langgraph_adapter"]
