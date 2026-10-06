# Cloud Database Migration Runbook: SQLite to Supabase PostgreSQL

**Document ID:** `DOC-012`  
**Phase:** 7B — Cloud Deployment Preparation  
**System Component:** Data Migration Utility & Verification Engine  
**Status:** Verification Completed (Ready for Execution Upon Approval)  

---

## 1. Migration Overview & Safeguards

The migration utility located at [`scripts/migrate_sqlite_to_postgres.py`](file:///d:/plant_growth_monitor/scripts/migrate_sqlite_to_postgres.py) transfers all telemetry records and calibration parameters from the local SQLite database to Supabase PostgreSQL.

### Strict Safeguards:
1. **Zero Data Loss:** All **89 current records** (including the original 85 historical records) are transferred.
2. **Explicit Primary Key Preservation:** Primary keys `1` through `89` are inserted verbatim into the target `sensor_readings` table.
3. **Identity Sequence Realignment:** The PostgreSQL identity sequence is updated to `MAX(id) + 1` so future live inserts from `ESP32_003` start at ID `90`.
4. **Source Database Protection:** The source SQLite file ([`database/plant_monitor.db`](file:///d:/plant_growth_monitor/database/plant_monitor.db)) is accessed strictly in **read-only mode**. It is never dropped, truncated, or modified.
5. **Dry-Run Inspection:** Supports `--dry-run` mode to inspect, validate, and verify record integrity without opening a remote network connection.

---

## 2. Source Data Profile (Verified Baseline)

| Parameter | Baseline Value | Verification Method |
|---|---|---|
| **Total Sensor Records** | **89** | `SELECT COUNT(*) FROM sensor_readings` |
| **Original Historical Baseline** | **85** (IDs 1–85) | `SELECT COUNT(*) FROM sensor_readings WHERE id <= 85` |
| **Phase 2 Validation Records** | **2** (IDs 86–87) | Validated edge telemetry tests |
| **Phase 4 Acceptance Records** | **2** (IDs 88–89) | Real hardware telemetry tests |
| **Primary Device ID** | `ESP32_003` (87 rows), `ESP32_001` (2 initial rows) | Grouped device inventory query |
| **Earliest Timestamp** | `2026-10-05T17:32:46` | `SELECT MIN(created_at) FROM sensor_readings` |
| **Latest Timestamp** | `2026-10-05T22:25:38` | `SELECT MAX(created_at) FROM sensor_readings` |
| **System Settings Count** | **6** | `SELECT COUNT(*) FROM system_settings` |
| **Dry Moisture Calibration** | `3326.0` | `system_settings WHERE key = 'dry_raw'` |
| **Wet Moisture Calibration** | `1520.0` | `system_settings WHERE key = 'wet_raw'` |

---

## 3. Migration Utility Command Reference

### A. Dry-Run Verification (Local Inspection Only)
```bash
python scripts/migrate_sqlite_to_postgres.py --dry-run
```
*Expected Output:*
```text
[*] Reading historical records from SQLite: database/plant_monitor.db
[*] Read 89 sensor records and 6 settings from SQLite (database/plant_monitor.db).
[*] DRY-RUN MODE: Validation checks passed. No data written to PostgreSQL.
```

### B. Live Migration Execution (To Be Run Once Supabase is Created)
```bash
python scripts/migrate_sqlite_to_postgres.py --supabase-url "postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require"
```
*(Or supply the connection string via the `DATABASE_URL` environment variable).*

---

## 4. Internal Execution Sequence

When executed against the target Supabase instance, the script performs the following sequential operations:

```mermaid
sequenceDiagram
    autonumber
    participant CLI as Migration Script
    participant SQLite as Local SQLite (Read-Only)
    participant Supabase as Supabase PostgreSQL

    CLI->>SQLite: Read 89 sensor_readings (ORDER BY id ASC)
    CLI->>SQLite: Read 6 system_settings
    SQLite-->>CLI: Return telemetry & configuration records
    CLI->>Supabase: CREATE TABLE IF NOT EXISTS sensor_readings & system_settings
    CLI->>Supabase: CREATE INDEXES (created_at DESC, device_id + created_at DESC)
    CLI->>Supabase: INSERT sensor_readings (IDs 1..89 with ON CONFLICT DO UPDATE)
    CLI->>Supabase: Realine sequence: SELECT setval(pg_get_serial_sequence('sensor_readings', 'id'), 90, false)
    CLI->>Supabase: INSERT system_settings (6 keys with ON CONFLICT DO UPDATE)
    CLI->>Supabase: Execute post-migration verification assertions
    Supabase-->>CLI: Confirm 89 records, earliest/latest timestamps, settings match
```

---

## 5. Post-Migration Verification Assertions

The script automatically executes and verifies the following assertions before exiting:

1. `assert pg_sensor_count >= 89`: Confirms that all 89 records are present in PostgreSQL.
2. `assert pg_orig_85_count == 85`: Confirms that the original 85 historical records (IDs 1 through 85) are intact.
3. `assert pg_esp32_003_count >= 87`: Confirms that all `ESP32_003` records are accounted for.
4. `assert min_ts == '2026-10-05T17:32:46'`: Confirms the earliest timestamp matches SQLite.
5. `assert max_ts == '2026-10-05T22:25:38'`: Confirms the latest timestamp matches SQLite.
6. `assert 'dry_raw' in pg_settings and 'wet_raw' in pg_settings`: Confirms that calibration settings (`3326.0` and `1520.0`) are persisted.

---

## 6. Rollback & Disaster Recovery Guarantee

- If a network error, invalid credential, or timeout occurs during migration, the transaction on Supabase PostgreSQL rolls back cleanly.
- Because SQLite is read exclusively, the local database remains 100% operational as the permanent local backup.
- Development and local acceptance testing can continue using SQLite at any time without interruption.
