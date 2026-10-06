# IoT Hardware & Circuit Interfacing Specification

## 1. Microcontroller: ESP32 DevKit V1
The system employs the Espressif ESP32 DevKit V1 (30-pin dual-core Xtensa 32-bit LX6, 240 MHz, 520 KB SRAM, integrated 2.4 GHz 802.11 b/g/n Wi-Fi and Bluetooth).

- **Current Device ID:** `ESP32_003`
- **Operating Voltage:** 3.3V logic level (maximum pin tolerance is 3.3V; 5V signals require voltage division).
- **Current Firmware Posting Interval:** ~10 seconds.

---

## 2. Sensor Interfacing & Electrical Pinout

### 2.1 Complete Pinout Mapping
| Sensor Component | Sensor Pin | ESP32 Pin | Logic Level | Electrical Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Capacitive Moisture Sensor v1.2** | VCC | 3.3V | 3.3V | Powered from regulated 3.3V rail. |
| | GND | GND | 0V | Common ground. |
| | AOUT | GPIO 34 | Analog (0–3.3V) | ADC1 Channel 6 (input-only pin; immune to Wi-Fi ADC2 conflicts). |
| **DS18B20 Digital Temp Sensor** | VCC | 3.3V | 3.3V | Waterproof stainless steel probe packaging. |
| | GND | GND | 0V | Common ground. |
| | DATA | GPIO 4 | 3.3V 1-Wire | Requires $4.7\text{ k}\Omega$ pull-up resistor between DATA and 3.3V. |
| **HC-SR04 Ultrasonic Ranging** | VCC | VIN (5V) | 5V | Transducers require 5.0V excitation for reliable 40 kHz pulses. |
| | GND | GND | 0V | Common ground. |
| | TRIG | GPIO 5 | 3.3V | Digital output trigger pulse (10 µs active high). |
| | ECHO | GPIO 18 | 2.5V (Divided) | **Voltage divider required:** $1\text{ k}\Omega + 1\text{ k}\Omega$ divider from 5V echo pulse. |

---

## 3. Circuit Schematics & Signal Integrity Details

### 3.1 HC-SR04 Echo Voltage Divider Circuit
The HC-SR04 module outputs a 5V TTL pulse on its ECHO line. Exposing ESP32 GPIO directly to 5V will permanently degrade the silicon ESD diodes.
```
HC-SR04 ECHO (5V) ──────[ 1 kΩ Resistor ]──────┬──────> ESP32 GPIO 18 (Input)
                                               │
                                       [ 1 kΩ Resistor ]
                                               │
                                              GND
```
- **Output Voltage at Node:** $V_{in} \times \frac{R_2}{R_1 + R_2} = 5.0\text{V} \times \frac{1000}{1000 + 1000} = 2.50\text{ V}$.
- **ESP32 High-Level Logic Threshold ($V_{IH}$):** Minimum $0.75 \times V_{DD} = 0.75 \times 3.3\text{V} = 2.475\text{ V}$.
- **Result:** $2.50\text{ V} \ge 2.475\text{ V}$, providing a clean logic HIGH without overvoltage.

### 3.2 Capacitive Soil Moisture Sensor (ADC1_CH6)
- **Principle:** Measures dielectric permittivity of soil using high-frequency oscillator. Capacitance increases with soil moisture, lowering output DC voltage.
- **Why GPIO 34?** GPIO 34 is part of ADC1. In the ESP32, ADC2 channels cannot be used concurrently with the Wi-Fi stack. ADC1 channels are unaffected by Wi-Fi transmissions, guaranteeing continuous analog conversions.

### 3.3 Mechanical Mounting Geometry for Growth Measurement
- The ultrasonic sensor is mounted on a fixed overhead gantry positioned at a calibrated distance of **$30.0\text{ cm}$** above the baseline soil surface.
- As the plant canopy grows upward toward the sensor, the measured sonic distance $D_{sensor}$ decreases.
- Plant height is computed deterministically as:
  $$H_{plant} = 30.0\text{ cm} - D_{sensor}$$
- Validation:
  - If $D_{sensor} = 12.88\text{ cm} \implies H_{plant} = 17.12\text{ cm}$.
  - If $D_{sensor} = 7.80\text{ cm} \implies H_{plant} = 22.20\text{ cm}$.
  - Physical boundary: $H_{plant} \ge 0.0\text{ cm}$ and $D_{sensor} \le 30.0\text{ cm}$.
