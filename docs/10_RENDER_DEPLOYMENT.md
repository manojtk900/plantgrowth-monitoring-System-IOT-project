# Render Cloud Deployment & ESP32 HTTPS Ingress Guide

**Project:** IoT-Based Plant Growth & Environmental Monitoring System  
**Target Host:** Render Web Service (Free / Starter Tier)  
**Target Database:** Render Managed PostgreSQL 16  
**Edge Microcontroller:** ESP32 DevKit V1 (`ESP32_003`)

---

## 1. Cloud Infrastructure Overview

```
                      ┌─────────────────────────────────────────┐
                      │              PUBLIC INTERNET            │
                      └────────────────────┬────────────────────┘
                                           │
                        HTTPS Port 443     │ TLS 1.2 / 1.3
                     (Let's Encrypt Cert)  │
                                           ▼
┌──────────────────┐               ┌─────────────────────────────────────────┐
│    ESP32_003     │               │           Render Cloud Gateway          │
│ DevKit V1 Edge   ├──────────────►│    • TLS Termination (Reverse Proxy)    │
│ WiFiClientSecure │               │    • Gunicorn WSGI Web Service          │
│ ISRG Root X1 CA  │               │    • Python 3.12 / Flask Application    │
└──────────────────┘               └───────────────────┬─────────────────────┘
                                                       │
                                                       │ Internal Socket / SSL
                                                       ▼
                                   ┌─────────────────────────────────────────┐
                                   │        Managed PostgreSQL 16            │
                                   │    • Persistent Storage Disks           │
                                   │    • sensor_readings (89+ records)      │
                                   │    • system_settings (Calibration)      │
                                   └─────────────────────────────────────────┘
```

---

## 2. Render Deployment Parameters

### 2.1 Service Specifications
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:$PORT`
- **Health Check Path:** `/health` (returns HTTP 200 `{"status": "ok", "database": "connected"}`)
- **Python Version:** `3.12.10` (pinned via `.python-version`)

### 2.2 Managed PostgreSQL Database
- **Database Name:** `plant_monitor_db`
- **User:** `plant_monitor_user`
- **Access URL:** Auto-injected into Web Service as `DATABASE_URL`

### 2.3 Required Environment Variables in Render Dashboard
| Key | Value / Source |
| :--- | :--- |
| `DATABASE_URL` | *Auto-populated from Render Managed Database* |
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `0` |
| `SECRET_KEY` | *Auto-generated 64-character hex string* |
| `PRIMARY_DEVICE_ID` | `ESP32_003` |

---

## 3. Database Migration Procedure (Pre-Deployment)

Before pointing the live ESP32 to the cloud service:
1. Provision the Render PostgreSQL database.
2. Retrieve the external `DATABASE_URL` from the Render dashboard.
3. Run the non-destructive migration script locally:
   ```bash
   python scripts/migrate_sqlite_to_postgres.py --postgres-url "postgresql://<USER>:<PASS>@<HOST>/plant_monitor_db?sslmode=require"
   ```
4. Verify all 89 records and system settings are transferred and verified.

---

## 4. ESP32 Cloud API & HTTPS Ingress Specification

> [!IMPORTANT]
> **Safety Rule:** DO NOT flash or modify the physical ESP32 firmware until the cloud service is fully provisioned and approved. The existing local HTTP Wi-Fi link remains active and tested.

### 4.1 Unchanged API JSON Contract
The cloud API preserves the identical endpoint path and payload structure as local development:
- **Cloud Ingress URL:** `https://<YOUR_RENDER_APP_NAME>.onrender.com/api/sensor-data`
- **HTTP Method:** `POST`
- **Content-Type:** `application/json`
- **Payload Schema:**
  ```json
  {
    "device_id": "ESP32_003",
    "moisture_raw": 3326.0,
    "moisture_percent": null,
    "temperature_c": 27.5,
    "distance_cm": 7.8,
    "plant_height_cm": 22.2,
    "status": "OK"
  }
  ```
- **Backend Responsibility:** The cloud Flask backend continues calculating `moisture_percent` from `moisture_raw` using persisted RSMI calibration. Calibration is never hardcoded on the ESP32.

---

### 4.2 Secure ESP32 TLS Strategy (Zero Insecure Shortcuts)

When transitioning the ESP32 from local HTTP to public cloud HTTPS, **DO NOT** call `client.setInsecure()`. Bypassing certificate checks leaves edge telemetry susceptible to Man-in-the-Middle (MITM) spoofing and false sensor injection.

#### A. Certificate Validation via ISRG Root X1
Render terminates TLS using Let's Encrypt certificates. The root certificate authority for Let's Encrypt is **ISRG Root X1**, valid through the year 2035.

The ESP32 firmware will load this Root CA certificate into flash:
```cpp
// ISRG Root X1 Root CA Certificate (Let's Encrypt)
const char* rootCACertificate = \
"-----BEGIN CERTIFICATE-----\n" \
"MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw\n" \
"TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh\n" \
"cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4\n" \
"WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu\n" \
"ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY\n" \
"MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc\n" \
"h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+\n" \
"0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U\n" \
"A5/TR5d8S5JlCdGwqqPssQuFBlUmPG9Jfyb97QUSGovsmWQ29lxAMNZ9khWoZuVX\n" \
"bqj2irGeI9BFbxLBAg8AtGBWWCnmqNwlKnHWzjy3qqHzdU5QmvZID5AJaUVxHRtR\n" \
"hnnj9lb6pwmKXUZFiBraWh63RDRejPKAxeBemNNgrmNUs2Y6UujYGF1njLM+SI6M\n" \
"G84KA72h6gkUvPQUqdHewP8AUltxQB7z56njJaFX880XJWWD88t36GQgUPAZ++Lg\n" \
"cZnE8vjJZrGS75fUI47VAw5ulinFHNdcb5xYnQElAWx9mtPtk+YKMWoR6IfRLkeQ\n" \
"InwgB77AOfchMBwurKAepBC3FoutdfFGDH526sOp5hg0sHBVFi1LFfuf9sGEtvBC\n" \
"K2vm5zuJWGFIb+ZxgMt0usj3hnxETNd+EZ27afmvxd45b61F50UZZtwBQMG3aXPX\n" \
"Cob6xA0lxHmZlsnH1DAfsDMbqFar53s/5306rfR482i880B4C85b84dHY8h138UM\n" \
"Hl59AH3i26J42f0rU8xggwIDAQABo0wwSjAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T\n" \
"AQH/BAUwAwEB/zAdBgNVHQ4EFgQU5KVaInstance8HnbqW3yE9BR4iBMbQwDQYJKoZI\n" \
"hvcNAQELBQADggIBAK291AtmInstance61TfGvC2A1P...\n" \
"-----END CERTIFICATE-----\n";
```

#### B. Cryptographic Time Synchronization via SNTP
TLS certificate validation requires the ESP32 to know the current real-world time to verify that the server certificate is within its valid date range:
```cpp
#include <WiFiClientSecure.h>

WiFiClientSecure client;

void setupTime() {
    // Synchronize clock with Network Time Protocol servers
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    time_t now = time(nullptr);
    while (now < 1700000000) { // Wait until valid UNIX timestamp acquired
        delay(500);
        now = time(nullptr);
    }
    client.setCACert(rootCACertificate);
}
```

#### C. Credential Segregation
Wi-Fi credentials (`SSID`, `PASSWORD`) and Cloud URL must be declared in a separate uncommitted header (e.g., `secrets.h`) rather than hardcoded in public sketch repositories.
