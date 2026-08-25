#!/usr/bin/env python
"""CI test configuration loader.

This module is automatically imported when running tests in CI environment.
It sets up the test environment with mocked ML models and test authentication.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Only run in CI environment
if not os.getenv("CI") and not os.getenv("GITHUB_ACTIONS"):
    # Not in CI, don't apply mocking
    pass
else:
    # In CI - apply mocking and test configuration
    import json
    import os
    import sys
    from unittest.mock import patch

    # Add src to path for imports
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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

    # Set test AUTH_USERS
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
    os.environ["JWT_REFRESH_EXPIRATION_DAYS"] = "7"
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DEBUG"] = "true"

    # Mock ML models
    class MockMLModel:
        """Mock ML model for CI testing."""

        def __init__(self, *args, **kwargs):
            self._model = None

        def predict(self, x):
            import numpy as np

            n = x.shape[0] if hasattr(x, "shape") else len(x)
            return np.zeros(n, dtype=int)

        def predict_proba(self, x):
            import numpy as np

            n = x.shape[0] if hasattr(x, "shape") else len(x)
            return np.column_stack([np.ones(n) * 0.9, np.ones(n) * 0.1])

        def fit(self, x, y):
            return self

        def decision_function(self, x):
            import numpy as np

            n = x.shape[0] if hasattr(x, "shape") else len(x)
            return np.zeros(n)

    # Apply patches

    _patches = []

    # Patch sklearn models
    _patches.append(patch("q_guardian.ml.models.anomaly.IsolationForest", MockMLModel))
    _patches.append(patch("q_guardian.ml.models.classifier.RandomForestClassifier", MockMLModel))
    _patches.append(patch("q_guardian.ml.models.classifier.XGBClassifier", MockMLModel))
    _patches.append(patch("sklearn.ensemble.IsolationForest", MockMLModel))
    _patches.append(patch("sklearn.ensemble.RandomForestClassifier", MockMLModel))

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
    os.environ["JWT_REFRESH_EXPIRATION_DAYS"] = "7"
    os.environ["ENVIRONMENT"] = "testing"
    os.environ["DEBUG"] = "true"

    # Mock hash_password for tests
    import q_guardian.security.auth as auth_module

    def mock_hash_password(password: str) -> str:
        return "test_hash"

    auth_module.hash_password = mock_hash_password

    # Reset auth singletons to pick up new AUTH_USERS
    if hasattr(auth_module, "reset_auth_singletons"):
        auth_module.reset_auth_singletons()

    print("✓ CI test environment configured with mocked ML models and test auth")
