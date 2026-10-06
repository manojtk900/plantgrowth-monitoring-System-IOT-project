# Supabase Managed PostgreSQL Architecture & Security Guide

**Document ID:** `DOC-011`  
**Phase:** 7B — Cloud Deployment Preparation  
**System Component:** Cloud Database Layer (Supabase PostgreSQL)  
**Status:** Architecture Ready (Awaiting Deployment Authorization)  

---

## 1. Architectural Role & Rationale

In the target cloud architecture:
```
ESP32_003 ────── HTTPS ──────► Render Web Service (Flask + Gunicorn)
                                           │
                                           ▼ (PostgreSQL Wire Protocol / psycopg2)
                                 Supabase PostgreSQL (Port 5432 / 6543)
```

### Why Supabase PostgreSQL over Render Managed PostgreSQL?
1. **Persistent Free Tier:** Render's Free PostgreSQL expires and shuts down after 30 days, followed by deletion after a 14-day grace period. Supabase Free Tier provides a persistent 500 MB database quota without the 30-day auto-expiration constraint, making it ideal for continuous, multi-month agricultural telemetry collection.
2. **Standard PostgreSQL Wire Protocol:** The application connects directly using Python's standard `psycopg2-binary` driver via the PostgreSQL wire protocol.
3. **Zero Proprietary SDK Coupling:** No Supabase JavaScript or Python frontend SDKs are imported. The Flask backend treats Supabase purely as a standard, high-performance PostgreSQL instance.
4. **Built-in Supavisor Connection Pooling:** Supabase includes native connection pooling, which efficiently handles transient connections from serverless or dyno-based web services like Render.

---

## 2. Supabase Connection String Acquisition

To configure the Flask backend, obtain the connection URI from the Supabase Project Dashboard:

1. Log in to [Supabase Console](https://supabase.com/dashboard).
2. Create or select your project (e.g., `plant-growth-monitor-db`).
3. Navigate to: **Project Settings** (gear icon) ➔ **Database**.
4. Scroll to **Connection string** and select the **URI** tab.

### Connection Modes:

| Mode | URI Format | Port | Recommended For |
|---|---|---|---|
| **Direct Connection** | `postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres` | `5432` | Local migration script (`scripts/migrate_sqlite_to_postgres.py`) |
| **Connection Pooler (Session)** | `postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres` | `5432` | Persistent web applications needing prepared statements |
| **Connection Pooler (Transaction)** | `postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres` | `6543` | Scalable stateless API requests on cloud web services (Render) |

> [!TIP]
> **Recommended for Render Web Service:** Use the **Connection Pooler (Transaction mode, port 6543)** or **Session mode (port 5432)** with `?sslmode=require`. Render Free Web Services share IPv4 outbound networks, and the Supavisor pooler domain resolves directly via IPv4/IPv6 dual-stack.

---

## 3. SSL & Transport Security

Supabase mandates SSL/TLS encryption for all external database connections.

- Append `?sslmode=require` to all connection URIs:
  ```text
  postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
  ```
- The backend abstraction layer in [`db.py`](file:///d:/plant_growth_monitor/db.py) passes this configuration to `psycopg2`, ensuring all data transmitted between Render and Supabase is encrypted in transit using TLS 1.3.

---

## 4. Secret Management & Git Hygiene

Under strict project security rules:
- **Never commit `DATABASE_URL`:** Real connection URIs containing passwords must never exist in repository code, Git commits, markdown documentation, or client-side assets.
- **Template Only in Version Control:** The file [`.env.example`](file:///d:/plant_growth_monitor/.env.example) contains generic placeholders:
  ```ini
  DATABASE_URL=postgresql://username:password@hostname:5432/databasename?sslmode=require
  FLASK_ENV=production
  FLASK_DEBUG=0
  SECRET_KEY=change-this-to-a-secure-random-32-byte-hex-string-in-production
  PRIMARY_DEVICE_ID=ESP32_003
  ```
- **Render Environment Variables:** When deploying the web service on Render, paste the Supabase connection string into the `DATABASE_URL` field in the Render dashboard's **Environment** tab. Render stores this as an encrypted secret.
- **`.gitignore` Enforced:** The repository's [`.gitignore`](file:///d:/plant_growth_monitor/.gitignore) excludes `.env`, `*.db`, and `database/*.db`, preventing accidental leaks of local databases or secrets.

---

## 5. Dialect & Driver Compatibility Verification

The backend abstraction layer in [`db.py`](file:///d:/plant_growth_monitor/db.py) provides automatic compatibility:

1. **URL Scheme Translation:** Supabase URIs starting with `postgres://` or `postgresql://` are normalized via `normalize_database_url()`.
2. **Dialect Transparency:** Dynamic cursor conversion maps SQLite `?` placeholders to PostgreSQL `%s` parameters.
3. **Primary Key Generation:** PostgreSQL inserts utilize `RETURNING id` to capture inserted IDs, matching SQLite's `lastrowid` behavior.
4. **Timezone Handling:** PostgreSQL `TIMESTAMPTZ` values are normalized into standard ISO 8601 strings, ensuring frontend charts and tables render identically regardless of database backend.
