"""Playbook Parser — parse YAML-like playbook definitions into PlaybookDefinition."""

from __future__ import annotations

import json
from typing import Any

import structlog

from q_guardian.response.data import PlaybookDefinition, PlaybookStep
from q_guardian.response.enums import FailureStrategy, StepType
from q_guardian.response.exceptions import PlaybookError

logger = structlog.get_logger(__name__)


class PlaybookParser:
    """Parses playbook definitions from various formats."""

    def parse_yaml_like(self, raw: str) -> PlaybookDefinition:
        """Parse a YAML-like playbook definition."""
        data = self._parse_yaml(raw)
        return self._dict_to_playbook(data)

    def parse_json(self, raw: str) -> PlaybookDefinition:
        """Parse a JSON playbook definition."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise PlaybookError(f"Invalid JSON: {e}") from e
        return self._dict_to_playbook(data)

    def parse_dict(self, data: dict[str, Any]) -> PlaybookDefinition:
        """Parse a dict playbook definition."""
        return self._dict_to_playbook(data)

    def _dict_to_playbook(self, data: dict[str, Any]) -> PlaybookDefinition:
        steps: list[PlaybookStep] = []
        for step_data in data.get("steps", []):
            if isinstance(step_data, dict):
                step = PlaybookStep(
                    name=step_data.get("name", ""),
                    step_type=StepType(step_data.get("type", "action")),
                    action=step_data.get("action", ""),
                    parameters=step_data.get("parameters", {}),
                    conditions=step_data.get("conditions", []),
                    timeout_seconds=float(step_data.get("timeout", 30)),
                    retry_count=int(step_data.get("retry", 0)),
                    failure_strategy=FailureStrategy(step_data.get("failure", "stop")),
                    depends_on=step_data.get("depends_on", []),
                    on_success=step_data.get("on_success", ""),
                    on_failure=step_data.get("on_failure", ""),
                    rollback_step=step_data.get("rollback", ""),
                    enabled=step_data.get("enabled", True),
                )
                steps.append(step)

        return PlaybookDefinition(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            steps=steps,
            triggers=data.get("triggers", []),
            conditions=data.get("conditions", []),
            timeout_seconds=float(data.get("timeout", 300)),
            tags=data.get("tags", []),
            enabled=data.get("enabled", True),
        )

    @staticmethod
    def _parse_yaml(raw: str) -> dict[str, Any]:
        """Minimal YAML parser for playbook definitions."""
        result: dict[str, Any] = {}
        current_section = None
        current_step: dict[str, Any] | None = None
        indent_level = 0

        for line in raw.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Detect indentation
            raw_indent = len(line) - len(line.lstrip())

            is_list = stripped.startswith("- ")
            if is_list:
                stripped = stripped[2:].strip()

            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip().strip("'\"")

                if is_list and current_section == "steps":
                    if current_step is not None:
                        result.setdefault("steps", []).append(current_step)
                    current_step = {key: val} if val else {}
                elif current_step is not None and raw_indent > indent_level:
                    if val:
                        current_step[key] = PlaybookParser._coerce_value(val)
                else:
                    if current_step is not None and current_section == "steps":
                        result.setdefault("steps", []).append(current_step)
                        current_step = None
                    if val:
                        result[key] = PlaybookParser._coerce_value(val)
                    elif key == "steps":
                        result[key] = []
                    else:
                        result[key] = val
                    if key == "steps":
                        current_section = "steps"
                        indent_level = raw_indent
                    else:
                        current_section = None

        if current_step is not None:
            result.setdefault("steps", []).append(current_step)

        return result

    @staticmethod
    def _coerce_value(raw: str) -> Any:
        """Convert a raw string value into a typed value where possible."""
        value: Any = raw
        if raw:
            try:
                value = float(raw)
            except ValueError:
                if raw.lower() in ("true", "false"):
                    value = raw.lower() == "true"
                elif raw.startswith("[") and raw.endswith("]"):
                    value = [v.strip().strip("'\"") for v in raw[1:-1].split(",") if v.strip()]
        return value
