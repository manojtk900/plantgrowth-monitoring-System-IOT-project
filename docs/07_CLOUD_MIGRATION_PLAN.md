# Production Cloud Migration Plan: SQLite to PostgreSQL

**Project:** IoT-Based Plant Growth & Environmental Monitoring System  
**Hardware Node:** ESP32 DevKit V1 (`ESP32_003`)  
**Target Cloud Infrastructure:** Render Web Service (Gunicorn + Flask) + Managed PostgreSQL / Supabase  
**Local Baseline:** Python 3.12, Flask, SQLite (`database/plant_monitor.db`), 89 telemetry records (85 historical preserved + 4 validation/acceptance records)

---

## 1. Executive Summary & Migration Objective

The current local architecture executes Flask against a local SQLite database (`database/plant_monitor.db`). While optimal for zero-dependency local development and testing, SQLite is fundamentally unsuitable for multi-worker containerized cloud deployments (such as Render) due to ephemeral filesystem disks, file locking contention with concurrent Gunicorn worker processes, and the lack of external network accessibility for multi-client dashboards.

This plan details the systematic, non-destructive migration to a cloud-native architecture:
$$\text{ESP32\_003} \xrightarrow[\text{JSON payload}]{\text{HTTPS POST}} \text{Render Flask Gateway (Gunicorn)} \xrightarrow[\text{SQL Connection Pool}]{\text{psycopg}} \text{Managed PostgreSQL Database}$$

---

## 2. Comprehensive Codebase Audit: SQLite Dependencies

A full codebase inspection identified the following components coupled to SQLite that must be abstracted for dual SQLite/PostgreSQL compatibility:

### 2.1 Driver & Connection Lifecycle
| Location | Current Implementation (SQLite) | Required Cloud Implementation (PostgreSQL) | Migration Strategy |
| :--- | :--- | :--- | :--- |
| `app.py:12` | `import sqlite3` | `psycopg2-binary` or `psycopg` (v3) connection pool | Dynamic driver loader based on `DATABASE_URL` scheme (`sqlite:` vs `postgres:` / `postgresql:`) |
| `app.py:48-65` | `get_db()` opens `sqlite3.connect(DATABASE_PATH)` with `PRAGMA busy_timeout = 5000` and `PRAGMA journal_mode = WAL` | Connection pool / client connection to remote PostgreSQL socket with SSL mode `require` | Encapsulate connection factory in `db.py` abstraction layer |
| `app.py:59` | `connection.row_factory = sqlite3.Row` | Dict-like row access (`RealDictCursor` or `dict_row`) | Provide uniform row dictionary mapping helper across drivers |

### 2.2 SQL Dialect & Syntax Incompatibilities
| Feature | SQLite Syntax | PostgreSQL Syntax | Solution |
| :--- | :--- | :--- | :--- |
| **Parameter Placeholders** | Positional `?` placeholders (`WHERE id = ?`) | Positional `%s` or `$1` placeholders | Query abstraction helper auto-translates `?` to `%s` when executing against PostgreSQL |
| **Auto-Increment Primary Key** | `id INTEGER PRIMARY KEY AUTOINCREMENT` | `id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY` or `id SERIAL PRIMARY KEY` | Dialect-aware schema generation in migration script & initialization |
| **Inserted Row ID Retrieval** | `cursor.lastrowid` | `RETURNING id` clause on `INSERT` | `execute_insert()` abstraction helper appending `RETURNING id` for Postgres or using `cur.lastrowid` for SQLite |
| **Upsert / Conflict Handling** | `INSERT OR IGNORE INTO system_settings ...` | `INSERT INTO system_settings ... ON CONFLICT (key) DO NOTHING` | Standardize on standard ANSI `ON CONFLICT (key) DO NOTHING` (supported in SQLite 3.24+ and all PostgreSQL versions) |
| **Table Schema Introspection** | `PRAGMA table_info(sensor_readings)` | `information_schema.columns` or `to_regclass` | Schema checks abstracted or executed via unified utility |

### 2.3 Hardcoded Development Configuration & Paths
| File & Line | Current Development Value | Production Target |
| :--- | :--- | :--- |
| `app.py:48-49` | `DATABASE_FOLDER = "database"`, `DATABASE_PATH = ...` | Configured via `DATABASE_URL` environment variable |
| `app.py:785` | `app.run(debug=True, host="0.0.0.0", port=5000)` | Production entrypoint via Gunicorn: `gunicorn app:app --bind 0.0.0.0:$PORT` |
| `app.py:debug` | `debug=True` hardcoded in `__main__` | Controlled by `FLASK_DEBUG=0` / `FLASK_ENV=production` |
| Root | Missing `Procfile` / startup command | Add production startup configuration |
| Root | Missing `render.yaml` | Add Render Blueprint infrastructure definition |
| Root | Implicit Python version | Pin Python 3.12 explicitly in `.python-version` |

---

## 3. Database Abstraction Strategy: Zero Disruption to Local Testing

To guarantee that **all 34 existing automated unit tests and local development workflows continue passing uninterrupted**, the application must **NOT** forcibly replace SQLite.

Instead, a unified Database Gateway (`db.py` / `DatabaseAdapter`) is implemented:
1. **Environment-Driven Routing**:
   - If `DATABASE_URL` is unset or begins with `sqlite:///`: The application operates in **SQLite Development Mode**, preserving `database/plant_monitor.db` and local testing isolation.
   - If `DATABASE_URL` begins with `postgresql://` or `postgres://`: The application operates in **PostgreSQL Production Mode**.
2. **Dialect Transparency**:
   - An intelligent query wrapper intercepts SQL statements:
     ```python
     def adapt_sql(sql_statement: str, is_postgres: bool) -> str:
         if is_postgres:
             # Convert SQLite '?' parameter tokens to PostgreSQL '%s' tokens
             return sql_statement.replace("?", "%s")
         return sql_statement
     ```
3. **Insert ID Abstraction**:
   - For SQLite: `cursor.execute(sql, params); return cursor.lastrowid`
   - For PostgreSQL: Append `RETURNING id` if not present; `cursor.execute(sql, params); return cursor.fetchone()['id']`

---

## 4. Data Migration & Preservation Protocol

### 4.1 Verification Baseline
The local SQLite database contains:
- **Total Records:** 89 rows
- **Original Historical Records:** 85 rows (IDs 1 through 85, from `2026-10-05T17:32:46` to `2026-10-05T21:40:37`)
- **Phase 2 Validation Records:** 2 rows (IDs 86 and 87)
- **Acceptance Test Records:** 2 rows (IDs 88 and 89)
- **Active Microcontroller ID:** `ESP32_003`
- **System Settings:** 6 key-value pairs (`dry_raw`, `wet_raw`, `sensor_mount_height_cm`, `drying_risk_temp_threshold`, `low_moisture_threshold`, `device_id`)

### 4.2 Migration Script Architecture (`scripts/migrate_sqlite_to_postgres.py`)
1. **Source Connect:** Opens `database/plant_monitor.db` in read-only mode.
2. **Schema Verification:** Ensures target PostgreSQL database has tables `sensor_readings` and `system_settings` with proper primary keys, data types, and indexes.
3. **Data Transfer with ID Preservation:**
   - Performs a transactional `COPY` or parameterized batch `INSERT` into PostgreSQL `sensor_readings`.
   - Explicitly preserves original sequential IDs (1 to 89).
   - Resets the PostgreSQL identity sequence to `MAX(id) + 1` so future inserts continue seamlessly from ID 90.
4. **Settings Synchronization:**
   - Transfers all key-value rows from `system_settings` to PostgreSQL.
5. **Post-Migration Audit & Assertions:**
   - Assert `COUNT(*) == 89`
   - Assert `MIN(created_at) == '2026-10-05T17:32:46'`
   - Assert `MAX(created_at) == '2026-10-05T22:25:38'`
   - Assert `COUNT(*) WHERE device_id = 'ESP32_003' == 87`
   - Assert `COUNT(*) WHERE device_id = 'ESP32_001' == 2`
   - Assert `dry_raw == 3326.0` and `wet_raw == 1520.0`
6. **Zero Destruction Guarantee:** The SQLite database file `database/plant_monitor.db` remains 100% untouched as the permanent local backup.

---

## 5. Deployment Target Specification: Render Web Service

### 5.1 Service Topology
- **Service Type:** Web Service (`render.yaml`)
- **Runtime:** Python 3.12 (pinned via `.python-version`)
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --workers 2 --threads 4 --timeout 60`
- **Managed Database:** Render PostgreSQL 16 (Free/Starter tier)
- **Auto-injected Variables:** `DATABASE_URL` (standard Postgres connection string)

### 5.2 Environment Variables Matrix
| Variable Name | Environment | Value / Source |
| :--- | :--- | :--- |
| `DATABASE_URL` | Production | Provided automatically by Render managed database |
| `FLASK_ENV` | Production | `production` |
| `FLASK_DEBUG` | Production | `0` |
| `SECRET_KEY` | Production | Generated cryptographically (`secrets.token_hex(32)`) |
| `PORT` | Production | Assigned automatically by Render port binding |

---

## 6. Migration Phasing & Checkpoints

```
[Phase 7.1] Codebase Audit & Migration Plan (Completed)
     ↓
[Phase 7.2] PostgreSQL Data Model & Schema Definition
     ↓
[Phase 7.3] Database Abstraction Layer (SQLite & PostgreSQL Coexistence)
     ↓
[Phase 7.4] Data Migration Script (89 records + settings audit)
     ↓
[Phase 7.5] Verification & Automated Tests
     ↓
[Phase 7.6] Production Packaging (requirements.txt, gunicorn, .env.example)
     ↓
[Phase 7.7] Health Check Endpoint (GET /health)
     ↓
[Phase 7.8] Security Audit & ESP32 HTTPS Specification
     ↓
[Phase 7.9] STOP & Await User Approval Prior to Cloud Deployment
```
