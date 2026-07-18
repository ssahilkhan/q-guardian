"""Playbook Validator — validates playbook definitions before execution."""

from __future__ import annotations

from q_guardian.response.data import PlaybookDefinition
from q_guardian.response.enums import StepType
from q_guardian.response.exceptions import PlaybookValidationError


class PlaybookValidator:
    """Validates playbook definitions for correctness."""

    def validate(self, playbook: PlaybookDefinition) -> list[str]:
        """Validate a playbook. Returns list of errors (empty = valid)."""
        errors: list[str] = []

        if not playbook.name:
            errors.append("Playbook name is required")

        if not playbook.steps:
            errors.append("Playbook must have at least one step")

        if len(playbook.steps) > 100:
            errors.append(f"Too many steps: {len(playbook.steps)} (max 100)")

        step_ids: set[str] = set()
        step_names: set[str] = set()

        for i, step in enumerate(playbook.steps):
            if not step.name:
                errors.append(f"Step {i}: name is required")
            elif step.name in step_names:
                errors.append(f"Step {i}: duplicate name '{step.name}'")
            else:
                step_names.add(step.name)

            if step.step_id in step_ids:
                errors.append(f"Step {i}: duplicate step_id '{step.step_id}'")
            step_ids.add(step.step_id)

            # Validate dependencies reference existing steps
            for dep in step.depends_on:
                if dep not in step_ids and dep not in step_names:
                    errors.append(
                        f"Step '{step.name}': depends_on '{dep}' references unknown step"
                    )

            # Validate timeout
            if step.timeout_seconds < 0:
                errors.append(f"Step '{step.name}': timeout cannot be negative")

            # Validate retry
            if step.retry_count < 0:
                errors.append(f"Step '{step.name}': retry_count cannot be negative")

        if playbook.timeout_seconds <= 0:
            errors.append("Playbook timeout must be positive")

        return errors

    def is_valid(self, playbook: PlaybookDefinition) -> bool:
        return len(self.validate(playbook)) == 0

    def require_valid(self, playbook: PlaybookDefinition) -> None:
        errors = self.validate(playbook)
        if errors:
            raise PlaybookValidationError(
                f"Playbook validation failed: {'; '.join(errors)}"
            )
