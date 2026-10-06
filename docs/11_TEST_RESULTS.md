# Initial Test Results & Audit Verification Report

## 1. Test Execution Summary
- **Audit Date:** October 2026
- **Test Environment:** Windows 10/11, Python 3.12/3.13, Flask 3.1.3, SQLite 3
- **Overall Status:** Baseline Operational; 4 Architecture Gaps Identified

---

## 2. Baseline Verification Log

### 2.1 Database Integrity Audit
- **Database File:** `database/plant_monitor.db`
- **Total Existing Records:** 85 valid rows
- **Device ID:** `ESP32_003` confirmed in all recent records
- **Earliest Record:** `2026-10-05T17:32:46`
- **Latest Record:** `2026-10-05T21:40:37`
- **Physical Sensor Range Observed:**
  - `moisture_raw`: Min 8.0, Max 3367.0
  - `moisture_percent`: Min 0.0%, Max 100.0%
  - `temperature_c`: Min 27.31°C, Max 30.25°C
  - `distance_cm`: 7.80 cm – 12.88 cm
  - `plant_height_cm`: 17.12 cm – 22.20 cm

### 2.2 Mathematical Geometric Relationship Confirmation
- Tested across records: $D_{sensor} + H_{plant} = 30.00\text{ cm} \pm 0.01\text{ cm}$.
- Confirmed: Mount gantry baseline height is exactly $30.0\text{ cm}$.

### 2.3 Identified Deficiencies Under Automated Scrutiny
1. **Device Status Heartbeat Failure:** `GET /api/status` returns `online: True` indefinitely regardless of time elapsed since last transmission.
2. **Chart Destruction Overhead:** `app.js` destroys and re-allocates 3 Chart.js instances every 10 seconds, causing DOM redraw stutter.
3. **Moisture Gauge Limitation:** Currently rendered as a plain horizontal CSS progress bar rather than an animated liquid tank.
4. **Plant Health Explainability Gap:** Deductions are hardcoded without an itemized breakdown.
