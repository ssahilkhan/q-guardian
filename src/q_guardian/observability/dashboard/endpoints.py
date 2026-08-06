from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.observability.data import TimeWindow
from q_guardian.observability.exceptions import DashboardError

if TYPE_CHECKING:
    from q_guardian.observability.dashboard.api import DashboardAPI

logger = structlog.get_logger("observability.dashboard.endpoints")


class DashboardEndpoints:
    def __init__(self, api: DashboardAPI) -> None:
        self._api = api
        logger.info("dashboard_endpoints_initialized")

    def metrics_endpoint(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self._api.get_metrics(query=query)
        except DashboardError:
            raise
        except Exception as e:
            logger.error("metrics_endpoint_error", error=str(e))
            raise DashboardError(
                message="Metrics endpoint failed",
                details={"error": str(e)},
            ) from e

    def health_endpoint(self) -> dict[str, Any]:
        try:
            return self._api.get_health()
        except DashboardError:
            raise
        except Exception as e:
            logger.error("health_endpoint_error", error=str(e))
            raise DashboardError(
                message="Health endpoint failed",
                details={"error": str(e)},
            ) from e

    def analytics_endpoint(
        self, start: str | None = None, end: str | None = None
    ) -> dict[str, Any]:
        try:
            time_window = None
            if start is not None or end is not None:
                now = datetime.now(UTC)
                start_dt = datetime.fromisoformat(start) if start else now
                end_dt = datetime.fromisoformat(end) if end else now
                time_window = TimeWindow(start=start_dt, end=end_dt)
            return self._api.get_analytics(time_window=time_window)
        except DashboardError:
            raise
        except Exception as e:
            logger.error("analytics_endpoint_error", error=str(e))
            raise DashboardError(
                message="Analytics endpoint failed",
                details={"error": str(e)},
            ) from e

    def runtime_endpoint(self) -> dict[str, Any]:
        try:
            return self._api.get_runtime()
        except DashboardError:
            raise
        except Exception as e:
            logger.error("runtime_endpoint_error", error=str(e))
            raise DashboardError(
                message="Runtime endpoint failed",
                details={"error": str(e)},
            ) from e

    def providers_endpoint(self) -> dict[str, Any]:
        try:
            return self._api.get_providers()
        except DashboardError:
            raise
        except Exception as e:
            logger.error("providers_endpoint_error", error=str(e))
            raise DashboardError(
                message="Providers endpoint failed",
                details={"error": str(e)},
            ) from e

    def incidents_endpoint(self, limit: int = 50) -> dict[str, Any]:
        try:
            return self._api.get_incidents(limit=limit)
        except DashboardError:
            raise
        except Exception as e:
            logger.error("incidents_endpoint_error", error=str(e))
            raise DashboardError(
                message="Incidents endpoint failed",
                details={"error": str(e)},
            ) from e

    def responses_endpoint(self, limit: int = 50) -> dict[str, Any]:
        try:
            return self._api.get_responses(limit=limit)
        except DashboardError:
            raise
        except Exception as e:
            logger.error("responses_endpoint_error", error=str(e))
            raise DashboardError(
                message="Responses endpoint failed",
                details={"error": str(e)},
            ) from e

    def policies_endpoint(self) -> dict[str, Any]:
        try:
            return self._api.get_policies()
        except DashboardError:
            raise
        except Exception as e:
            logger.error("policies_endpoint_error", error=str(e))
            raise DashboardError(
                message="Policies endpoint failed",
                details={"error": str(e)},
            ) from e

    def plugins_endpoint(self) -> dict[str, Any]:
        try:
            return self._api.get_plugins()
        except DashboardError:
            raise
        except Exception as e:
            logger.error("plugins_endpoint_error", error=str(e))
            raise DashboardError(
                message="Plugins endpoint failed",
                details={"error": str(e)},
            ) from e

    def alerts_endpoint(self) -> dict[str, Any]:
        try:
            return self._api.get_alerts()
        except DashboardError:
            raise
        except Exception as e:
            logger.error("alerts_endpoint_error", error=str(e))
            raise DashboardError(
                message="Alerts endpoint failed",
                details={"error": str(e)},
            ) from e

    def snapshot_endpoint(self) -> dict[str, Any]:
        try:
            return self._api.get_snapshot()
        except DashboardError:
            raise
        except Exception as e:
            logger.error("snapshot_endpoint_error", error=str(e))
            raise DashboardError(
                message="Snapshot endpoint failed",
                details={"error": str(e)},
            ) from e
