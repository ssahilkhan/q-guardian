"""Dataset authentication and access control for external dataset providers.

Provides a centralized authentication layer for dataset downloads,
initially prioritizing Hugging Face Hub.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from q_guardian.benchmark.registry import DatasetSpec


class DatasetAccessType(Enum):
    """Classification of dataset access requirements."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    GATED = "gated"
    PRIVATE = "private"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class AuthProvider(Enum):
    """Supported authentication providers."""

    HUGGINGFACE = "huggingface"


@dataclass(frozen=True)
class DatasetAccessInfo:
    """Information about a dataset's access requirements.

    Attributes:
        dataset_id: Stable identifier for the dataset.
        access_type: Classification of access requirements.
        provider: Authentication provider (if applicable).
        requires_token: Whether a token is required.
        message: Human-readable explanation of access status.
        homepage: Dataset homepage URL for manual verification.
    """

    dataset_id: str
    access_type: DatasetAccessType
    provider: AuthProvider | None = None
    requires_token: bool = False
    message: str = ""
    homepage: str = ""

    @property
    def is_accessible(self) -> bool:
        """Whether the dataset can be accessed with current credentials."""
        return self.access_type in (
            DatasetAccessType.PUBLIC,
            DatasetAccessType.AUTHENTICATED,
        )

    @property
    def needs_user_action(self) -> bool:
        """Whether user action is needed (accept terms, request access, etc.)."""
        return self.access_type in (
            DatasetAccessType.GATED,
            DatasetAccessType.AUTHENTICATED,
            DatasetAccessType.PRIVATE,
        )


@dataclass(frozen=True)
class AuthConfig:
    """Configuration for dataset authentication.

    Attributes:
        hf_token: Hugging Face token (prefer HF_TOKEN environment variable).
        token_env_var: Environment variable name for HF token.
    """

    hf_token: str | None = None
    token_env_var: str = "HF_TOKEN"

    @classmethod
    def from_env(cls, token_env_var: str = "HF_TOKEN") -> AuthConfig:
        """Create config from environment variables.

        Args:
            token_env_var: Environment variable name for the HF token.

        Returns:
            AuthConfig instance with token from environment.
        """
        return cls(
            hf_token=os.environ.get(token_env_var),
            token_env_var=token_env_var,
        )

    @classmethod
    def from_config(cls, hf_token: str | None, token_env_var: str = "HF_TOKEN") -> AuthConfig:
        """Create config from explicit token and environment fallback.

        Args:
            hf_token: Explicit Hugging Face token (e.g., from config file).
            token_env_var: Environment variable name for fallback.

        Returns:
            AuthConfig instance with resolved token.
        """
        return cls(
            hf_token=hf_token or os.environ.get(token_env_var),
            token_env_var=token_env_var,
        )

    def resolve_token(self) -> str | None:
        """Return the resolved token, preferring explicit over environment.

        Returns:
            The token string if available, None otherwise.
        """
        return self.hf_token


class DatasetAuthResolver:
    """Resolves dataset access requirements and authentication status.

    Centralizes authentication logic for dataset providers, initially
    supporting Hugging Face Hub. Determines whether a dataset is public,
    gated, private, or otherwise restricted.
    """

    HF_TOKEN_ENV_VAR = "HF_TOKEN"
    HF_HUB_URL = "https://huggingface.co"

    def __init__(self, config: AuthConfig | None = None) -> None:
        """Initialize the resolver.

        Args:
            config: Authentication configuration. Defaults to environment.
        """
        self._config = config or AuthConfig.from_env()

    @property
    def token(self) -> str | None:
        """Return the current authentication token (never logged)."""
        return self._config.resolve_token()

    @property
    def has_token(self) -> bool:
        """Check if a token is configured."""
        return self.token is not None

    def classify_access(self, spec: DatasetSpec) -> DatasetAccessInfo:
        """Classify the access requirements for a dataset specification.

        Args:
            spec: Dataset specification from the registry.

        Returns:
            DatasetAccessInfo with classification and guidance.
        """
        if spec.format != "hf":
            return DatasetAccessInfo(
                dataset_id=spec.dataset_id,
                access_type=DatasetAccessType.PUBLIC,
                message="Local dataset, no authentication required",
                homepage=spec.homepage,
            )

        if spec.requires_token:
            if self.has_token:
                return DatasetAccessInfo(
                    dataset_id=spec.dataset_id,
                    access_type=DatasetAccessType.AUTHENTICATED,
                    provider=AuthProvider.HUGGINGFACE,
                    requires_token=True,
                    message=(
                        f"Dataset requires authentication. Token configured. "
                        f"Complete any required terms acceptance or access approval "
                        f"at {spec.homepage}"
                    ),
                    homepage=spec.homepage,
                )
            return DatasetAccessInfo(
                dataset_id=spec.dataset_id,
                access_type=DatasetAccessType.GATED,
                provider=AuthProvider.HUGGINGFACE,
                requires_token=True,
                message=(
                    f"This dataset is gated on Hugging Face. "
                    f"Configure HF_TOKEN after completing any required access "
                    f"approval at {spec.homepage}"
                ),
                homepage=spec.homepage,
            )

        return DatasetAccessInfo(
            dataset_id=spec.dataset_id,
            access_type=DatasetAccessType.PUBLIC,
            message="Public dataset, no authentication required",
            homepage=spec.homepage,
        )

    def validate_token(self) -> tuple[bool, str]:
        """Validate the configured token format (basic sanity check).

        Note: This does NOT verify the token with the provider.
        Use check_dataset_access() for actual validation.

        Returns:
            Tuple of (is_valid, message).
        """
        token = self.token
        if not token:
            return False, "No token configured. Set HF_TOKEN environment variable."

        if not token.startswith(("hf_", "hf-")):
            return False, (
                "Token format appears invalid. Hugging Face tokens typically start with 'hf_'."
            )

        if len(token) < 20:
            return False, "Token appears too short to be valid."

        return True, "Token format appears valid."

    def get_auth_headers(self) -> dict[str, str]:
        """Get HTTP headers for authenticated requests.

        Returns:
            Dictionary with Authorization header if token available, empty dict otherwise.
        """
        token = self.token
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def check_dataset_access(
        self,
        spec: DatasetSpec,
        *,
        allow_offline: bool = False,
    ) -> DatasetAccessInfo:
        """Classify dataset access from registry metadata and token presence.

        Classification reflects what the registry declares as required
        (``requires_token``) combined with whether a token is configured.
        It does not perform a lightweight provider request here; genuine
        server-side verification happens when rows are actually downloaded
        (see :class:`q_guardian.benchmark.download.DatasetDownloader`).

        Args:
            spec: Dataset specification to check.
            allow_offline: Accepted for API compatibility; classification is
                identical with or without it because no network call is made.

        Returns:
            DatasetAccessInfo with access classification.
        """
        if spec.format != "hf":
            return DatasetAccessInfo(
                dataset_id=spec.dataset_id,
                access_type=DatasetAccessType.PUBLIC,
                message="Local dataset, no authentication required",
                homepage=spec.homepage,
            )

        if not spec.requires_token:
            return DatasetAccessInfo(
                dataset_id=spec.dataset_id,
                access_type=DatasetAccessType.PUBLIC,
                message="Public dataset, no authentication required",
                homepage=spec.homepage,
            )

        if not self.has_token:
            return DatasetAccessInfo(
                dataset_id=spec.dataset_id,
                access_type=DatasetAccessType.GATED,
                provider=AuthProvider.HUGGINGFACE,
                requires_token=True,
                message=(
                    f"This dataset is gated on Hugging Face. "
                    f"Configure HF_TOKEN after completing any required access "
                    f"approval at {spec.homepage}"
                ),
                homepage=spec.homepage,
            )

        return DatasetAccessInfo(
            dataset_id=spec.dataset_id,
            access_type=DatasetAccessType.AUTHENTICATED,
            provider=AuthProvider.HUGGINGFACE,
            requires_token=True,
            message=(
                f"Dataset requires authentication. Token configured. "
                f"Complete any required terms acceptance or access approval "
                f"at {spec.homepage}"
            ),
            homepage=spec.homepage,
        )


def create_auth_resolver(
    hf_token: str | None = None,
    token_env_var: str = "HF_TOKEN",
) -> DatasetAuthResolver:
    """Factory function to create an authentication resolver.

    Args:
        hf_token: Explicit Hugging Face token (e.g., from config).
        token_env_var: Environment variable name for fallback.

    Returns:
        Configured DatasetAuthResolver instance.
    """
    config = AuthConfig.from_config(hf_token, token_env_var)
    return DatasetAuthResolver(config)
