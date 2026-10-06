# Business Requirements Document (BRD)

## Project Title
**IoT-Based Plant Growth & Environmental Monitoring System**

**Document Version:** 1.0.0  
**Scope:** Academic Engineering Capstone / Precision Agriculture IoT Pilot

---

## 1. Executive Summary & Business Problem
Agriculture accounts for approximately 70% of global freshwater withdrawals. Unscientific, timer-based or ad-hoc manual irrigation results in chronic over-watering, root hypoxia, fungal disease proliferation, and nutrient leaching. Conversely, delayed irrigation under high daytime temperatures causes rapid wilting and irreversible biomass stunting.

Existing industrial smart-agriculture supervisory control systems (SCADA) cost thousands of dollars, making them inaccessible for small-scale nurseries, educational greenhouses, and urban farmers. Low-cost alternatives often suffer from inaccurate capacitive sensor calibration, lack of temperature cross-correlation, and unreliable web user interfaces.

This project delivers a **cost-effective (<$30 hardware footprint), transparent, edge-to-dashboard monitoring platform** that combines:
1. Microcontroller-level telemetry via ESP32 DevKit V1.
2. Calibrated Relative Soil Moisture Indexing (RSMI).
3. Contactless canopy height growth tracking via ultrasonic echo measurement.
4. Explainable rule-based environmental decision support.

---

## 2. Stakeholders & Roles

| Stakeholder Group | Representation | Expectations |
| :--- | :--- | :--- |
| **Academic Evaluators** | University Project Viva Board | Rigorous engineering methodology, circuit integrity, transparent calibration calculations, explainable condition scoring, comprehensive IEEE documentation. |
| **Agricultural Operators** | Greenhouse & Nursery Managers | Intuitive, low-latency visual status, early drying alerts, zero false alarms, durable operation. |
| **System Developers / QA** | Full-Stack & IoT Engineers | Modular Python Flask codebase, zero regression of working hardware flow, documented REST APIs, automated test coverage. |

---

## 3. Business Value Proposition
- **Water Conservation:** Enables precision irrigation timing by identifying optimal moisture thresholds and high evaporative drying risk.
- **Biomass Optimization:** Tracks vertical growth rate (cm/day) continuously without disturbing plant foliage.
- **Cost Reduction:** Utilizes commercially standard off-the-shelf components (ESP32, Capacitive v1.2, DS18B20, HC-SR04) with open-source software (Flask, SQLite, Chart.js).
- **Educational & Demonstration Excellence:** Modern, animated dashboard built to high visual standards suitable for technical presentations and research publications.

---

## 4. Scope & Constraints
- **Hardware Boundary:** Fixed to ESP32 DevKit V1 with designated GPIO assignments (GPIO 34, GPIO 4, GPIO 5, GPIO 18).
- **Atmospheric Sensor Scope:** Strictly limited to current physical sensors. No fake air humidity readings.
- **Budgetary Ceiling:** Hardware component cost $\le \$35$ USD; zero software licensing costs.
- **Operational Environment:** Local LAN deployment with static/DHCP IP binding for edge device to Flask server.

---

## 5. Success Criteria & KPIs

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| **Telemetry Ingestion Reliability** | $> 99.5\%$ packet success | Ratio of successful HTTP 201 responses to ESP32 transmission attempts over 24 hours. |
| **Dashboard Latency** | $< 200\text{ms}$ refresh response | Network tab evaluation of `/api/latest` payload fetch. |
| **Calibration Accuracy** | Clamped $[0, 100]\%$ linear mapping | Unit test verification against physical bounds (`DRY_RAW = 3326`, `WET_RAW = 1520`). |
| **Device Disconnect Detection** | Transition to OFFLINE within 5 minutes | Simulated power-cut test and timestamp difference validation. |
| **Academic Rigor** | 100% explainable metrics | Viva review demonstrating formula transparency for every score. |
