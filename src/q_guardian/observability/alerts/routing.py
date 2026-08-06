"""Alert routing for Q-Guardian Observability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from q_guardian.observability.data import Alert
    from q_guardian.observability.enums import AlertSeverity

logger = structlog.get_logger(__name__)


class AlertRouter:
    def __init__(self) -> None:
        self._routes: dict[str, list[str]] = {}
        self._default_channels: list[str] = []
        logger.info("alert_router_initialized")

    def add_route(self, severity: AlertSeverity, channel: str) -> None:
        key = severity.value
        if key not in self._routes:
            self._routes[key] = []
        if channel not in self._routes[key]:
            self._routes[key].append(channel)
            logger.info("alert_route_added", severity=key, channel=channel)

    def remove_route(self, severity: AlertSeverity, channel: str) -> bool:
        key = severity.value
        channels = self._routes.get(key, [])
        if channel in channels:
            channels.remove(channel)
            if not channels:
                del self._routes[key]
            logger.info("alert_route_removed", severity=key, channel=channel)
            return True
        logger.warning("alert_route_remove_not_found", severity=key, channel=channel)
        return False

    def get_routes(self, severity: AlertSeverity) -> list[str]:
        return list(self._routes.get(severity.value, []))

    def get_all_routes(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._routes.items()}

    def route_alert(self, alert: Alert) -> list[str]:
        channels = list(self._routes.get(alert.severity.value, []))
        if not channels:
            channels = list(self._default_channels)
        logger.info(
            "alert_routed",
            alert_id=alert.alert_id,
            severity=alert.severity.value,
            channels=channels,
        )
        return channels

    def set_default_channels(self, channels: list[str]) -> None:
        self._default_channels = list(channels)
        logger.info("default_channels_set", channels=channels)

    def get_default_channels(self) -> list[str]:
        return list(self._default_channels)

    def to_dict(self) -> dict[str, Any]:
        return {
            "routes": self.get_all_routes(),
            "default_channels": list(self._default_channels),
        }
