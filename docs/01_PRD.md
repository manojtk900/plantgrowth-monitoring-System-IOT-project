# Product Requirements Document (PRD)

## Project Title
**IoT-Based Plant Growth & Environmental Monitoring System**

**Document Version:** 1.0.0  
**Status:** Approved for Baseline Implementation  
**Target Hardware:** ESP32 DevKit V1 (Device ID: `ESP32_003`)  
**Target Platform:** Flask 3.x, SQLite, Modern Web Dashboard (Vanilla CSS, JavaScript, Chart.js)

---

## 1. Product Vision & Problem Statement

### 1.1 Product Vision
To provide agricultural researchers, greenhouse operators, and indoor horticulturists with a precision, cost-effective, real-time edge monitoring platform that converts raw environmental telemetry into explainable, actionable plant condition metrics without false scientific claims.

### 1.2 Problem Statement
Conventional automated plant care systems either rely on expensive, proprietary industrial sensors or cheap consumer gadgets that output opaque "black-box" health scores or inaccurate volumetric moisture readings. Small-scale greenhouse operators and agricultural students require a transparent system that:
- Captures physical environmental data reliably at the hardware level.
- Computes calibration-adjusted relative soil moisture without overloading low-power microcontrollers.
- Detects composite environmental stress (e.g. high temperature coupled with low moisture accelerating drying risk).
- Provides an intuitive, modern dashboard with animated liquid-fill visualization, historical trend analysis, and physical plant height tracking.

---

## 2. Target Users & User Personas

| User Persona | Role | Key Goals | Pain Points with Existing Systems |
| :--- | :--- | :--- | :--- |
| **Dr. Ananya / Professor** | Academic Evaluator & Agronomy Researcher | Verifiable sensor calibration, explainable condition scoring, raw vs derived data distinction. | Distrusts systems that claim "100% soil moisture saturation" without soil texture context or fake air humidity readings. |
| **Rohan / Student Researcher** | Project Developer & Presenter | High demonstration appeal, modern UI, live hardware status, reliable offline handling during viva. | Clunky dashboards, flickering charts, lack of responsive mobile design, unclear architecture. |
| **Vikram / Urban Farm Operator** | Greenhouse Horticulturist | Early warning of drying risk, irrigation decision support, tracking vertical canopy growth over weeks. | Information overload, lack of cross-variable drying alerts (heat + drought). |

---

## 3. Goals & Non-Goals

### 3.1 Project Goals
- **G-1 (Hardware Integrity):** Preserve stable communication with ESP32 DevKit V1 using GPIO 34 (Soil Moisture), GPIO 4 (DS18B20), GPIO 5/18 (HC-SR04).
- **G-2 (Explainable Calibration):** Backend-side linear mapping of capacitive soil moisture raw ADC (`DRY_RAW = 3326`, `WET_RAW = 1520`) into a 0–100% Relative Soil Moisture Index (RSMI).
- **G-3 (Animated Liquid Fill UI):** Deliver a fluid, animated water-tank visualization representing moisture levels with continuous gentle surface waves and smooth height transitions.
- **G-4 (Rule-Based Environmental Condition Engine):** Cross-correlate soil moisture and DS18B20 temperature to determine drying risk (Low/Moderate/High) and an explainable Plant Condition Score (0–100).
- **G-5 (Physical Growth Tracking):** Calculate true plant height relative to the calibrated 30.0 cm ultrasonic sensor mount height ($H_{plant} = 30.0\text{ cm} - D_{sensor}$).
- **G-6 (Data Integrity & Trend Analytics):** Compute real-time rates of moisture loss and vertical growth trends using actual SQLite historical readings without fabricating data.

### 3.2 Non-Goals
- **NG-1 (Volumetric Water Content):** Will NOT claim laboratory-grade volumetric soil moisture content ($\theta_v, \text{m}^3/\text{m}^3$) or scientific matric potential without soil texture curves.
- **NG-2 (Fake Humidity):** There is currently NO physical air-humidity sensor; the system will NOT display fabricated or simulated humidity values.
- **NG-3 (Black-box AI Health Diagnosis):** Will NOT claim AI diagnosis of plant pathology/disease without multispectral imaging or biological pathology data.
- **NG-4 (ESP32 Firmware Disruption):** Will NOT modify ESP32 pin assignments or alter the `POST /api/sensor-data` payload structure.
- **NG-5 (Premature Cloud Dependency):** Will NOT force cloud hosting dependencies during local laboratory evaluation.

---

## 4. User Stories & Acceptance Criteria

### US-1: Real-Time Liquid Moisture Visualization
- **As a** greenhouse monitor,
- **I want** to see the soil moisture displayed as an animated liquid inside a transparent container,
- **So that** I can intuitively assess root-zone water availability at a glance.
- **Acceptance Criteria:**
  - Water level rises/falls smoothly using CSS transitions (`transform` / `height`).
  - Surface features a continuous moving sinusoidal wave effect.
  - Value updates interpolate smoothly from the previous percentage without dropping to 0%.
  - Displays numerical percentage, raw ADC reading, and relative category (e.g. "Good", "Low").

### US-2: Temperature-Aware Drying Risk
- **As a** grower,
- **I want** the system to alert me when elevated temperatures accelerate soil drying,
- **So that** I can intervene before moisture reaches wilting point.
- **Acceptance Criteria:**
  - Evaluates both moisture percentage and DS18B20 temperature.
  - If moisture is Low ($<35\%$) and temperature is High ($>30^\circ\text{C}$), drying risk is classified as **High**.
  - Decision engine exposes transparent explanation text.

### US-3: Explainable Plant Condition Score
- **As an** evaluator,
- **I want** to inspect why the plant condition score is a specific value (e.g., 78/100),
- **So that** I understand the underlying environmental factors.
- **Acceptance Criteria:**
  - Score is labeled "Plant Condition Score" or "Environmental Plant Health Score".
  - Shows breakdown: Moisture factor, Temperature factor, Trend factor, Sensor health.

### US-4: Device Connection State Verification
- **As an** operator,
- **I want** to know if the ESP32 is genuinely transmitting data,
- **So that** I am not misled by stale sensor values if power is lost.
- **Acceptance Criteria:**
  - Evaluates elapsed time since last received timestamp ($T_{now} - T_{latest}$).
  - $< 30\text{s}$: **ONLINE** (green indicator).
  - $30\text{s} - 90\text{s}$: **RECENT** (amber indicator).
  - $90\text{s} - 5\text{m}$: **STALE** (orange indicator).
  - $> 5\text{m}$: **OFFLINE** (red indicator).

---

## 5. Functional Requirements Overview
- **FR-01:** Backend ingestion of ESP32 JSON payload (`POST /api/sensor-data`).
- **FR-02:** Backend moisture percentage calculation using calibrated constants.
- **FR-03:** Data validation rejecting impossible readings (e.g. raw ADC $> 4095$, temp $=-127^\circ\text{C}$, negative distance).
- **FR-04:** Real-time polling and chart update without canvas destruction flicker.
- **FR-05:** Tabbed/navigable views for Dashboard, Plant Growth, Analytics, Sensor History, Device Status, and Settings.
- **FR-06:** Historical data search, sorting, and pagination.

---

## 6. Non-Functional Requirements
- **NFR-01 (Performance):** Dashboard initial load $< 1.2\text{s}$; polling roundtrip $< 150\text{ms}$.
- **NFR-02 (Compatibility):** Compatible with modern browsers (Chrome, Edge, Firefox, Safari) and responsive from 360px mobile to 4K desktop.
- **NFR-03 (Data Safety):** Database operations wrapped in transactions; automatic table and index initialization.
- **NFR-04 (Maintainability):** Modular architecture with clean separation of routes, calculation models, and static assets.
