"""Core constants and configuration values for Q-Guardian."""

from typing import Final

APP_TITLE: Final[str] = "Q-Guardian"
APP_DESCRIPTION: Final[str] = (
    "A Hybrid Quantum-Classical Framework for Runtime Security of Autonomous AI Agents"
)
APP_VERSION: Final[str] = "1.1.0"

API_V1_PREFIX: Final[str] = "/api/v1"

HEALTH_ENDPOINT: Final[str] = "/health"
VERSION_ENDPOINT: Final[str] = "/version"
ROOT_ENDPOINT: Final[str] = "/"

CORRELATION_ID_HEADER: Final[str] = "X-Correlation-ID"
REQUEST_ID_HEADER: Final[str] = "X-Request-ID"

MONGODB_MIN_POOL_SIZE: Final[int] = 1
MONGODB_MAX_POOL_SIZE: Final[int] = 10
MONGODB_TIMEOUT_MS: Final[int] = 5000
