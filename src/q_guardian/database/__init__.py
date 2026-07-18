"""Database module for Q-Guardian.

Provides MongoDB connection management using the Motor async driver.
"""

from q_guardian.database.client import MongoDBClient, get_database, get_db_client
from q_guardian.database.health import check_database_health

__all__ = [
    "MongoDBClient",
    "check_database_health",
    "get_database",
    "get_db_client",
]
