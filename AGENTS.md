# IoT Plant Growth Monitor - Project Rules

## Core Principle
Preserve working functionality. Never rewrite the entire project without explicit approval.

## Backend
- Use Flask.
- Keep the existing REST API compatible with the ESP32.
- Use SQLite during local development.
- Do not delete historical database records.
- Validate all incoming sensor data.
- Keep moisture calibration on the backend.

## ESP32
Current device: ESP32_003
Current pins:
- Soil moisture: GPIO 34
- DS18B20: GPIO 4
- HC-SR04 TRIG: GPIO 5
- HC-SR04 ECHO: GPIO 18 (voltage divider)
Do not change these pins unless technically necessary and explicitly documented.
Do not modify ESP32 firmware unnecessarily.

## Moisture Calibration
DRY_RAW = 3326
WET_RAW = 1520
Moisture is a relative soil moisture index. Do not claim laboratory-measured volumetric water content.

## Sensors Available
- Capacitive Soil Moisture Sensor (AOUT -> GPIO 34)
- DS18B20 Waterproof Temperature Sensor (DATA -> GPIO 4)
- HC-SR04 Ultrasonic Sensor (TRIG -> GPIO 5, ECHO -> GPIO 18)
There is currently NO air humidity sensor. Never generate fake humidity readings.

## UI Principles
- Prefer modern, clean, responsive, agriculture/IoT-focused design.
- Explainable visualizations.
- Moisture visualization should use an animated liquid-fill/wave design with smooth transitions without resetting to zero.

## Data Integrity
Never fabricate:
- Sensor readings
- Historical readings
- Humidity
- Growth
- Health measurements
All displayed values should originate from real data or clearly labelled calculated values.

## Testing
After changes:
1. Run backend tests.
2. Test API endpoints.
3. Test database operations.
4. Test browser UI.
5. Verify existing ESP32 data flow.
Never consider a feature complete merely because the code compiles.