"""JSON serialization utilities for Q-Guardian.

Uses orjson for high-performance JSON operations.
"""

from __future__ import annotations

from typing import Any

import orjson


def json_dumps(data: Any) -> bytes:
    """Serialize data to JSON bytes using orjson.

    Args:
        data: The data to serialize.

    Returns:
        JSON-encoded bytes.
    """
    return orjson.dumps(data)


def json_loads(data: bytes | str) -> Any:
    """Deserialize JSON data using orjson.

    Args:
        data: JSON bytes or string to deserialize.

    Returns:
        Deserialized Python object.
    """
    return orjson.loads(data)


class OrjsonResponse:
    """FastAPI-compatible response class using orjson for serialization.

    Provides faster JSON serialization than the default json module.
    Use as a response_class in FastAPI route decorators.
    """

    @staticmethod
    def encode(data: Any) -> bytes:
        """Encode data to JSON bytes.

        Args:
            data: The data to encode.

        Returns:
            JSON-encoded bytes.
        """
        return orjson.dumps(
            data,
            option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS,
        )
