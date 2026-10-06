# Comprehensive Test Plan

## 1. Quality Assurance Strategy
The testing strategy guarantees that every software change maintains full compatibility with `ESP32_003` while ensuring mathematical correctness, database safety, and visual polish.

---

## 2. Test Matrix

### 2.1 Backend Unit & Integration Tests (`tests/test_backend.py`)

| Test ID | Component | Test Input | Expected Behavior |
| :--- | :--- | :--- | :--- |
| **TC-CALC-01** | Moisture Math | `raw = 3326` (Dry Baseline) | Returns `0.0%`. |
| **TC-CALC-02** | Moisture Math | `raw = 1520` (Wet Baseline) | Returns `100.0%`. |
| **TC-CALC-03** | Moisture Math | `raw = 2423` (Mid-point) | Returns `50.0%`. |
| **TC-CALC-04** | Moisture Clamping | `raw = 3500` (Excessively dry / open circuit) | Clamped to `0.0%` (not negative). |
| **TC-CALC-05** | Moisture Clamping | `raw = 1200` (Submerged) | Clamped to `100.0%` (not $>100\%$). |
| **TC-CALC-06** | Moisture Null | `raw = None` | Returns `None` without exception. |
| **TC-VAL-01** | DS18B20 Disconnect | `temperature_c = -127.0` | Flagged as sensor disconnected; excluded from temp calculations. |
| **TC-VAL-02** | DS18B20 Power-On | `temperature_c = 85.0` | Flagged as uninitialized register. |
| **TC-VAL-03** | Distance Validation | `distance_cm = -5.0` | Rejected or flagged invalid; height not corrupted. |
| **TC-ENG-01** | Drying Risk Engine | `moisture = 15%`, `temp = 32°C` | Returns `High` drying risk. |
| **TC-ENG-02** | Drying Risk Engine | `moisture = 18%`, `temp = 22°C` | Returns `Moderate` drying risk. |
| **TC-ENG-03** | Condition Score | Ideal inputs (Moisture 65%, Temp 24°C) | Returns score $\ge 90$ with clean explanation. |
| **TC-API-01** | `POST /api/sensor-data` | Valid JSON from ESP32 | Returns `201 Created`, records inserted in SQLite. |
| **TC-API-02** | `POST /api/sensor-data` | Empty or malformed payload | Returns `400 Bad Request` with helpful error. |
| **TC-API-03** | `GET /api/latest` | Non-empty database | Returns `200 OK` with complete latest telemetry. |
| **TC-API-04** | `GET /api/status` | Reading received 10s ago | Returns `online: true, state: "ONLINE"`. |
| **TC-API-05** | `GET /api/status` | Last reading $> 5$ minutes ago | Returns `online: false, state: "OFFLINE"`. |

---

## 3. UI/UX Verification Plan
- **Wave Visual Fluidity:** Verify that water wave animation continues horizontally without tearing or lag.
- **Value Update Continuity:** Verify when sensor reading updates from 20% to 60%, the liquid level animates upward smoothly and does not drop to 0% first.
- **Empty State Display:** Disconnect sensor simulation; verify UI displays graceful fallback (`--`).
- **Responsive Layout:** Check desktop (1920x1080), laptop (1366x768), tablet (768x1024), and mobile (375x812) viewports.
