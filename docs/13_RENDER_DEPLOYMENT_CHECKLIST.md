# Production Cloud Deployment Checklist & Verification Plan

**Document ID:** `DOC-013`  
**Phase:** 7B — Cloud Deployment Preparation  
**System Architecture:** ESP32_003 ➔ HTTPS ➔ Render Flask Web Service ➔ Supabase PostgreSQL ➔ Dashboard  
**Status:** Staged (Awaiting Explicit User Authorization Before Execution)  

---

## Deployment Rule of Engagement

> [!CRITICAL]
> **DO NOT DEPLOY OUT OF SEQUENCE.**
> Every step in this checklist must be completed and verified before proceeding to the subsequent step.
> **Under no circumstances should the ESP32 firmware be flashed until Step G is verified live in production.**

---

## Sequential Deployment Protocol

```mermaid
graph TD
    A[STEP A: Provision Supabase PostgreSQL] --> B[STEP B: Run Local SQLite Migration]
    B --> C[STEP C: Verify 89 Records in Supabase]
    C --> D[STEP D: Deploy Flask to Render Web Service]
    D --> E[STEP E: Verify GET /health on Render]
    E --> F[STEP F: Verify Render API Endpoints]
    F --> G[STEP G: Verify Web Dashboard in Browser]
    G --> H[STEP H: Flash ESP32 with Cloud HTTPS Endpoint]

    style A fill:#e0f2fe,stroke:#0284c7
    style B fill:#e0f2fe,stroke:#0284c7
    style C fill:#dcfce7,stroke:#16a34a
    style D fill:#fef3c7,stroke:#d97706
    style E fill:#dcfce7,stroke:#16a34a
    style F fill:#dcfce7,stroke:#16a34a
    style G fill:#dcfce7,stroke:#16a34a
    style H fill:#fee2e2,stroke:#dc2626
```

---

### STEP A: Provision Supabase PostgreSQL Database
- [ ] Log in to [Supabase Dashboard](https://supabase.com/dashboard).
- [ ] Create a new project: `plant-growth-monitor-db`.
- [ ] Select region closest to deployment (e.g., `US East / West` or `Frankfurt`).
- [ ] Set a secure database password and save it in a local password manager.
- [ ] Navigate to **Project Settings** ➔ **Database** ➔ **Connection String**.
- [ ] Copy the **Direct Connection URI** (for migration) and **Pooler URI** (for Render Web Service).

---

### STEP B: Run Local Migration to Supabase
- [ ] Open PowerShell in the project directory: `d:\plant_growth_monitor`.
- [ ] Run the migration script against the Supabase Direct Connection URI:
  ```powershell
  .\.venv\Scripts\python scripts/migrate_sqlite_to_postgres.py --supabase-url "postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres?sslmode=require"
  ```
- [ ] Ensure the script exits with status code `0` and outputs `Migration successfully completed and verified`.

---

### STEP C: Verify 89 Records & Configuration in Supabase
- [ ] Open the **Table Editor** or **SQL Editor** in the Supabase Dashboard.
- [ ] Execute:
  ```sql
  SELECT COUNT(*) FROM sensor_readings;
  ```
  **Verification Criteria:** Result must be exactly **`89`**.
- [ ] Execute:
  ```sql
  SELECT MIN(created_at), MAX(created_at) FROM sensor_readings;
  ```
  **Verification Criteria:** Earliest is `2026-10-05T17:32:46`, latest is `2026-10-05T22:25:38`.
- [ ] Execute:
  ```sql
  SELECT * FROM system_settings;
  ```
  **Verification Criteria:** Confirm `dry_raw = 3326.0`, `wet_raw = 1520.0`, `sensor_mount_height_cm = 30.0`.

---

### STEP D: Deploy Flask to Render Web Service
- [ ] Log in to [Render Dashboard](https://dashboard.render.com/).
- [ ] Select **New** ➔ **Web Service** ➔ Connect GitHub repository or deploy via Blueprint using [`render.yaml`](file:///d:/plant_growth_monitor/render.yaml).
- [ ] Configure Web Service Settings:
  - **Name:** `plant-growth-monitor-web`
  - **Environment:** `Python 3`
  - **Region:** Matching Supabase region
  - **Branch:** `main`
  - **Build Command:** `pip install -r requirements.txt`
  - **Start Command:** `gunicorn app:app --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:$PORT`
  - **Health Check Path:** `/health`
- [ ] Add Environment Variables in Render:
  - `PYTHON_VERSION`: `3.12.10`
  - `FLASK_ENV`: `production`
  - `FLASK_DEBUG`: `0`
  - `DATABASE_URL`: `postgresql://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require`
  - `SECRET_KEY`: `<Generate random 32-byte secret>`
  - `PRIMARY_DEVICE_ID`: `ESP32_003`
- [ ] Click **Create Web Service** and await build completion.

---

### STEP E: Verify `/health` on Render
- [ ] Send HTTP GET request to Render service:
  ```bash
  curl -i https://plant-growth-monitor-web.onrender.com/health
  ```
- [ ] **Verification Criteria:**
  - HTTP Status: `200 OK`
  - JSON Body:
    ```json
    {
      "status": "ok",
      "service": "plant_growth_monitor",
      "database": "connected"
    }
    ```

---

### STEP F: Verify All Render API Endpoints
Execute automated curl / HTTP requests against the live Render URL:
- [ ] `GET https://<render-url>/api/latest` ➔ HTTP 200 with `device_id: ESP32_003`
- [ ] `GET https://<render-url>/api/status` ➔ HTTP 200 with dynamic liveness state
- [ ] `GET https://<render-url>/api/history?limit=10` ➔ HTTP 200 with `total: 89`
- [ ] `GET https://<render-url>/api/history/export` ➔ HTTP 200 with CSV payload (90 lines)
- [ ] `GET https://<render-url>/api/analytics` ➔ HTTP 200 with biological rate displaying `"Insufficient long-term data (< 24h)"`
- [ ] `GET https://<render-url>/api/settings` ➔ HTTP 200 with `dry_raw: 3326.0`, `wet_raw: 1520.0`

---

### STEP G: Verify Web Dashboard in Browser
- [ ] Open `https://<render-url>/` in a web browser.
- [ ] Verify that the Animated Liquid Soil Moisture Tank renders with the latest telemetry value.
- [ ] Verify that Temperature, Distance, Plant Height, and Condition Score display properly.
- [ ] Verify that the Sensor History Log tab displays 89 records with pagination.
- [ ] Verify that the Analytics tab displays valid cards without errors.
- [ ] Open Browser DevTools Console: Ensure **zero JavaScript errors**.

---

### STEP H: ONLY AFTER ALL OF THE ABOVE: Update ESP32 Firmware
> [!CAUTION]
> Execute this step ONLY when Steps A through G have succeeded with 100% pass rates.

- [ ] In ESP32 firmware source:
  - Add SNTP time synchronization (`configTime(0, 0, "pool.ntp.org")`).
  - Ingest the ISRG Root X1 Root CA certificate for Render HTTPS.
  - Initialize `WiFiClientSecure` with `client.setCACert(isrg_root_ca)`.
  - Update endpoint to `https://<render-url>/api/sensor-data`.
- [ ] Compile and flash firmware to `ESP32_003`.
- [ ] Observe live serial monitor at 115200 baud:
  - Wi-Fi connected ➔ SNTP synchronized ➔ TLS handshake successful ➔ HTTP 201 Created returned.
- [ ] Refresh Render dashboard: Verify status indicator turns green (`● ONLINE`) and live telemetry updates.
