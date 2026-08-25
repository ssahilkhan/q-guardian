"""Test configuration and mocking for CI environment."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest


# Set test environment before any imports
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGODB_DATABASE", "q_guardian_test")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRATION_MINUTES", "30")
os.environ.setdefault("JWT_REFRESH_EXPIRATION_DAYS", "7")

# Set AUTH_USERS for test authentication
import json
from q_guardian.security.auth import hash_password

test_users = {
    "tester": {"password_hash": hash_password("correct-password"), "roles": ["analyst"]},
    "admin": {"password_hash": hash_password("correct-password"), "roles": ["admin"]},
    "service": {"password_hash": hash_password("service-password"), "roles": ["service"]},
}
os.environ["AUTH_USERS"] = json.dumps(test_users)


# Mock ML models to avoid loading heavy models in CI
class MockMLModel:
    """Mock ML model for CI testing."""

    def __init__(self, *args, **kwargs):
        self._model = None

    def predict(self, X):
        """Return mock predictions."""
        import numpy as np
        n = X.shape[0] if hasattr(X, 'shape') else len(X)
        return np.zeros(n, dtype=int)

    def predict_proba(self, X):
        """Return mock probabilities."""
        import numpy as np
        n = X.shape[0] if hasattr(X, 'shape') else len(X)
        return np.column_stack([np.ones(n) * 0.9, np.ones(n) * 0.1])

    def fit(self, X, y):
        return self

    def decision_function(self, X):
        import numpy as np
        n = X.shape[0] if hasattr(X, 'shape') else len(X)
        return np.zeros(n)


# Apply ML model patches
_patches = []

# Patch IsolationForest
_patches.append(patch("q_guardian.ml.models.anomaly.IsolationForest", MockMLModel))

# Patch RandomForestClassifier
_patches.append(patch("q_guardian.ml.models.classifier.RandomForestClassifier", MockMLModel))

# Patch XGBClassifier
_patches.append(patch("q_guardian.ml.models.classifier.XGBClassifier", MockMLModel))

# Patch sklearn models
_patches.append(patch("sklearn.ensemble.IsolationForest", MockMLModel))
_patches.append(patch("sklearn.ensemble.RandomForestClassifier", MockMLModel))
_patches.append(patch("sklearn.ensemble.RandomForestClassifier", MockMLModel))

# Start all patches
for p in _patches:
    p.start()

# Mock sentence-transformers if imported
try:
    from sentence_transformers import SentenceTransformer
    original_sentence_transformer = SentenceTransformer

    class MockSentenceTransformer:
        def __init__(self, *args, **kwargs):
            pass

        def encode(self, texts, *args, **kwargs):
            import numpy as np
            if isinstance(texts, str):
                texts = [texts]
            return np.random.rand(len(texts), 384).astype(np.float32)

    import sentence_transformers
    sentence_transformers.SentenceTransformer = MockSentenceTransformer
except ImportError:
    pass


# Ensure AUTH_USERS is set for tests
import os
import json
from q_guardian.security.auth import hash_password

test_users = {
    "tester": {"password_hash": "test_hash", "roles": ["analyst"]},
    "admin": {"password_hash": "test_hash", "roles": ["admin"]},
    "service": {"password_hash": "test_hash", "roles": ["service"]},
}
os.environ["AUTH_USERS"] = json.dumps(test_users)
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "true"
os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
os.environ["MONGODB_DATABASE"] = "q_guardian_test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["SECRET_KEY"] = "test-secret-key-for-ci-only"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")


# Monkey-patch hash_password for tests
import q_guardian.security.auth as auth_module
original_hash_password = auth_module.hash_password


def mock_hash_password(password: str) -> str:
    return "test_hash"


auth_module.hash_password = mock_hash_password

# Reset auth singletons to pick up new AUTH_USERS
import q_guardian.security.auth as auth_module
if hasattr(auth_module, "reset_auth_singletons"):
    auth_module.reset_auth_singletons()

print("✓ CI test environment configured with mocked ML models and test auth")