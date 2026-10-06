# Software Requirements Specification (SRS)
## Based on IEEE Std 830-1998

**Project Title:** IoT-Based Plant Growth & Environmental Monitoring System  
**Document Identifier:** SRS-PGMS-2026-V1  
**Date:** October 2026

---

## 1. Introduction
### 1.1 Purpose
This document specifies the software requirements for the IoT-Based Plant Growth & Environmental Monitoring System, comprising a Python Flask backend, SQLite persistence store, RESTful API layer, and an interactive browser-based dashboard.

### 1.2 Scope
The system acquires sensor data from an ESP32 microcontroller, calculates relative soil moisture and plant height, assesses temperature-dependent soil drying risk, tracks growth over time, and presents visual diagnostics (including an animated liquid moisture gauge) on a responsive dashboard.

### 1.3 Definitions, Acronyms, and Abbreviations
- **ADC:** Analog-to-Digital Converter (12-bit on ESP32, range 0–4095).
- **RSMI:** Relative Soil Moisture Index (0–100% relative scale).
- **DS18B20:** Maxim Integrated 1-Wire Digital Thermometer.
- **HC-SR04:** Ultrasonic Ranging Module (40 kHz sonic transducer).
- **REST:** Representational State Transfer.
- **UI/UX:** User Interface / User Experience.

---

## 2. Overall Description
### 2.1 Product Perspective
The system functions as an IoT edge-to-server monitoring pipeline:
```
[Sensors] ──GPIO──> [ESP32 DevKit V1] ──HTTP POST/WiFi──> [Flask REST API] ──SQL──> [SQLite DB]
                                                                  │
                                                          [HTTP GET JSON]
                                                                  ↓
                                                      [Web Dashboard (HTML5/CSS3/JS)]
```

### 2.2 User Characteristics
Users include agricultural operators, researchers, and project evaluators possessing basic computer literacy and familiar with environmental metrics (°C, %, cm).

### 2.3 Operating Environment
- **Server:** Python 3.10+ on Windows / Linux / macOS.
- **Client:** Modern standards-compliant web browser (Google Chrome 110+, Mozilla Firefox 110+, Apple Safari 16+, Microsoft Edge 110+).
- **Microcontroller:** ESP32 DevKit V1 with 2.4 GHz 802.11 b/g/n Wi-Fi.

---

## 3. Specific Requirements

### 3.1 External Interface Requirements
#### 3.1.1 Hardware Interfaces
- Capacitive Soil Moisture Sensor connected to ADC1 Channel 6 (GPIO 34).
- DS18B20 Data Line connected to GPIO 4 with a $4.7\text{ k}\Omega$ pull-up resistor.
- HC-SR04 Trigger connected to GPIO 5; Echo connected to GPIO 18 through a $1\text{ k}\Omega + 1\text{ k}\Omega$ resistive voltage divider (5V $\rightarrow$ 2.5V safe logic).

#### 3.1.2 Software Interfaces
- SQLite 3.x embedded database driver.
- Chart.js 4.x via CDN for real-time canvas rendering.

---

### 3.2 Functional Requirements

| Req ID | Title | Description | Priority |
| :--- | :--- | :--- | :--- |
| **FR-001** | Telemetry Ingestion | Server shall expose `POST /api/sensor-data` accepting JSON payload: `device_id`, `moisture_raw`, `moisture_percent`, `temperature_c`, `distance_cm`, `plant_height_cm`, `status`. Return HTTP 201 on success. | High |
| **FR-002** | Payload Validation | Server shall validate that numeric fields adhere to physical limits ($0 \le \text{moisture\_raw} \le 4095$, $-20 \le \text{temperature} \le 80$, $\text{distance} \ge 0$). Discard or flag invalid frames without crashing. | High |
| **FR-003** | RSMI Calculation | Server shall calculate relative moisture index using $RSMI = \max\left(0, \min\left(100, \frac{3326 - \text{raw}}{3326 - 1520} \times 100\right)\right)$ when `moisture_raw` is present. | High |
| **FR-004** | Latest State Query | Server shall expose `GET /api/latest` returning the most recently recorded reading as JSON. | High |
| **FR-005** | History Query | Server shall expose `GET /api/history?limit=N` returning historical readings in reverse chronological order. | High |
| **FR-006** | Real-Time Telemetry Polling | Dashboard shall poll `/api/latest` every 5 seconds to update gauges and cards without page reloads. | High |
| **FR-007** | Animated Liquid Moisture Fill | Dashboard shall render an animated liquid tank showing water level matching RSMI, with continuous surface wave motion and smooth height transitions. | High |
| **FR-008** | Temperature-Aware Drying Risk | Decision engine shall evaluate soil moisture and temperature to classify drying risk (Low, Moderate, High) with contextual recommendations. | High |
| **FR-009** | Explainable Condition Score | System shall calculate an explainable Environmental Plant Health Score (0–100) detailing contributing deductions. | Medium |
| **FR-010** | Device Liveness Evaluation | System shall determine hardware liveness based on the elapsed duration since the latest reading: ONLINE ($<30\text{s}$), RECENT ($<90\text{s}$), STALE ($<5\text{m}$), OFFLINE ($>5\text{m}$). | High |
| **FR-011** | Plant Growth Analytics | System shall track height change between readings ($\Delta H$) and aggregate total growth since observation commencement. | Medium |
| **FR-012** | Dedicated Tab Navigation | Dashboard navigation shall allow seamless switching between Dashboard, Plant Growth, Analytics, Sensor History, Device Status, and Settings. | Medium |

---

### 3.3 Non-Functional Requirements

| Req ID | Metric | Specification |
| :--- | :--- | :--- |
| **NFR-001** | Ingestion Latency | $POST$ request processing and database commit time $\le 50\text{ ms}$. |
| **NFR-002** | UI Smoothness | CSS liquid wave animation shall run at a minimum of 50 FPS on modern mobile/desktop GPUs. |
| **NFR-003** | Data Retention | SQLite database shall retain historical records without arbitrary truncation. |
| **NFR-004** | Fault Tolerance | If a sensor drops off or returns NULL, system displays `--` and status flag without UI breakdown. |
| **NFR-005** | Zero Mock Humidity | Dashboard shall not display or simulate relative air humidity without physical sensor hardware. |
