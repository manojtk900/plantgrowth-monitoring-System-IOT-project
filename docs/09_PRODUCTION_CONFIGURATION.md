# Production Environment & Configuration Specification

**Project:** IoT-Based Plant Growth & Environmental Monitoring System  
**Framework:** Python Flask (WSGI compliant)  
**Configuration Strategy:** 12-Factor App (Environment Variable Driven)

---

## 1. Architectural Configuration Model

The application follows the Twelve-Factor App methodology by strictly separating configuration from code. All environment-specific behaviors (database engine, port bindings, debug modes, credentials) are injected via system environment variables.

```
                  ┌───────────────────────────────────────┐
                  │          Configuration Source         │
                  │ (.env / Render Environment Variables) │
                  └──────────────────┬────────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
      [Development Environment]               [Production Environment]
      • FLASK_ENV=development                • FLASK_ENV=production
      • FLASK_DEBUG=1                         • FLASK_DEBUG=0
      • Database: SQLite file                 • Database: Render PostgreSQL
      • Server: Flask Werkzeug                • Server: Gunicorn WSGI
      • Transport: HTTP on 0.0.0.0:5000       • Transport: HTTPS on $PORT
      • Telemetry: ESP32 Wi-Fi subnet         • Telemetry: ESP32 TLS Ingress
```

---

## 2. Environment Variables Matrix

| Variable | Type | Default (Dev) | Production Target | Description |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | String | *Unset* (falls back to `database/plant_monitor.db`) | `postgresql://user:pass@host:5432/dbname?sslmode=require` | PostgreSQL or SQLite connection URI. |
| `FLASK_ENV` | String | `development` | `production` | Declares operational execution mode. |
| `FLASK_DEBUG`| Integer / Bool | `1` | `0` | Disables interactive debuggers, stack trace exposure, and pin access. |
| `PORT` | Integer | `5000` | Injected by Render (e.g. `10000`) | Network port for Gunicorn / Flask socket binding. |
| `SECRET_KEY` | Hex String | *In-memory fallback* | Cryptographic 64-character random string | Session signing and cryptographic verification token. |
| `PRIMARY_DEVICE_ID` | String | `ESP32_003` | `ESP32_003` | Identifies primary active edge microcontroller node. |

---

## 3. Web Server Comparison: Flask Development vs. Production Gunicorn

| Characteristic | Local Development (`python app.py`) | Production Cloud (`gunicorn app:app`) |
| :--- | :--- | :--- |
| **WSGI Server** | Werkzeug Development Server | Gunicorn 21+ Pre-fork Worker Model |
| **Worker Threads** | Single process (blocking) | 2 Workers $\times$ 4 Threads per worker (8 concurrent requests) |
| **Process Management** | Manual console termination | Master process auto-restarts failed workers |
| **Timeout Handling** | Indefinite (prone to hanging requests) | 60-second worker timeout |
| **Static File Serving** | Local Flask static route | Gunicorn / WhiteNoise / Reverse Proxy |
| **Security Surface** | Exposes Werkzeug debugger if crashed | Returns sanitized 500 JSON without stack traces |

---

## 4. Production Security Checklist

1. **`debug=False` Enforced:** Never execute `app.run(debug=True)` in cloud hosting.
2. **Secrets Out of Version Control:** `.env` is added to `.gitignore`. `.env.example` contains only placeholder schema.
3. **Database Credentials Encrypted in Transit:** `sslmode=require` appended to PostgreSQL connection URI.
4. **Error Sanitization:** All HTTP $400$ and $500$ responses return clean JSON payloads without internal file system paths or stack frames.
5. **CORS & Ingress Policies:** Direct API ingress restricted to authorized telemetry endpoints.
