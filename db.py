"""
db.py
=====
Unified Database Abstraction Layer for the IoT Plant Growth Monitor.
Supports both:
  1. Local Development / Testing: SQLite (default)
  2. Production Cloud Deployment: PostgreSQL (via DATABASE_URL)

Provides dialect-transparent query execution, parameter translation (? -> %s),
uniform row dictionary access, transaction control, and schema initialization.
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

# Driver imports with graceful fallback
try:
    import sqlite3
except ImportError:
    sqlite3 = None

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None


# Default local database file path
DEFAULT_SQLITE_PATH = os.path.join("database", "plant_monitor.db")


def normalize_database_url(url: Optional[str] = None) -> str:
    """
    Returns a normalized database connection string.
    If url is None or empty, checks the DATABASE_URL environment variable.
    If still unset or 'sqlite', returns the default SQLite file path.
    Fixes Render's default 'postgres://' scheme to 'postgresql://'.
    """
    db_url = url or os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return DEFAULT_SQLITE_PATH

    # Render uses 'postgres://' which SQLAlchemy/psycopg2 requires as 'postgresql://'
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return db_url


def is_postgres_url(db_url: str) -> bool:
    """Returns True if the database URL targets a PostgreSQL server."""
    return db_url.startswith("postgresql://") or db_url.startswith("postgres://")


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Converts driver-specific row representations into clean dicts with ISO timestamps."""
    if row is None:
        return {}
    if isinstance(row, dict):
        d = dict(row)
    elif hasattr(row, "keys"):
        d = dict(row)
    else:
        d = dict(row)

    # Standardize datetime objects into ISO format strings for JSON compatibility
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


class DatabaseCursor:
    """
    Cursor wrapper providing dialect parameter conversion (? -> %s),
    uniform dict row access, and transparent lastrowid support.
    """

    def __init__(self, raw_cursor: Any, is_postgres: bool):
        self.raw_cursor = raw_cursor
        self.is_postgres = is_postgres
        self._lastrowid = None

    def execute(self, sql: str, params: Optional[Union[List, Tuple]] = None) -> "DatabaseCursor":
        if self.is_postgres:
            adapted_sql = sql.replace("?", "%s")
            # For INSERTs without RETURNING, automatically add RETURNING id to capture lastrowid
            clean_sql = adapted_sql.strip().rstrip(";")
            if re.match(r"^\s*INSERT\s+INTO\s+sensor_readings", clean_sql, re.IGNORECASE) and not re.search(r"\breturning\b", clean_sql, re.IGNORECASE):
                clean_sql += " RETURNING id"
                self.raw_cursor.execute(clean_sql, params or ())
                row = self.raw_cursor.fetchone()
                if row:
                    if isinstance(row, dict):
                        self._lastrowid = row.get("id")
                    elif hasattr(row, "keys"):
                        self._lastrowid = row["id"]
                    else:
                        self._lastrowid = row[0]
                return self

            self.raw_cursor.execute(clean_sql, params or ())
            return self
        else:
            self.raw_cursor.execute(sql, params or ())
            self._lastrowid = getattr(self.raw_cursor, "lastrowid", None)
            return self

    @property
    def lastrowid(self) -> Optional[int]:
        return self._lastrowid

    def fetchone(self) -> Optional[Dict[str, Any]]:
        row = self.raw_cursor.fetchone()
        if not row:
            return None
        return _row_to_dict(row)

    def fetchall(self) -> List[Dict[str, Any]]:
        rows = self.raw_cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    def __iter__(self):
        return iter(self.fetchall())


class DatabaseConnection:
    """
    Unified wrapper around an active SQLite or PostgreSQL connection.
    Ensures consistent query execution, parameter formatting, and dict row access.
    """

    def __init__(self, raw_conn: Any, is_postgres: bool):
        self.raw_conn = raw_conn
        self.is_postgres = is_postgres

    def cursor(self) -> DatabaseCursor:
        return DatabaseCursor(self.raw_conn.cursor(), self.is_postgres)

    def commit(self):
        self.raw_conn.commit()

    def rollback(self):
        self.raw_conn.rollback()

    def close(self):
        try:
            self.raw_conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

    def adapt_sql(self, sql: str) -> str:
        """
        Translates SQL statements across dialects:
        - If PostgreSQL: converts '?' parameter markers to '%s'
        - If SQLite: preserves '?' markers
        """
        if self.is_postgres:
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params: Optional[Union[List, Tuple]] = None) -> Any:
        """Executes a SQL statement and returns the raw cursor."""
        cur = self.cursor()
        adapted_sql = self.adapt_sql(sql)
        cur.execute(adapted_sql, params or ())
        return cur

    def fetch_one(self, sql: str, params: Optional[Union[List, Tuple]] = None) -> Optional[Dict[str, Any]]:
        """Executes a query and returns the first row as a dictionary."""
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def fetch_all(self, sql: str, params: Optional[Union[List, Tuple]] = None) -> List[Dict[str, Any]]:
        """Executes a query and returns all rows as a list of dictionaries."""
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def fetch_val(self, sql: str, params: Optional[Union[List, Tuple]] = None) -> Any:
        """Executes a scalar query and returns the single value (e.g. COUNT(*))."""
        cur = self.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return None
        if isinstance(row, dict) or hasattr(row, "keys"):
            return list(dict(row).values())[0]
        return row[0]

    def execute_insert(self, sql: str, params: Optional[Union[List, Tuple]] = None) -> Optional[int]:
        """
        Executes an INSERT statement and reliably returns the generated primary key ID
        across both SQLite (via cursor.lastrowid) and PostgreSQL (via RETURNING id).
        """
        cur = self.cursor()
        if self.is_postgres:
            # Append RETURNING id if not already present
            clean_sql = sql.strip().rstrip(";")
            if not re.search(r"\breturning\b", clean_sql, re.IGNORECASE):
                clean_sql += " RETURNING id"
            adapted_sql = self.adapt_sql(clean_sql)
            cur.execute(adapted_sql, params or ())
            row = cur.fetchone()
            if row:
                if isinstance(row, dict):
                    return row.get("id")
                return row[0]
            return None
        else:
            adapted_sql = self.adapt_sql(sql)
            cur.execute(adapted_sql, params or ())
            return cur.lastrowid

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        """Converts driver-specific row representations into clean dicts with ISO timestamps."""
        if isinstance(row, dict):
            d = dict(row)
        elif hasattr(row, "keys"):
            d = dict(row)
        else:
            d = dict(row)

        # Standardize datetime objects into ISO format strings for JSON compatibility
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d


def get_db(db_url: Optional[str] = None) -> DatabaseConnection:
    """
    Factory creating a wrapped DatabaseConnection for SQLite or PostgreSQL.
    """
    target = normalize_database_url(db_url)

    if is_postgres_url(target):
        if not psycopg2:
            raise RuntimeError("psycopg2 is required to connect to PostgreSQL. Install psycopg2-binary.")
        conn = psycopg2.connect(target, cursor_factory=psycopg2.extras.RealDictCursor)
        return DatabaseConnection(conn, is_postgres=True)

    # Otherwise, SQLite mode
    if not sqlite3:
        raise RuntimeError("sqlite3 module is not available in Python runtime.")

    folder = os.path.dirname(target)
    if folder:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect(target, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass

    return DatabaseConnection(conn, is_postgres=False)


def init_db(db_url: Optional[str] = None) -> None:
    """
    Initializes database schema and default configuration parameters
    for either SQLite or PostgreSQL.
    """
    with get_db(db_url) as db:
        if db.is_postgres:
            # 1. PostgreSQL Schema
            db.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    device_id VARCHAR(64) NOT NULL DEFAULT 'ESP32_003',
                    moisture_raw DOUBLE PRECISION,
                    moisture_percent DOUBLE PRECISION,
                    temperature_c DOUBLE PRECISION,
                    distance_cm DOUBLE PRECISION,
                    plant_height_cm DOUBLE PRECISION,
                    status VARCHAR(32) NOT NULL DEFAULT 'OK',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_sensor_readings_created_at ON sensor_readings (created_at DESC);")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_created ON sensor_readings (device_id, created_at DESC);")

            db.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key VARCHAR(64) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Seed system settings
            seeds = [
                ("dry_raw", "3326.0"),
                ("wet_raw", "1520.0"),
                ("sensor_mount_height_cm", "30.0"),
                ("drying_risk_temp_threshold", "30.0"),
                ("low_moisture_threshold", "25.0"),
                ("device_id", "ESP32_003")
            ]
            for k, v in seeds:
                db.execute("""
                    INSERT INTO system_settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO NOTHING;
                """, [k, v])

        else:
            # 2. SQLite Schema
            db.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL DEFAULT 'ESP32_003',
                    moisture_raw REAL,
                    moisture_percent REAL,
                    temperature_c REAL,
                    distance_cm REAL,
                    plant_height_cm REAL,
                    status TEXT DEFAULT 'OK',
                    created_at TEXT NOT NULL
                );
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_sensor_readings_created_at ON sensor_readings (created_at DESC);")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_created ON sensor_readings (device_id, created_at DESC);")

            db.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            now_iso = datetime.now().isoformat()
            seeds = [
                ("dry_raw", "3326.0"),
                ("wet_raw", "1520.0"),
                ("sensor_mount_height_cm", "30.0"),
                ("drying_risk_temp_threshold", "30.0"),
                ("low_moisture_threshold", "25.0"),
                ("device_id", "ESP32_003")
            ]
            for k, v in seeds:
                db.execute("""
                    INSERT OR IGNORE INTO system_settings (key, value, updated_at)
                    VALUES (?, ?, ?);
                """, [k, v, now_iso])


def upsert_system_setting(db: DatabaseConnection, key: str, value: str, updated_at: Optional[str] = None) -> None:
    """
    Dialect-safe upsert for system_settings table.
    """
    ts = updated_at or datetime.now().isoformat()
    if db.is_postgres:
        db.execute("""
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at;
        """, [key, value, ts])
    else:
        db.execute("""
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO UPDATE
            SET value = excluded.value, updated_at = excluded.updated_at;
        """, [key, value, ts])
