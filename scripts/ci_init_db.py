#!/usr/bin/env python
"""CI test database initialization script.

Initializes the test MongoDB database with test users from AUTH_USERS env var.
"""

import asyncio
import json
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from q_guardian.database.client import get_db_client
from q_guardian.security.auth import hash_password


async def init_db() -> None:
    """Initialize test database with test users."""
    auth_users_json = os.environ.get("AUTH_USERS")
    if not auth_users_json:
        print("ERROR: AUTH_USERS environment variable not set")
        sys.exit(1)

    try:
        auth_users = json.loads(auth_users_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid AUTH_USERS JSON: {e}")
        sys.exit(1)

    mongodb_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_database = os.environ.get("MONGODB_DATABASE", "q_guardian_test")

    client = get_db_client()
    client._uri = mongodb_uri
    client._database_name = mongodb_database

    try:
        await client.connect()
        db = client.database  # Use property, not method

        # Create test users
        users_collection = db["users"]
        for username, data in json.loads(os.environ["AUTH_USERS"]).items():
            # Ensure password is hashed
            if "password_hash" not in data:
                data["password_hash"] = hash_password(data.get("password", "changeme"))
            await users_collection.update_one(
                {"username": username},
                {"$set": {"username": username, **data}},
                upsert=True,
            )
        print("Test database initialized successfully")

    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(init_db())
