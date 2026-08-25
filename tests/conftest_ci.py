#!/usr/bin/env python
"""CI test configuration loader.

This module is automatically imported when running tests in CI environment.
It sets up the test environment with mocked ML models and test authentication.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

# Only run in CI environment
if not os.getenv("CI") and not os.getenv("GITHUB_ACTIONS"):
    # Not in CI, don't apply mocking
    pass
else:
    # In CI - apply mocking and test configuration
    import json
    from q_guardian.security.auth import hash_password

    # Set test environment variables
    os.environ.setdefault("CI", "true")
    os.environ.setdefault("GITHUB_ACTIONS", "true")
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
    os.environ.setdefault("ENVIRONMENT", "testing")
    os.environ.setdefault("DEBUG", "true")

    # Set test AUTH_USERS
    from q_guardian.security.auth import hash_password
    test_users = {
        "tester": {"password_hash": "test_hash", "roles": ["analyst"]},
        "admin": {"password_hash": "test_hash", "roles": ["admin"]},
        "service": {"password_hash": "test_hash", "roles": ["service"]},
    }
    os.environ["AUTH_USERS"] = json.dumps(test_users)
    os.environ["RATE_LIMIT_ENABLED"] = "false"
    os.environ["LOG_LEVEL"] = "INFO"
    os.environ["SECRET_KEY"] = "test-secret-key-for-ci-only"
    os.environ["JWT_ALGORITHM"] = "HS256"
    os.environ["JWT_EXPIRATION_MINUTES"] = "30"
    os.environ["JWT_REFRESH_EXPIRATION_DAYS": "7"
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DEBUG"] = "true"

    # Mock ML models
    class MockMLModel:
        """Mock ML model for CI testing."""

        def __init__(self, *args, **kwargs):
            self._model = None

        def predict(self, X):
            import numpy as np
            n = X.shape[0] if hasattr(X, 'shape') else len(X)
            return np.zeros(n, dtype=int)

        def predict_proba(self, X):
            import numpy as np
            n = X.shape[0] if hasattr(X, 'shape') else len(X)
            return np.column_stack([np.ones(n) * 0.9, np.ones(n) * 0.1])

        def fit(self, X, y):
            return self

        def decision_function(self, X):
            import numpy as np
            n = X.shape[0] if hasattr(X, 'shape') else len(X)
            return np.zeros(n)

    # Apply patches
    import unittest.mock as mock

    _patches = []

    # Patch sklearn models
    _patches.append(mock.patch("q_guardian.ml.models.anomaly.IsolationForest", MockMLModel))
    _patches.append(mock.patch("q_guardian.ml.models.classifier.RandomForestClassifier", MockMLModel))
    _patches.append(mock.patch("q_guardian.ml.models.classifier.XGBClassifier", MockMLModel))
    _patches.append(mock.patch("sklearn.ensemble.IsolationForest", MockMLModel))
    _patches.append(mock.patch("sklearn.ensemble.RandomForestClassifier", MockMLModel))
    _patches.append(mock.patch("sklearn.ensemble.RandomForestClassifier", MockMLModel))

    for p in _patches:
        p.start()

    # Mock sentence-transformers
    try:
        import sentence_transformers
        class MockSentenceTransformer:
            def __init__(self, *args, **kwargs):
                pass

            def encode(self, texts, *args, **kwargs):
                import numpy as np
                if isinstance(texts, str):
                    texts = [texts]
                return np.random.rand(len(texts), 384).astype(np.float32)

        sentence_transformers.SentenceTransformer = MockSentenceTransformer
    except ImportError:
        pass

    # Set test AUTH_USERS
    import q_guardian.security.auth as auth_module
    original_hash_password = auth_module.hash_password

    def mock_hash_password(password: str) -> str:
        return "test_hash"

    auth_module.hash_password = mock_hash_password

    # Reset auth singletons to pick up new AUTH_USERS
    if hasattr(auth_module, "reset_auth_singletons"):
        auth_module.reset_auth_singletons()

    print("✓ CI test environment configured with mocked ML models and test auth")