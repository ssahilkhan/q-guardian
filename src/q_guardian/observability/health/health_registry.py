from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.enums import HealthStatus
from q_guardian.utils.uuid_utils import generate_uuid

if TYPE_CHECKING:
    from q_guardian.observability.data import HealthStatusModel

logger = structlog.get_logger("observability.health_registry")


class HealthRegistry:
    def __init__(self) -> None:
        self._components: dict[str, HealthStatusModel] = {}
        self._registry_id: str = generate_uuid()

    @property
    def registry_id(self) -> str:
        return self._registry_id

    def register(self, name: str, component: HealthStatusModel) -> None:
        self._components[name] = component
        logger.info(
            "component_registered",
            registry_id=self._registry_id,
            component=name,
            status=component.status.value,
        )

    def unregister(self, name: str) -> bool:
        if name in self._components:
            del self._components[name]
            logger.info(
                "component_unregistered",
                registry_id=self._registry_id,
                component=name,
            )
            return True
        return False

    def get(self, name: str) -> HealthStatusModel | None:
        return self._components.get(name)

    def list_all(self) -> dict[str, HealthStatusModel]:
        return dict(self._components)

    def count(self) -> int:
        return len(self._components)

    def get_healthy_count(self) -> int:
        return sum(1 for c in self._components.values() if c.status == HealthStatus.HEALTHY)

    def get_unhealthy_count(self) -> int:
        return sum(1 for c in self._components.values() if c.status == HealthStatus.UNHEALTHY)

    def get_degraded_count(self) -> int:
        return sum(1 for c in self._components.values() if c.status == HealthStatus.DEGRADED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_id": self._registry_id,
            "count": self.count(),
            "healthy": self.get_healthy_count(),
            "unhealthy": self.get_unhealthy_count(),
            "degraded": self.get_degraded_count(),
            "components": {
                name: component.model_dump(mode="json")
                for name, component in self._components.items()
            },
        }
