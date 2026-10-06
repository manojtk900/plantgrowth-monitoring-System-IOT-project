# Database Design & Migration Specification

## 1. Current SQLite Schema Audit
The existing production database file is located at `database/plant_monitor.db`. It currently contains 85 verified physical sensor records collected from `ESP32_003`.

### 1.1 Existing Table: `sensor_readings`
```sql
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    moisture_raw REAL,
    moisture_percent REAL,
    temperature_c REAL,
    distance_cm REAL,
    plant_height_cm REAL,
    status TEXT,
    created_at TEXT NOT NULL
);
```

### 1.2 Identified Deficiencies in Current Schema
1. **Lack of Secondary Indexes:** No index on `created_at` or `device_id`. Queries like `ORDER BY id DESC LIMIT 100` are acceptable for small datasets, but time-range queries (`WHERE created_at >= ?`) will require full-table scans.
2. **Missing Derived Context Fields:** Metrics such as `moisture_status`, `drying_risk`, and `health_score` are currently calculated ad-hoc on the frontend, making historical analytics and reporting inconsistent.
3. **No Sensor Validation Flag:** No dedicated column for sensor anomaly flags (`VALID`, `TEMP_FAULT`, `ULTRASONIC_DISCONNECTED`).

---

## 2. Non-Destructive Schema Evolution

To preserve all 85+ existing historical records without data loss, the schema is upgraded using non-destructive `ALTER TABLE ADD COLUMN` statements and index additions.

### 2.1 Evolved Schema Definition
```sql
-- Indexes for optimized time-series retrieval
CREATE INDEX IF NOT EXISTS idx_sensor_readings_created_at 
    ON sensor_readings(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_device_created 
    ON sensor_readings(device_id, created_at DESC);

-- Non-destructive column expansions (applied safely if not present)
-- ALTER TABLE sensor_readings ADD COLUMN moisture_status TEXT;
-- ALTER TABLE sensor_readings ADD COLUMN drying_risk TEXT;
-- ALTER TABLE sensor_readings ADD COLUMN health_score INTEGER;
-- ALTER TABLE sensor_readings ADD COLUMN sensor_flags TEXT;
```

---

## 3. Data Dictionary

| Column Name | Data Type | Nullable | Constraints / Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No | `PRIMARY KEY AUTOINCREMENT` | Unique auto-incrementing reading identifier. |
| `device_id` | `TEXT` | No | Default: `'ESP32_003'` | Identifier string of the transmitting edge microcontroller. |
| `moisture_raw` | `REAL` | Yes | Range $[0, 4095]$ | Raw 12-bit ADC value from capacitive soil moisture probe. |
| `moisture_percent` | `REAL` | Yes | Range $[0.0, 100.0]$ | Calibrated Relative Soil Moisture Index (RSMI). |
| `temperature_c` | `REAL` | Yes | Range $[-20.0, 85.0]$ | Ambient/soil temperature measured by DS18B20 in °C. |
| `distance_cm` | `REAL` | Yes | Range $[2.0, 400.0]$ | Raw distance measured by HC-SR04 ultrasonic sensor. |
| `plant_height_cm` | `REAL` | Yes | $\ge 0.0$ | Calculated canopy height ($30.0\text{ cm} - \text{distance\_cm}$). |
| `moisture_status` | `TEXT` | Yes | `'VERY_DRY'`, `'GOOD'`, etc. | Textual moisture classification based on central thresholds. |
| `drying_risk` | `TEXT` | Yes | `'LOW'`, `'MODERATE'`, `'HIGH'` | Temperature-aware evaporative drying risk level. |
| `health_score` | `INTEGER` | Yes | Range $[0, 100]$ | Calculated Environmental Plant Health Condition Score. |
| `status` | `TEXT` | Yes | Default: `'OK'` | Overall hardware transmission status string. |
| `sensor_flags` | `TEXT` | Yes | JSON / comma list | Sensor diagnostic flags (e.g. `'DS18B20_OK,HCSR04_OK'`). |
| `created_at` | `TEXT` | No | ISO 8601 string | Timestamp of record receipt (`YYYY-MM-DDTHH:MM:SS`). |

---

## 4. Query Optimization & Retention
- **Fast Latest Query:** `SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1;`
- **Windowed History:** `SELECT * FROM sensor_readings ORDER BY id DESC LIMIT :limit OFFSET :offset;`
- **Range Summary Query for Analytics:**
  ```sql
  SELECT 
      COUNT(*) AS total_samples,
      AVG(moisture_percent) AS avg_moisture,
      MIN(moisture_percent) AS min_moisture,
      MAX(moisture_percent) AS max_moisture,
      AVG(temperature_c) AS avg_temp,
      MIN(temperature_c) AS min_temp,
      MAX(temperature_c) AS max_temp,
      AVG(plant_height_cm) AS avg_height,
      MAX(plant_height_cm) - MIN(plant_height_cm) AS total_growth
  FROM sensor_readings
  WHERE created_at >= datetime('now', '-24 hours');
  ```
