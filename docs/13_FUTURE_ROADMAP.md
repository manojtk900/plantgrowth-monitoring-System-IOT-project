# Future Roadmap & Evolution Strategy

## 1. Architectural Horizon

```
Phase 0-11 (Current Local Edge) ──> Phase 12-13 (Production & Cloud) ──> Long-Term (Automated Agritech)
• Calibrated RSMI               • Waitress / Gunicorn Service       • Peristaltic Closed-Loop Pump
• Liquid Tank Visualization     • PostgreSQL Migration              • Physical SHT31 Air Humidity
• Multi-View Dashboard          • Multi-Node Edge Support           • Solar Harvesting + Deep Sleep
• Explainable Condition Score   • Device Auth & HTTPS               • LoRa / ESP-NOW Mesh
```

---

## 2. Planned Sensor Enhancements

### 2.1 Physical Air Humidity Sensor (SHT31 / DHT22)
- **Constraint Reminder:** Currently, no physical air humidity sensor is attached.
- **Future Integration:** SHT31-D via I2C (GPIO 21 SDA, GPIO 22 SCL) offering $\pm 2\%$ RH accuracy.
- **External Weather API Disambiguation:** If an external weather API (e.g. Open-Meteo) is added, the UI must explicitly distinguish:
  - `"External Weather Humidity (City Grid)"` vs.
  - `"Measured Microclimate Canopy Humidity"`.

### 2.2 Closed-Loop Automated Irrigation Actuation
- 5V optically isolated single-channel relay connected to ESP32 GPIO 23.
- Controls a 12V 100 mL/min peristaltic dosing pump.
- Firmware safety cutoffs: Max watering burst 15 seconds; minimum interval 1 hour to prevent flooding from sensor dislodgement.

---

## 3. Communication & Scalability Enhancements
- **MQTT Protocol Transition:** Transition telemetry from HTTP POST to MQTT broker (Mosquitto / HiveMQ) for lower overhead and bidirectional pump actuation.
- **Multi-Zone Support:** Partition database and dashboard to view multiple beds (`Bed A`, `Bed B`, `Greenhouse 1`).
- **Telemetry Export:** CSV and Excel export utilities on the Sensor History view.
