"""
Snowflake Client — connection and query utilities for the Schema-Change
Impact Simulator.

Configuration is read entirely from environment variables (no secrets in code):
  SNOWFLAKE_ACCOUNT   — e.g. "xy12345.us-east-1"
  SNOWFLAKE_USER      — e.g. "PRERNA_USER"
  SNOWFLAKE_PASSWORD  — Snowflake password
  SNOWFLAKE_WAREHOUSE — e.g. "COMPUTE_WH"
  SNOWFLAKE_DATABASE  — e.g. "ANALYTICS" (database containing the PRERNA schema)
  SNOWFLAKE_ROLE      — optional, uses the user's default role if not set

How downstream dependencies are approximated:
  Since we don't assume a dedicated lineage table exists, we scan
  INFORMATION_SCHEMA.VIEWS for views whose SQL definition text references
  the target table.  Direct (1-hop) = views that mention the table name.
  Transitive (2-hop) = views that mention any of those direct views.
  This is a conservative approximation suitable for the hackathon demo.
"""

from __future__ import annotations

import os
from typing import Any


class SnowflakeConnectionError(Exception):
    """Raised when Snowflake connection fails or is not configured."""


class SnowflakeClient:
    """Thin wrapper around snowflake-connector-python."""

    def __init__(self) -> None:
        self.account = os.environ.get("SNOWFLAKE_ACCOUNT", "")
        self.user = os.environ.get("SNOWFLAKE_USER", "")
        self.password = os.environ.get("SNOWFLAKE_PASSWORD", "")
        self.warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "")
        self.database = os.environ.get("SNOWFLAKE_DATABASE", "")
        self.role = os.environ.get("SNOWFLAKE_ROLE", "")

        if not all([self.account, self.user, self.password]):
            raise SnowflakeConnectionError(
                "Snowflake credentials not configured. "
                "Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD "
                "environment variables."
            )

    def _connect(self):
        """Create and return a Snowflake connection."""
        try:
            import snowflake.connector
        except ImportError:
            raise SnowflakeConnectionError(
                "snowflake-connector-python is not installed. "
                "Run: pip install snowflake-connector-python"
            )

        conn_params: dict[str, Any] = {
            "account": self.account,
            "user": self.user,
            "password": self.password,
        }
        if self.warehouse:
            conn_params["warehouse"] = self.warehouse
        if self.database:
            conn_params["database"] = self.database
        if self.role:
            conn_params["role"] = self.role

        try:
            return snowflake.connector.connect(**conn_params)
        except Exception as e:
            raise SnowflakeConnectionError(f"Failed to connect to Snowflake: {e}")

    def get_downstream_dependencies(
        self, table_name: str, schema_name: str = "PRERNA"
    ) -> dict[str, int]:
        """Approximate downstream dependencies by scanning INFORMATION_SCHEMA.VIEWS.

        Direct (1-hop): views whose definition references the target table.
        Transitive (2-hop): views that reference any of the direct-dependency views.

        Returns dict with: total_count, direct_count, transitive_count, max_depth.
        """
        conn = self._connect()
        try:
            cursor = conn.cursor()

            # 1-hop: views whose SQL definition mentions the target table
            cursor.execute(
                """
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA = %s
                  AND UPPER(VIEW_DEFINITION) LIKE %s
                """,
                (schema_name.upper(), f"%{table_name.upper()}%"),
            )
            direct_views = [row[0] for row in cursor.fetchall()]
            direct_count = len(direct_views)

            # 2-hop: views that reference any direct-dependency view
            transitive_count = 0
            if direct_views:
                for view_name in direct_views:
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM INFORMATION_SCHEMA.VIEWS
                        WHERE TABLE_SCHEMA = %s
                          AND UPPER(VIEW_DEFINITION) LIKE %s
                          AND TABLE_NAME != %s
                        """,
                        (
                            schema_name.upper(),
                            f"%{view_name.upper()}%",
                            view_name.upper(),
                        ),
                    )
                    transitive_count += cursor.fetchone()[0]

            total_count = direct_count + transitive_count
            max_depth = 0
            if direct_count > 0:
                max_depth = 1
            if transitive_count > 0:
                max_depth = 2

            return {
                "total_count": total_count,
                "direct_count": direct_count,
                "transitive_count": transitive_count,
                "max_depth": max_depth,
            }
        finally:
            conn.close()
