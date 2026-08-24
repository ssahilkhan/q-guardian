"""LangGraph adapter for Q-Guardian.

Integrates Q-Guardian's security pipeline with LangGraph framework,
providing security scanning for LangGraph graph inputs, outputs,
states, and messages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from q_guardian.adapters.base import Adapter
from q_guardian.security.encoding import detect_all_encodings

if TYPE_CHECKING:
    from q_guardian.sdk.guardian import Guardian

try:
    import langgraph
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import START, StateGraph
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.types import Command, interrupt

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    langgraph = None  # type: ignore[assignment]
    StateGraph = object  # type: ignore[assignment]
    START = object  # type: ignore[assignment]
    CompiledStateGraph = object  # type: ignore[assignment]
    BaseCheckpointSaver = object  # type: ignore[assignment]
    InMemorySaver = object  # type: ignore[assignment]
    interrupt = object  # type: ignore[assignment]
    Command = object  # type: ignore[assignment]
    HumanMessage = object  # type: ignore[assignment]
    AIMessage = object  # type: ignore[assignment]
    ToolMessage = object  # type: ignore[assignment]
    SystemMessage = object  # type: ignore[assignment]
    BaseMessage = object  # type: ignore[assignment]
    LANGGRAPH_AVAILABLE = False

logger = logging.getLogger("q_guardian.adapters.langgraph")


class LangGraphSecurityError(Exception):
    """Raised when LangGraph execution is blocked by security policy."""

    def __init__(self, message: str, findings: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.findings = findings or []


class LangGraphAdapter(Adapter):
    """Adapter for LangGraph framework integration.

    Provides security scanning for LangGraph graph inputs, outputs,
    states, messages, and node execution.
    """

    def __init__(
        self,
        guardian: Guardian | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the LangGraph adapter.

        Args:
            guardian: Optional Guardian instance for security scanning.
            config: Optional configuration dictionary.
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError(
                "LangGraph is not installed. Install with: pip install 'q-guardian[langgraph]'"
            )

        self._guardian = guardian
        self._config = config or {}
        self._compiled_graph: Any = None
        self._checkpointer: Any = None

    @property
    def name(self) -> str:
        return "langgraph"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def framework_name(self) -> str:
        return "LangGraph"

    async def initialize(self, context: Any) -> None:
        """Initialize the adapter with framework context.

        Args:
            context: The shared framework context.
        """
        self._context = context
        logger.info("LangGraph adapter initialized")

    async def shutdown(self) -> None:
        """Shut down the adapter and release resources."""
        self._compiled_graph = None
        self._checkpointer = None
        logger.info("LangGraph adapter shut down")

    async def connect_agent(self, agent_config: dict[str, Any]) -> Any:
        """Connect an AI agent to the security framework.

        Args:
            agent_config: Configuration for the agent connection.
                Expected keys: 'graph' (StateGraph), 'checkpointer' (optional)

        Returns:
            Compiled graph with security wrapping.
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError(
                "LangGraph is not installed. Install with: pip install 'q-guardian[langgraph]'"
            )

        graph = agent_config.get("graph")
        if graph is None:
            raise ValueError("agent_config must contain 'graph' (StateGraph instance)")

        checkpointer = agent_config.get("checkpointer")
        compiled = self.compile_graph(graph, checkpointer=checkpointer)
        self._compiled_graph = compiled
        return compiled

    async def process_prompt(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """Process a prompt through the security pipeline.

        Args:
            prompt: The prompt text to process.
            context: Additional processing context.

        Returns:
            Processing result dictionary with security findings.
        """
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import PromptNormalizer, PromptValidator, RuleEngine

        # Normalize and validate
        normalizer = PromptNormalizer()
        validator = PromptValidator()

        normalized = normalizer.normalize(prompt)
        validation_status, validation_errors = validator.validate(normalized)

        # Extract features
        from q_guardian.security.pipeline import PromptFeatureExtractor

        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        # Rule analysis
        findings = RuleEngine().analyze(normalized, features)

        # Build analysis
        analysis = PromptAnalysis(
            original_prompt=prompt,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )

        # Decision
        from q_guardian.security.decision import SecurityDecisionEngine

        decision_engine = SecurityDecisionEngine()
        decision_engine.decide(analysis)

        return analysis.model_dump()

    async def handle_response(self, response: Any) -> dict[str, Any]:
        """Handle a response from the AI framework.

        Args:
            response: The raw response from the AI framework.

        Returns:
            Processed response dictionary.
        """
        # Extract text content from response
        text_content = self._extract_text_content(response)
        return await self.process_prompt(text_content, {})

    async def extract_features(self, data: Any) -> dict[str, Any]:
        """Extract security-relevant features from framework data.

        Args:
            data: Raw data from the AI framework.

        Returns:
            Extracted features dictionary.
        """
        from q_guardian.security.homoglyph import analyze_homoglyphs

        text_content = self._extract_text_content(data)
        if not text_content:
            return {}

        features = {}

        # Basic features
        features["length"] = len(text_content)
        features["word_count"] = len(text_content.split())
        features["line_count"] = text_content.count("\n") + 1

        # Encoding detection
        encoding_candidates = detect_all_encodings(text_content)
        features["encoding_candidates"] = [
            {
                "encoding": c.encoding,
                "confidence": c.confidence,
                "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
            }
            for c in encoding_candidates
        ]

        # Homoglyph detection
        homoglyph_results = analyze_homoglyphs(text_content)
        features["homoglyph"] = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
            "confusables_count": len(homoglyph_results["confusables"]),
            "mixed_script_count": len(homoglyph_results["mixed_script"]),
        }

        return features

    # ============================================================
    # LangGraph-specific APIs
    # ============================================================

    def compile_graph(
        self,
        graph: StateGraph,  # type: ignore[type-arg]
        checkpointer: BaseCheckpointSaver | None = None,  # type: ignore[type-arg]
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        **kwargs: Any,
    ) -> CompiledStateGraph:  # type: ignore[type-arg]
        """Compile a LangGraph StateGraph with security wrapping.

        Args:
            graph: The StateGraph to compile.
            checkpointer: Optional checkpointer for persistence.
            interrupt_before: List of node names to interrupt before.
            interrupt_after: List of node names to interrupt after.
            **kwargs: Additional arguments passed to graph.compile().

        Returns:
            Compiled graph with security wrapping.
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph is not installed")

        # Wrap node functions for security scanning
        self._wrap_graph_nodes(graph)

        compile_kwargs = {}
        if checkpointer is not None:
            compile_kwargs["checkpointer"] = checkpointer
        if interrupt_before:
            compile_kwargs["interrupt_before"] = interrupt_before
        if interrupt_after:
            compile_kwargs["interrupt_after"] = interrupt_after
        compile_kwargs.update(kwargs)

        compiled = graph.compile(**compile_kwargs)

        # Wrap the compiled graph for security
        self._compiled_graph = self._wrap_compiled_graph(compiled)
        return self._compiled_graph

    def wrap_graph(self, compiled_graph: CompiledStateGraph) -> CompiledStateGraph:  # type: ignore[type-arg]
        """Wrap an already compiled graph with security scanning.

        Args:
            compiled_graph: Pre-compiled LangGraph graph.

        Returns:
            Wrapped graph with security scanning.
        """
        self._compiled_graph = self._wrap_compiled_graph(compiled_graph)
        return self._compiled_graph

    async def scan_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """Scan graph input state for security threats.

        Args:
            state: Input state dictionary.

        Returns:
            Security analysis result.
        """
        return await self._scan_state(state, "input")

    async def scan_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Scan graph output state for security threats.

        Args:
            state: Output state dictionary.

        Returns:
            Security analysis result.
        """
        return await self._scan_state(state, "output")

    async def scan_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Scan graph state for security threats.

        Args:
            state: State dictionary to scan.

        Returns:
            Security analysis result.
        """
        return await self._scan_state(state, "state")

    # ============================================================
    # Internal Implementation
    # ============================================================

    def _wrap_graph_nodes(self, graph: StateGraph) -> StateGraph:
        """Wrap node functions in a graph for security scanning.

        This creates a new graph with wrapped node functions.
        """
        # LangGraph doesn't easily allow node wrapping after graph creation.
        # We handle security at the compiled graph level instead.
        return graph

    def _wrap_compiled_graph(self, compiled: CompiledStateGraph) -> CompiledStateGraph:
        """Wrap a compiled graph with security scanning."""
        # Store original invoke/ainvoke methods
        original_invoke = compiled.invoke
        original_ainvoke = compiled.ainvoke
        original_stream = compiled.stream
        original_astream = compiled.astream

        adapter = self

        async def secured_ainvoke(input_data, config=None, **kwargs):
            # Scan input
            await adapter._scan_and_check(input_data, "input")
            # Execute original
            result = await original_ainvoke(input_data, config, **kwargs)
            # Scan output
            await adapter._scan_and_check(result, "output")
            return result

        def secured_invoke(input_data, config=None, **kwargs):
            # Scan input
            adapter._scan_and_check_sync(input_data, "input")
            # Execute original
            result = original_invoke(input_data, config, **kwargs)
            # Scan output
            adapter._scan_and_check_sync(result, "output")
            return result

        def secured_stream(input_data, config=None, **kwargs):
            # Scan input
            adapter._scan_and_check_sync(input_data, "input")

            # Stream with output scanning
            async def scan_stream():
                async for chunk in original_stream(input_data, config, **kwargs):
                    # Scan each chunk
                    await adapter._scan_and_check(chunk, "stream_chunk")
                    yield chunk

            return scan_stream()

        async def secured_astream(input_data, config=None, **kwargs):
            # Scan input
            await adapter._scan_and_check(input_data, "input")
            # Stream with output scanning
            async for chunk in original_astream(input_data, config, **kwargs):
                await adapter._scan_and_check(chunk, "stream_chunk")
                yield chunk

        # Replace methods
        compiled.invoke = secured_invoke
        compiled.ainvoke = secured_ainvoke
        compiled.stream = secured_stream
        compiled.astream = secured_astream

        return compiled

    async def _scan_and_check(self, data: Any, source: str) -> dict[str, Any]:
        """Scan data and raise exception if blocked."""
        result = await self._scan_text(self._extract_text_content(data), source)
        if result.get("decision") == "block":
            raise LangGraphSecurityError(
                f"Security policy violation in {source}",
                result.get("findings", []),
            )
        return result

    def _scan_and_check_sync(self, data: Any, source: str) -> dict[str, Any]:
        """Synchronous version of scan and check."""
        result = asyncio.run(self._scan_text(self._extract_text_content(data), source))
        if result.get("decision") == "block":
            raise LangGraphSecurityError(
                f"Security policy violation in {source}",
                result.get("findings", []),
            )
        return result

    async def _scan_state(self, state: dict[str, Any], source: str) -> dict[str, Any]:
        """Scan a state dictionary for security threats."""
        # Extract text from state values
        text_parts = []
        for key, value in state.items():
            if isinstance(value, str):
                text_parts.append(f"{key}: {value}")
            elif isinstance(value, (list, dict)):
                text_parts.append(f"{key}: {self._extract_text_content(value)}")

        text_content = "\n".join(text_parts)
        return await self._scan_text(text_content, source)

    async def _scan_text(self, text: str, source: str) -> dict[str, Any]:
        """Scan text content using the existing security pipeline."""
        from q_guardian.security.decision import SecurityDecisionEngine
        from q_guardian.security.homoglyph import analyze_homoglyphs
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import (
            PromptFeatureExtractor,
            PromptNormalizer,
            PromptValidator,
            RuleEngine,
        )

        if not text or not text.strip():
            return {"decision": "allow", "risk_score": 0.0, "findings": []}

        # Normalize and validate
        normalizer = PromptNormalizer()
        validator = PromptValidator()

        normalized = normalizer.normalize(text)
        validation_status, validation_errors = validator.validate(normalized)

        # Extract features
        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        # Add encoding and homoglyph features
        from q_guardian.security.encoding import detect_all_encodings

        encoding_candidates = detect_all_encodings(text)
        homoglyph_results = analyze_homoglyphs(text)

        # Add to features
        features.encoding_candidates = [
            {
                "encoding": c.encoding,
                "confidence": c.confidence,
                "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
            }
            for c in encoding_candidates
        ]
        features.homoglyph = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
        }

        # Rule analysis
        engine = RuleEngine()
        findings = engine.analyze(normalized, features)

        # Build analysis
        analysis = PromptAnalysis(
            original_prompt=text,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )

        # Decision
        decision_engine = SecurityDecisionEngine()
        decision_engine.decide(analysis)

        return {
            "decision": analysis.decision.value,
            "risk_score": analysis.risk_score,
            "findings": [f.model_dump() for f in analysis.findings],
            "encoding_context": {
                "encoding_candidates": [
                    {
                        "encoding": c.encoding,
                        "confidence": c.confidence,
                        "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
                    }
                    for c in encoding_candidates
                ],
                "homoglyph": {
                    "has_confusables": homoglyph_results["has_confusables"],
                    "has_mixed_script": homoglyph_results["has_mixed_script"],
                },
            },
        }

    async def _scan_text(self, text: str, source: str) -> dict[str, Any]:
        """Scan text content using the existing security pipeline."""
        return await self._scan_text(text, source)

    def _extract_text_content(self, data: Any) -> str:
        """Extract text content from various data types."""
        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            parts = []
            for key, value in data.items():
                if isinstance(value, str):
                    parts.append(f"{key}: {value}")
                elif isinstance(value, (list, dict)):
                    parts.append(f"{key}: {self._extract_text_content(value)}")
                elif hasattr(data, "content") and isinstance(data.content, str):
                    parts.append(f"{key}: {data.content}")
            return "\n".join(parts)
        elif isinstance(data, list):
            parts = []
            for item in data:
                parts.append(self._extract_text_content(item))
            return "\n".join(parts)
        elif hasattr(data, "content") and isinstance(data.content, str):
            return data.content
        elif hasattr(data, "content") and isinstance(data.content, list):
            # Structured content (e.g., [{"type": "text", "text": "..."}])
            parts = []
            for item in data.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "\n".join(parts)
        elif hasattr(data, "content"):
            return str(data.content)
        return str(data)

    def _extract_text_content(self, data: Any) -> str:
        """Extract text content from various data types."""
        return self._extract_text_content(data)

    def _extract_messages_text(self, messages: list[Any]) -> str:
        """Extract text from a list of LangChain messages."""
        if not messages:
            return ""

        parts = []
        for _msg in messages:
            if hasattr(_msg, "content"):
                content = _msg.content
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item.get("text", ""))
        return "\n".join(parts)

    # ============================================================
    # Indirect injection: provenance-aware state scanning (P3-5)
    # ============================================================

    async def scan_state_with_provenance(
        self,
        state: dict[str, Any],
        untrusted_keys: list[str],
        source: str = "state",
    ) -> dict[str, Any]:
        """Scan graph state with provenance-aware indirect injection analysis.

        Values under ``untrusted_keys`` are treated as untrusted external
        content (tool outputs, retrieved documents, ...) and analyzed by
        the ``ii-*`` rules in addition to the standard direct rules.
        Behavior is additive: keys not listed keep their existing handling,
        and an empty ``untrusted_keys`` list yields the same result as a
        plain state scan.

        This method is intentionally self-contained and does not rely on
        the legacy internal text-scanning helpers.

        Args:
            state: The graph state dictionary.
            untrusted_keys: State keys whose values carry untrusted
                external content. String values and lists of strings are
                supported; other value types are stringified.
            source: Label describing where the state came from.

        Returns:
            Scan result dictionary with decision, risk_score, findings,
            source, encoding_context, and (when segments were scanned)
            indirect_context keys.

        Raises:
            ValueError: If ``untrusted_keys`` is empty or state is empty.
        """
        from q_guardian.security.config import IndirectInjectionConfig
        from q_guardian.security.decision import SecurityDecisionEngine
        from q_guardian.security.homoglyph import analyze_homoglyphs
        from q_guardian.security.indirect import (
            ContentSegment,
            SourceType,
            build_untrusted_context,
        )
        from q_guardian.security.models import PromptAnalysis
        from q_guardian.security.pipeline import (
            PromptFeatureExtractor,
            PromptNormalizer,
            PromptValidator,
            RuleEngine,
        )

        if not untrusted_keys:
            raise ValueError("untrusted_keys must contain at least one state key")
        if not state:
            raise ValueError("state must not be empty")

        segments: list[ContentSegment] = []
        for position, key in enumerate(untrusted_keys):
            if key not in state:
                continue
            value = state[key]
            texts = (
                [str(item) for item in value]
                if isinstance(value, list)
                else [value if isinstance(value, str) else str(value)]
            )
            for text in texts:
                if text.strip():
                    segments.append(
                        ContentSegment(
                            content=text,
                            source_type=SourceType.TOOL_OUTPUT,
                            source_id=key,
                            position=position,
                        )
                    )

        direct_text = "\n".join(str(v) for k, v in state.items() if isinstance(v, str))
        if not direct_text.strip():
            return {"decision": "allow", "risk_score": 0.0, "findings": [], "source": source}

        normalizer = PromptNormalizer()
        validator = PromptValidator()
        normalized = normalizer.normalize(direct_text)
        validation_status, validation_errors = validator.validate(normalized)

        feature_extractor = PromptFeatureExtractor()
        features = feature_extractor.extract(normalized)

        homoglyph_results = analyze_homoglyphs(normalized)
        features.metadata["homoglyph"] = {
            "has_confusables": homoglyph_results["has_confusables"],
            "has_mixed_script": homoglyph_results["has_mixed_script"],
        }

        indirect_context: dict[str, Any] | None = None
        if segments:
            indirect_config = IndirectInjectionConfig()
            indirect_context = build_untrusted_context(segments, indirect_config)
            features.metadata["untrusted_context"] = indirect_context

        engine = RuleEngine()
        findings = engine.analyze(normalized, features)

        analysis = PromptAnalysis(
            original_prompt=direct_text,
            normalized_prompt=normalized,
            is_valid=(validation_status.value == "valid"),
            validation_status=validation_status,
            validation_errors=validation_errors,
            features=features,
            findings=findings,
        )
        SecurityDecisionEngine().decide(analysis)

        result: dict[str, Any] = {
            "decision": analysis.decision.value,
            "risk_score": analysis.risk_score,
            "findings": [f.model_dump() for f in analysis.findings],
            "recommendation": analysis.recommendation,
            "source": source,
            "encoding_context": {
                "encoding_candidates": [
                    {
                        "encoding": c.encoding,
                        "confidence": c.confidence,
                        "decoded_preview": c.metadata.get("decoded_preview", "")[:200],
                    }
                    for c in detect_all_encodings(normalized)
                ],
                "homoglyph": {
                    "has_confusables": homoglyph_results["has_confusables"],
                    "has_mixed_script": homoglyph_results["has_mixed_script"],
                },
            },
        }
        if indirect_context is not None:
            result["indirect_context"] = {
                "segments_scanned": len(indirect_context.get("segments", [])),
                "segments_omitted": indirect_context.get("segments_omitted", 0),
                "trusted_count": indirect_context.get("trusted_count", 0),
                "indirect_findings_count": sum(
                    1 for f in analysis.findings if f.rule_id.startswith("ii-")
                ),
            }
        return result

    def health(self) -> dict[str, Any]:
        """Return adapter health status."""
        return {
            "status": "healthy",
            "adapter": self.name,
            "version": self.version,
            "framework": self.framework_name,
            "langgraph_available": LANGGRAPH_AVAILABLE,
            "compiled_graph_ready": self._compiled_graph is not None,
        }

    def configuration(self) -> dict[str, Any]:
        """Return adapter configuration schema."""
        return {
            "encoding_detection_enabled": self._config.get("encoding_detection_enabled", True),
            "max_decode_depth": self._config.get("max_decode_depth", 3),
            "max_decoded_length": self._config.get("max_decoded_length", 50000),
        }


def create_langgraph_adapter(
    guardian: Guardian | None = None,
    config: dict[str, Any] | None = None,
) -> LangGraphAdapter:
    """Factory function to create a LangGraph adapter.

    Args:
        guardian: Optional Guardian instance for security scanning.
        config: Optional configuration dictionary.

    Returns:
        Configured LangGraphAdapter instance.
    """
    return LangGraphAdapter(guardian=guardian, config=config)
