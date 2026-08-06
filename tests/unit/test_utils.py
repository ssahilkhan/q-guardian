"""Unit tests for utility modules."""

from __future__ import annotations

import pytest

from q_guardian.utils.datetime_utils import (
    get_current_timestamp,
    get_utc_now,
    to_iso_format,
    utc_timestamp,
)
from q_guardian.utils.helpers import chunk_list, flatten_list, mask_sensitive, none_if_empty
from q_guardian.utils.json_utils import json_dumps, json_loads
from q_guardian.utils.uuid_utils import generate_correlation_id, generate_uuid


class TestUUIDUtils:
    """Tests for UUID generation utilities."""

    def test_generate_uuid_returns_string(self) -> None:
        """Verify UUID generation returns a string."""
        result = generate_uuid()
        assert isinstance(result, str)

    def test_generate_uuid_format(self) -> None:
        """Verify UUID matches v4 format."""
        result = generate_uuid()
        parts = result.split("-")
        assert len(parts) == 5
        assert len(result) == 36

    def test_generate_uuid_uniqueness(self) -> None:
        """Verify multiple UUIDs are unique."""
        uuids = {generate_uuid() for _ in range(100)}
        assert len(uuids) == 100

    def test_correlation_id_length(self) -> None:
        """Verify correlation ID is 12 characters."""
        result = generate_correlation_id()
        assert len(result) == 12

    def test_correlation_id_is_alphanumeric(self) -> None:
        """Verify correlation ID contains only hex characters."""
        result = generate_correlation_id()
        assert result.isalnum()


class TestDatetimeUtils:
    """Tests for datetime utilities."""

    def test_get_utc_now_returns_datetime(self) -> None:
        """Verify UTC now returns a datetime object."""
        from datetime import datetime

        result = get_utc_now()
        assert isinstance(result, datetime)

    def test_utc_timestamp_returns_float(self) -> None:
        """Verify timestamp returns a float."""
        result = utc_timestamp()
        assert isinstance(result, float)

    def test_get_current_timestamp_format(self) -> None:
        """Verify timestamp string contains T separator."""
        result = get_current_timestamp()
        assert "T" in result

    def test_to_iso_format(self) -> None:
        """Verify ISO format conversion."""
        from datetime import UTC, datetime

        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = to_iso_format(dt)
        assert "2026-01-15" in result


class TestJSONUtils:
    """Tests for JSON utilities."""

    def test_json_dumps_returns_bytes(self) -> None:
        """Verify JSON dumps returns bytes."""
        result = json_dumps({"key": "value"})
        assert isinstance(result, bytes)

    def test_json_loads_roundtrip(self) -> None:
        """Verify JSON loads/dumps roundtrip."""
        data = {"name": "Q-Guardian", "version": "0.1.0"}
        dumped = json_dumps(data)
        loaded = json_loads(dumped)
        assert loaded == data

    def test_json_loads_from_string(self) -> None:
        """Verify JSON loads from string."""
        result = json_loads('{"test": true}')
        assert result == {"test": True}


class TestHelpers:
    """Tests for common helper utilities."""

    def test_mask_sensitive_long_string(self) -> None:
        """Verify sensitive string masking."""
        result = mask_sensitive("secret-api-key-12345")
        assert result.startswith("***")
        assert result.endswith("345")

    def test_mask_sensitive_short_string(self) -> None:
        """Verify masking of short strings."""
        result = mask_sensitive("abc", visible_chars=4)
        assert result == "***"

    def test_chunk_list(self) -> None:
        """Verify list chunking."""
        items = [1, 2, 3, 4, 5, 6, 7]
        chunks = chunk_list(items, 3)
        assert len(chunks) == 3
        assert chunks[0] == [1, 2, 3]

    def test_chunk_list_invalid_size(self) -> None:
        """Verify ValueError for invalid chunk size."""
        with pytest.raises(ValueError, match="chunk_size must be at least 1"):
            chunk_list([1, 2, 3], 0)

    def test_flatten_list(self) -> None:
        """Verify list flattening."""
        nested = [[1, 2], [3, 4], [5]]
        result = flatten_list(nested)
        assert result == [1, 2, 3, 4, 5]

    def test_none_if_empty_whitespace(self) -> None:
        """Verify empty string returns None."""
        assert none_if_empty("   ") is None
        assert none_if_empty("") is None
        assert none_if_empty(None) is None

    def test_none_if_empty_valid(self) -> None:
        """Verify valid string passes through."""
        assert none_if_empty("hello") == "hello"
