"""Playbook Registry — manages playbook definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from q_guardian.response.exceptions import PlaybookError

if TYPE_CHECKING:
    from q_guardian.response.data import PlaybookDefinition

logger = structlog.get_logger(__name__)


class PlaybookRegistry:
    """Registry for playbook definitions."""

    def __init__(self) -> None:
        self._playbooks: dict[str, PlaybookDefinition] = {}

    def register(self, playbook: PlaybookDefinition) -> None:
        if playbook.playbook_id in self._playbooks:
            raise PlaybookError(f"Playbook already registered: {playbook.name}")
        self._playbooks[playbook.playbook_id] = playbook
        logger.info("playbook_registered", playbook_id=playbook.playbook_id, name=playbook.name)

    def unregister(self, playbook_id: str) -> bool:
        return self._playbooks.pop(playbook_id, None) is not None

    def get(self, playbook_id: str) -> PlaybookDefinition | None:
        return self._playbooks.get(playbook_id)

    def get_by_name(self, name: str) -> PlaybookDefinition | None:
        for p in self._playbooks.values():
            if p.name == name:
                return p
        return None

    def get_by_trigger(self, trigger: str) -> PlaybookDefinition | None:
        for p in self._playbooks.values():
            if p.enabled and trigger in p.triggers:
                return p
        return None

    def list_playbooks(self) -> list[PlaybookDefinition]:
        return list(self._playbooks.values())

    def list_enabled(self) -> list[PlaybookDefinition]:
        return [p for p in self._playbooks.values() if p.enabled]

    def has(self, playbook_id: str) -> bool:
        return playbook_id in self._playbooks

    def count(self) -> int:
        return len(self._playbooks)

    def clear(self) -> None:
        self._playbooks.clear()
