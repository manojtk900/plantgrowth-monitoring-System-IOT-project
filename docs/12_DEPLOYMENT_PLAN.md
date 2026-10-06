# Deployment & Operations Plan

## 1. Local Edge Deployment (Current Stage)

### 1.1 Local Host Requirements
- **OS:** Windows 10/11, Ubuntu 22.04 LTS, or Raspberry Pi OS (64-bit).
- **Python Version:** 3.10 or higher.
- **Port:** 5000 TCP open on local firewall for Wi-Fi subnet traffic.

### 1.2 Running the Application
```powershell
# 1. Activate Virtual Environment
.\.venv\Scripts\Activate.ps1

# 2. Run Application Gateway
python app.py
```
- Ingress Address for ESP32: `http://<HOST_LOCAL_IP>:5000/api/sensor-data`
- Web Dashboard Access: `http://localhost:5000` or `http://<HOST_LOCAL_IP>:5000`

### 1.3 Windows Firewall Configuration
To allow the ESP32 to send HTTP POST requests to port 5000 across the local Wi-Fi:
```powershell
New-NetFirewallRule -DisplayName "Flask Plant Monitor 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

---

## 2. Production Edge Service (Waitress / Systemd)
For 24/7 continuous monitoring without debug server overhead:
- On Windows: Use `waitress-serve --host=0.0.0.0 --port=5000 app:app`.
- On Linux / Raspberry Pi: Deploy as a `systemd` daemon with automatic restart on reboot.

---

## 3. Future Cloud Migration Roadmap (Phase 13)
When migrating from local edge to public cloud hosting (e.g., Render, Railway, AWS EC2):
1. **Database Decoupling:** Migrate from embedded SQLite to managed PostgreSQL / Supabase.
2. **Device Authentication:** Implement pre-shared API keys (`X-Device-Token`) in HTTP headers.
3. **Domain & HTTPS:** Deploy behind Cloudflare with TLS encryption.
4. **Environment Configuration:** Store all database URIs and secrets in `.env` or cloud secret managers.
