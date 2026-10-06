# Academic Project Report Content & Viva Voce Guide

## 1. Project Title & Abstract
**Project Title:** IoT-Based Plant Growth & Environmental Monitoring System Using ESP32 and Calibrated Edge Telemetry

### Abstract
Efficient water utilization and microclimate monitoring are paramount for sustainable agriculture. This project presents an end-to-end edge-to-web telemetry system designed to monitor soil moisture, root-zone temperature, and vertical plant growth. Built around an ESP32 DevKit V1 microcontroller, the edge node samples a capacitive soil moisture sensor (GPIO 34), a DS18B20 digital temperature probe (GPIO 4), and an HC-SR04 ultrasonic distance sensor (GPIO 5/18) mounted at a fixed reference distance of 30.0 cm above the substrate. 

Raw analog capacitive readings are transmitted over local Wi-Fi to a lightweight Python Flask REST API server, where an empirical linear calibration model converts raw values into a Relative Soil Moisture Index (RSMI) bounded between dry (3326) and wet (1520) baselines. The system features a temperature-aware drying risk engine, an explainable Environmental Plant Condition Score, and a modern responsive dashboard featuring an animated liquid moisture gauge, historical trend analysis, and physical canopy height growth curves. The system preserves strict scientific data integrity by disclaiming unmeasured parameters such as air humidity.

---

## 2. Key Viva Voce Q&A Preparation

### Q1: Why did you use a capacitive moisture sensor instead of a resistive moisture sensor?
**Answer:** Resistive soil moisture sensors pass DC current directly through probe tracks exposed to wet soil, causing rapid electrochemical oxidation and galvanic corrosion within days, which distorts readings and contaminates soil with metal ions. Capacitive sensors are physically insulated by solder mask and measure changes in soil dielectric permittivity without electrical conduction, offering long-term stability and corrosion immunity.

### Q2: Why is the moisture percentage calculated on the Flask server instead of inside the ESP32?
**Answer:** Edge microcontrollers should focus on deterministic signal acquisition and minimal power consumption. By keeping calibration constants (`DRY_RAW = 3326`, `WET_RAW = 1520`) on the server:
1. Recalibration for different soil types (e.g. sandy loam vs cocopeat) requires zero microcontroller flashing.
2. Raw ADC values are preserved in the database for retrospective recalibration and historical data integrity.
3. Complex floating-point calculations and multi-factor decision engines do not strain microcontroller memory.

### Q3: Why do higher ADC values correspond to drier soil in your sensor?
**Answer:** The capacitive probe contains a 555-timer oscillator circuit. When soil is dry, the dielectric constant is low (~3), resulting in low capacitance. Lower capacitance produces higher filtered output voltage. The ESP32's 12-bit ADC converts this higher voltage into a larger digital integer (~3326). When soil is saturated, water's high dielectric constant (~80) increases capacitance, lowering output voltage and producing a lower ADC value (~1520).

### Q4: Why is there a voltage divider on the HC-SR04 ECHO pin?
**Answer:** The HC-SR04 operates at 5V VCC to drive its ultrasonic transducers and outputs a 5V TTL pulse on the ECHO pin. The ESP32 GPIO inputs have a maximum absolute voltage rating of 3.6V. Exposing GPIO 18 directly to 5V will permanently damage the microcontroller. A $1\text{ k}\Omega + 1\text{ k}\Omega$ voltage divider steps the 5V pulse down to $2.5\text{ V}$, which safely satisfies the ESP32's minimum logic HIGH threshold ($V_{IH} \approx 2.475\text{ V}$).

### Q5: How do you measure plant height using an ultrasonic sensor?
**Answer:** The HC-SR04 is mounted at a fixed overhead reference height of $H_{ref} = 30.0\text{ cm}$ pointing downward toward the soil bed. The sensor measures distance to the highest point of the plant canopy ($D_{sensor}$). Plant height is calculated as $H_{plant} = H_{ref} - D_{sensor} = 30.0\text{ cm} - D_{sensor}$. As the plant grows upward, $D_{sensor}$ decreases and calculated height increases.

### Q6: Why does your dashboard not show air humidity?
**Answer:** Engineering integrity requires that we only display data originating from physical sensors. The current hardware build includes capacitive soil moisture, temperature, and ultrasonic distance. There is no physical air humidity sensor (e.g. SHT31 or DHT22) attached. Generating fake humidity or guessing it from soil moisture would violate scientific data integrity.
