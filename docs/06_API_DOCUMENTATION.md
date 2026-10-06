# REST API Documentation

## 1. Overview & Protocol Guarantee
The Flask backend provides a RESTful JSON API. All existing endpoints and payloads are strictly backwards-compatible with the firmware running on `ESP32_003`.

---

## 2. Endpoints Specification

### 2.1 Ingestion: Add Sensor Reading
- **Endpoint:** `POST /api/sensor-data`
- **Content-Type:** `application/json`
- **Description:** Receives periodic telemetry from the ESP32. Validates values, computes the Relative Soil Moisture Index (RSMI), assigns a server-side timestamp, and persists the record to SQLite.

#### Request Headers
| Header | Value | Description |
| :--- | :--- | :--- |
| `Content-Type` | `application/json` | Mandatory payload format. |

#### Request Payload
```json
{
  "device_id": "ESP32_003",
  "moisture_raw": 3326.0,
  "moisture_percent": null,
  "temperature_c": 27.75,
  "distance_cm": 7.8,
  "plant_height_cm": 22.2,
  "status": "OK"
}
```

#### Validation Rules
1. `moisture_raw`: Expected $0 \le \text{moisture\_raw} \le 4095$. If out of range, stored as null or flagged.
2. `temperature_c`: Discard error codes (e.g. $-127.0^\circ\text{C}$ indicating disconnected DS18B20; $+85.0^\circ\text{C}$ indicating unconverted power-on register).
3. `distance_cm`: Must be $\ge 0.0$.
4. `plant_height_cm`: Clamped to $\ge 0.0$.

#### Success Response (`201 Created`)
```json
{
  "success": true,
  "message": "Sensor reading saved successfully",
  "reading_id": 86,
  "created_at": "2026-10-05T21:55:00",
  "moisture_raw": 3326.0,
  "moisture_percent": 0.0,
  "moisture_status": "Very Dry",
  "drying_risk": "Moderate",
  "health_score": 75
}
```

#### Error Response (`400 Bad Request`)
```json
{
  "success": false,
  "message": "No JSON data received or invalid payload"
}
```

---

### 2.2 Telemetry: Get Latest Reading
- **Endpoint:** `GET /api/latest`
- **Description:** Returns the most recently ingested record from the database.

#### Success Response (`200 OK`)
```json
{
  "success": true,
  "data": {
    "id": 85,
    "device_id": "ESP32_003",
    "moisture_raw": 3335.0,
    "moisture_percent": 0.0,
    "temperature_c": 27.75,
    "distance_cm": 7.8,
    "plant_height_cm": 22.2,
    "moisture_status": "Very Dry",
    "drying_risk": "Moderate",
    "health_score": 75,
    "status": "OK",
    "created_at": "2026-10-05T21:40:37"
  }
}
```

#### Not Found Response (`404 Not Found`)
```json
{
  "success": false,
  "message": "No sensor data available"
}
```

---

### 2.3 Telemetry: Get Sensor History
- **Endpoint:** `GET /api/history`
- **Query Parameters:**
  - `limit` (integer, optional, default: 100, max: 500): Number of records to return.
  - `offset` (integer, optional, default: 0): Pagination offset.
  - `range` (string, optional): `live`, `today`, `7d`, `30d`.

#### Success Response (`200 OK`)
```json
{
  "success": true,
  "count": 85,
  "total": 85,
  "data": [
    {
      "id": 85,
      "device_id": "ESP32_003",
      "moisture_raw": 3335.0,
      "moisture_percent": 0.0,
      "temperature_c": 27.75,
      "distance_cm": 7.8,
      "plant_height_cm": 22.2,
      "status": "OK",
      "created_at": "2026-10-05T21:40:37"
    }
  ]
}
```

---

### 2.4 Diagnostics: Device Connection Status
- **Endpoint:** `GET /api/status`
- **Description:** Evaluates actual telemetry freshness against current server clock.

#### Success Response (`200 OK` - Online)
```json
{
  "success": true,
  "online": true,
  "state": "ONLINE",
  "seconds_since_last_seen": 12,
  "last_update": "2026-10-05T21:40:37",
  "device_id": "ESP32_003"
}
```

#### Success Response (`200 OK` - Stale / Offline)
```json
{
  "success": true,
  "online": false,
  "state": "OFFLINE",
  "seconds_since_last_seen": 750,
  "last_update": "2026-10-05T21:40:37",
  "device_id": "ESP32_003"
}
```

---

### 2.5 Analytics: Summary Statistics
- **Endpoint:** `GET /api/analytics`
- **Description:** Returns aggregate minimum, maximum, average, and trend rates over available historical data.

#### Success Response (`200 OK`)
```json
{
  "success": true,
  "sample_count": 85,
  "time_window": "All Time",
  "moisture": {
    "current": 0.0,
    "avg": 3.4,
    "min": 0.0,
    "max": 100.0,
    "trend": "Stable"
  },
  "temperature": {
    "current": 27.75,
    "avg": 28.1,
    "min": 27.31,
    "max": 30.25,
    "trend": "Stable"
  },
  "plant_growth": {
    "current_height_cm": 22.2,
    "baseline_height_cm": 17.12,
    "total_growth_cm": 5.08,
    "trend": "Growing"
  }
}
```
