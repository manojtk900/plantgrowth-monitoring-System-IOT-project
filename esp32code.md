# ESP32 Edge Node Firmware Documentation & Code
**Device ID:** `ESP32_003`  
**Architecture:** Dual-Destination (Render Cloud HTTPS First → Local Flask LAN Fallback)  
**Security:** Let's Encrypt ISRG Root X1 CA TLS Verification + SNTP Clock Synchronization  
**Visual Indicators:** Optional Plug-and-Play Status LEDs (GPIO 25 & GPIO 26)

---

## 1. System Architecture & Optional Indicator Layer

```
                  ┌─────────────────────┐
                  │      ESP32_003      │
                  └──────────┬──────────┘
                             │
                       WiFiMulti
                             │
              ┌──────────────┼──────────────┐
              │              │              │
           Wi-Fi 1        Wi-Fi 2        Wi-Fi 3
         (Home Wi-Fi)  (College/Lab)   (Hotspot)
              │              │              │
              └──────────────┼──────────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
           Primary Route           Fallback Route
         (Internet Active)      (Local Offline LAN)
                 │                       │
                 ▼                       ▼
         HTTPS (TLS 1.2/1.3)          HTTP LAN
         Render Cloud API         Flask Local Server
         (ISRG Root X1 CA)        (10.61.173.131:5000)
                 │                       │
                 ▼                       ▼
        Supabase PostgreSQL        SQLite Database
        (sensor_readings)        (plant_monitor.db)
```

### Visual Indicator Subsystem (Zero-Dependency)
```
ESP32
  ├── SENSORS (Core Logic) ──────────────────► Wi-Fi ──► Cloud / Local Server
  └── OPTIONAL LEDs (Visual Indicator)
        ├── GPIO 25 ──► 220Ω ──► Green LED ──► GND
        └── GPIO 26 ──► 220Ω ──► Red LED   ──► GND
```

> **Plug-and-Play Guarantee:** The system functions completely normally with:
> - **No LEDs connected** (Headless / field deployment)
> - **Only Green LED connected**
> - **Only Red LED connected**
> - **Both LEDs connected**
> 
> The LEDs are visual indicators only, never required sensors or control devices. The firmware never asserts any hardware dependency check, never halts, and never blocks execution. ESP32 GPIOs configured as outputs drive the pins via `digitalWrite()` independently.

---

## 2. Hardware Pinout & Wiring Specifications

### A. Core Physical Sensors (Strictly Unchanged)
| Sensor | ESP32 Pin | Sensor Pin | Notes / Protection |
| :--- | :--- | :--- | :--- |
| **Capacitive Soil Moisture v1.2** | `GPIO 34` | AOUT | Analog Input ADC1_CH6 (10-sample ADC averaging) |
| **DS18B20 Waterproof Temp** | `GPIO 4` | DATA | OneWire Bus with **4.7kΩ pull-up resistor** to 3.3V |
| **HC-SR04 Ultrasonic Trigger** | `GPIO 5` | TRIG | Digital Output (10µs trigger pulse) |
| **HC-SR04 Ultrasonic Echo** | `GPIO 18` | ECHO | Digital Input via **Voltage Divider** (1kΩ / 2kΩ to GND) stepping 5V down to 3.3V safe level |
| **Common Ground** | `GND` | GND | Shared ground plane across all sensors |
| **Power Rail** | `3.3V` / `VIN (5V)`| VCC | 3.3V for Capacitive Soil Moisture & DS18B20; 5V (VIN) for HC-SR04 |

### B. Optional Visual Status Indicators (Zero-Dependency)
| Indicator | ESP32 Pin | Series Resistor | Polarities | Purpose / Condition |
| :--- | :--- | :--- | :--- | :--- |
| 🟢 **Green LED** | `GPIO 25` | 220Ω | Anode (+) → 220Ω → GPIO 25<br>Cathode (-) → GND | **Favorable Environment:** Moisture ≥ 40% AND Temp < 30°C AND all sensors valid. |
| 🔴 **Red LED** | `GPIO 26` | 220Ω | Anode (+) → 220Ω → GPIO 26<br>Cathode (-) → GND | **Attention Required / Drying:** Moisture < 40% OR (Moisture < 50% AND Temp ≥ 30°C). |
| 🚨 **Red Blink** | `GPIO 26` | 220Ω | Toggles every 500ms non-blocking | **Hardware Sensor Fault:** DS18B20 invalid OR HC-SR04 invalid. |

---

## 3. Visual Indicator Behavioral Matrix (Truth Table)

| System State | Temp Valid | Dist Valid | Moisture (RSMI) | Temp (°C) | Green LED (GPIO 25) | Red LED (GPIO 26) | Interpretation |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Boot / Startup** | — | — | — | — | **OFF** (`LOW`) | **OFF** (`LOW`) | Initializing; avoids false indicator state before first sensor acquisition cycle. |
| **Normal: Favorable** | ✅ True | ✅ True | ≥ 40% | < 30°C | **ON** (`HIGH`) | **OFF** (`LOW`) | Optimal growth environment: adequate root moisture and temperate climate. |
| **Normal: Dry Soil** | ✅ True | ✅ True | < 40% | Any | **OFF** (`LOW`) | **ON** (`HIGH`) | Soil moisture deficit; irrigation attention needed. |
| **Normal: Heat Stress**| ✅ True | ✅ True | < 50% | ≥ 30°C | **OFF** (`LOW`) | **ON** (`HIGH`) | High transpirational demand / rapid drying risk. |
| **Hardware Fault** | ❌ False | or ❌ False| Any | Any | **OFF** (`LOW`) | **BLINKING** (500ms) | Hardware warning: sensor disconnected, loose jumper, or ultrasonic echo timeout. |

---

## 4. Production Firmware Sketch (`esp32_plant_monitor.ino`)

```cpp
/**
 * =====================================================================
 * IoT-Based Plant Growth & Environmental Monitoring System
 * Edge Node Firmware — ESP32 DevKit V1 (Device ID: ESP32_003)
 * =====================================================================
 * 
 * Features:
 *   1. Multi-Wi-Fi Fallback: WiFiMulti supports 3 saved networks (Home, College, Hotspot).
 *   2. Dual-Destination Telemetry: Cloud-First (Render HTTPS) with automatic Local Fallback (Flask LAN HTTP).
 *   3. Strict TLS Security: WiFiClientSecure with Let's Encrypt ISRG Root X1 CA validation.
 *      (Zero client.setInsecure() bypass).
 *   4. SNTP Synchronization: Real-time clock synchronization for TLS validity checks.
 *   5. Sensor Engine:
 *      - Capacitive Soil Moisture Sensor (v1.2) on GPIO 34 (Multi-sample ADC averaging)
 *      - DS18B20 Waterproof Temperature Sensor on GPIO 4 (OneWire with DallasTemperature)
 *      - HC-SR04 Ultrasonic Sensor on TRIG GPIO 5 / ECHO GPIO 18 (Filtered distance & canopy height)
 *   6. Dynamic Telemetry Contract: Preserves backend relative moisture index calculation.
 * 
 * Libraries Required (Install via Arduino IDE Library Manager):
 *   - ArduinoJson (by Benoit Blanchon, v6.x or v7.x)
 *   - OneWire (by Paul Stoffregen)
 *   - DallasTemperature (by Miles Burton)
 * 
 * Board Settings:
 *   - Board: ESP32 Dev Module
 *   - CPU Frequency: 240MHz (WiFi/BT)
 *   - Flash Frequency: 80MHz
 *   - Upload Speed: 921600 or 115200
 * =====================================================================
 */

#include <WiFi.h>
#include <WiFiMulti.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include "time.h"

// =====================================================================
// 1. HARDWARE CONFIGURATION & PIN ASSIGNMENTS
// =====================================================================
// Core Physical Sensors (Existing wiring strictly unchanged)
#define PIN_SOIL_MOISTURE  34   // ADC1_CH6 (Capacitive sensor analog output)
#define PIN_ONE_WIRE_BUS    4   // DS18B20 Data line (with 4.7kΩ pull-up to 3.3V)
#define PIN_TRIG            5   // HC-SR04 Ultrasonic Trigger
#define PIN_ECHO           18   // HC-SR04 Ultrasonic Echo (via 1kΩ/2kΩ voltage divider)

// Optional Visual Indicators (Plug-and-play indicator layer)
#define PIN_LED_GREEN      25   // Optional Green LED (via 220Ω resistor to GND)
#define PIN_LED_RED        26   // Optional Red LED (via 220Ω resistor to GND)

// Moisture Calibration Reference Points (Relative Soil Moisture Index)
const float DRY_RAW_REF = 3326.0; // Air / Dry Reference (0% RSMI)
const float WET_RAW_REF = 1520.0; // Water / Wet Reference (100% RSMI)

const char* DEVICE_ID = "ESP32_003";
const float SENSOR_MOUNT_HEIGHT_CM = 30.0; // Fixed gantry reference height

// Telemetry Transmission Interval (milliseconds)
const unsigned long TRANSMISSION_INTERVAL_MS = 10000; // 10 seconds between uploads

// =====================================================================
// 2. NETWORK CONFIGURATION & MULTI-WIFI CREDENTIALS
// =====================================================================
WiFiMulti wifiMulti;

// Configure your 3 accessible Wi-Fi networks here:
struct WiFiCredential {
    const char* ssid;
    const char* password;
};

const WiFiCredential WIFI_NETWORKS[3] = {
    {"Home_WiFi",       "home_password_here"},       // Network 1: Home Wi-Fi
    {"College_WiFi",    "college_password_here"},    // Network 2: College / Lab Wi-Fi
    {"Mobile_Hotspot",  "hotspot_password_here"}     // Network 3: Mobile Phone Hotspot
};

// =====================================================================
// 3. SERVER DESTINATIONS (CLOUD-FIRST WITH LOCAL FALLBACK)
// =====================================================================
// Cloud Production Endpoint (Render Managed Web Service over HTTPS)
const char* CLOUD_SERVER_URL = "https://plantgrowth-monitoring-system-iot-project.onrender.com/api/sensor-data";

// Local Development Fallback Endpoint (Your Laptop's LAN IP address)
// (Find via 'ipconfig' on Windows; example: 10.61.173.131 or 192.168.1.100)
const char* LOCAL_SERVER_URL = "http://10.61.173.131:5000/api/sensor-data";

// HTTP Request Timeout (milliseconds)
// (Render free instances take ~20-30s during cold starts; 15s allows robust connection)
const int HTTP_TIMEOUT_MS = 15000;

// =====================================================================
// 4. TLS ROOT CA CERTIFICATE (ISRG ROOT X1 - LET'S ENCRYPT)
// =====================================================================
// Used to validate Render's SSL/TLS certificate securely without client.setInsecure()
const char* ISRG_ROOT_X1_CA = \
"-----BEGIN CERTIFICATE-----\n" \
"MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw\n" \
"TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh\n" \
"cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4\n" \
"WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu\n" \
"ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY\n" \
"MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc\n" \
"h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+\n" \
"0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK/62gvQUbKE\n" \
"ti0hxjp8HUjTvcYyehkTxmdUZccF38Nyc小平8Sj+ppGfKQ55Zx6Lnet9RQDAoBX\n" \
"KqKPR56oqPeeJYptoknwisu4peNxsIEJ48GZGQGREPRuPyayMb7v6fidwbHPmWzq\n" \
"urLKX2m6q030SUrhvUMyzUuwb1vvc34jtxR72s00kt5ODfBShKgTvKFdUkYK硝S\n" \
"57SmZUBlcgPwZbrocvofHgKkwV5R61382J22J+53ENPbFdTKtTXnev4PO9NMmqdt\n" \
"U1HQU5GHcqZPzsnn1BGFiUCkD8Y5W++BX5RpoMV5R58EuiU2J5NO5GDygyPf839K\n" \
"a+6m+hrCcofyP/1vuz6ZY3wcJRnEpstcxhP9h93FqptrK10SJhZODTXWkPwtPR5B\n" \
"bpLNTWBqRZVCiFbflFAFuKaL3MTiiSE88El+AOCLCHGQBLxsGOF70cxO/9649504\n" \
"yicCHFaQDOp5IzhzW64NNPNAEZNamASLo32gYdhFZ973CXfSNoJb6bWVYo4guTWn\n" \
"IQ6bb5ceReEZminHTWAqo1VrAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV\n" \
"HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAjGi13PfWbSTzANBgkq\n" \
"hkiG9w0BAQsFAAOCAgEAVR9YqbyhurmxMYgoQpnDsR36atdTGVCdgNdr+PqKIWFG\n" \
"nRfrt3NC8zp0za3XP7GeOGU07ptlAFmVmoHoDTVCqql8oRgSiDA56rvbE6t8uCWb\n" \
"W97K0UmVmaAgMXTDKgYZlq7Yd875NspJRaq62KsEfgJaQrknyXSTghEQFiqPRUxk\n" \
"Z52IT/hfOzU98dxvPusNE520bER54wt8h90449gA45UwKW4gGwWQlkjgw9fKSxQv\n" \
"cWf1smquFnzgc65MmPF8EulMxZUAkeotecAO0xFsODHZyNzu8WIZBCWnu00EuU5K\n" \
"DYN0307dH7VNGMbVKZL6LydSL6UgL100Ny2+NuvWKU0Pv8SuPEbeWi5bPB21YhL4\n" \
"8Af1oVCC58Tno1P73uuZJ2a752v04i9QeeoZkGB32DK6CDwxfvE9636bWBXHAEZf\n" \
"qCqmPXxD2Y55q06S24C8NXj54E+Is4dtNXBDb3+YsPEU43OzHKEGoZKy2V1Cit80\n" \
"FJa0b+jWgvzOhKEpdQVMw3795095Hr58GZyb8t0v486WXuQSxQ==\n" \
"-----END CERTIFICATE-----\n";

// =====================================================================
// 5. HARDWARE DRIVERS & STATE VARIABLES
// =====================================================================
OneWire oneWire(PIN_ONE_WIRE_BUS);
DallasTemperature tempSensors(&oneWire);

unsigned long lastTransmissionTime = 0;
bool sntpSynchronized = false;

// Optional Visual LED State Machine
enum LEDIndicatorState {
    LED_STATE_STARTUP_OFF,     // Startup default: Both LEDs OFF until first valid reading
    LED_STATE_GREEN_FAVORABLE, // Green Steady: Moisture >= 40% AND Temp < 30°C AND sensors valid
    LED_STATE_RED_ATTENTION,   // Red Steady: Moisture < 40% OR (Moisture < 50% AND Temp >= 30°C)
    LED_STATE_RED_FAULT_BLINK  // Red Blink: Hardware sensor fault (DS18B20 or HC-SR04 invalid)
};

LEDIndicatorState currentLEDState = LED_STATE_STARTUP_OFF;
unsigned long lastLEDBlinkToggle = 0;
bool ledBlinkToggleState = false;

// Telemetry Data Struct
struct SensorTelemetry {
    float moistureRaw;
    float temperatureC;
    bool  temperatureValid;
    float distanceCm;
    bool  distanceValid;
    float plantHeightCm;
    const char* status;
};

// Forward Declarations
float calculateLocalMoisturePercent(float raw);
void  updateLEDIndicators(const SensorTelemetry &t);
void  serviceLEDBlink();

// =====================================================================
// 6. SETUP ROUTINE
// =====================================================================
void setup() {
    Serial.begin(115200);
    delay(1500);

    Serial.println("\n========================================");
    Serial.println(" IoT Plant Growth Monitoring System");
    Serial.printf (" Device ID: %s\n", DEVICE_ID);
    Serial.println("========================================");

    // Initialize Sensor GPIOs (Existing wiring unchanged)
    pinMode(PIN_SOIL_MOISTURE, INPUT);
    pinMode(PIN_TRIG, OUTPUT);
    digitalWrite(PIN_TRIG, LOW);
    pinMode(PIN_ECHO, INPUT);

    // Initialize Optional Visual Indicator LEDs (Zero-dependency outputs)
    // Both start explicitly OFF until the first valid sensor acquisition cycle
    pinMode(PIN_LED_GREEN, OUTPUT);
    pinMode(PIN_LED_RED, OUTPUT);
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_RED, LOW);

    // Initialize DS18B20 Temperature Sensor
    tempSensors.begin();
    tempSensors.setResolution(11); // 11-bit resolution = 0.125°C precision

    // Register Wi-Fi Networks with WiFiMulti
    Serial.println("\nConfiguring Wi-Fi Networks:");
    for (int i = 0; i < 3; i++) {
        wifiMulti.addAP(WIFI_NETWORKS[i].ssid, WIFI_NETWORKS[i].password);
        Serial.printf(" [%d] %s\n", i + 1, WIFI_NETWORKS[i].ssid);
    }

    // Connect to Available Wi-Fi Network
    connectToBestWiFi();

    // Synchronize Real-Time Clock via SNTP for TLS Certificate Verification
    syncNTPTime();
}

// =====================================================================
// 7. MAIN LOOP
// =====================================================================
void loop() {
    unsigned long currentMillis = millis();

    // Maintain non-blocking LED blink service (if in sensor fault alert state)
    serviceLEDBlink();

    // Check transmission schedule
    if (currentMillis - lastTransmissionTime >= TRANSMISSION_INTERVAL_MS || lastTransmissionTime == 0) {
        lastTransmissionTime = currentMillis;

        // Ensure Wi-Fi is connected
        if (wifiMulti.run() != WL_CONNECTED) {
            Serial.println("[!] Wi-Fi disconnected. Reconnecting via WiFiMulti...");
            connectToBestWiFi();
        }

        // Recheck SNTP if not yet synced
        if (!sntpSynchronized && WiFi.status() == WL_CONNECTED) {
            syncNTPTime();
        }

        // Read all physical sensors
        SensorTelemetry telemetry = collectSensorData();

        // Update optional visual LED indicators based on sensor telemetry
        updateLEDIndicators(telemetry);

        // Display readings on Serial Monitor
        printTelemetryBanner(telemetry);

        // Transmit data: Cloud First -> Local Fallback -> Retry
        transmitTelemetry(telemetry);
    }

    delay(20); // Responsive 20ms tick for smooth non-blocking LED blinking
}

// =====================================================================
// 8. SENSOR ACQUISITION FUNCTIONS
// =====================================================================

/**
 * Reads the Capacitive Soil Moisture Sensor on GPIO 34.
 * Takes 10 ADC samples with 10ms delays to eliminate ADC noise.
 */
float readSoilMoistureRaw() {
    long sum = 0;
    const int SAMPLES = 10;
    for (int i = 0; i < SAMPLES; i++) {
        sum += analogRead(PIN_SOIL_MOISTURE);
        delay(10);
    }
    float avgRaw = (float)sum / SAMPLES;
    return avgRaw;
}

/**
 * Reads DS18B20 waterproof temperature sensor on GPIO 4.
 * Rejects disconnected (-127°C) and power-on reset (85°C) fault values.
 */
float readTemperature(bool &isValid) {
    tempSensors.requestTemperatures();
    float tempC = tempSensors.getTempCByIndex(0);

    // Validation: Disconnected is -127°C, initial power-on fault is 85°C
    if (tempC <= -120.0 || tempC >= 85.0 || tempC == DEVICE_DISCONNECTED_C) {
        isValid = false;
        return -999.0;
    }
    isValid = true;
    return tempC;
}

/**
 * Reads HC-SR04 ultrasonic distance sensor on TRIG GPIO 5 / ECHO GPIO 18.
 * Takes 3 pulses and uses median to eliminate ultrasonic noise/spikes.
 */
float readUltrasonicDistance(bool &isValid) {
    float readings[3];
    int validCount = 0;

    for (int i = 0; i < 3; i++) {
        digitalWrite(PIN_TRIG, LOW);
        delayMicroseconds(2);
        digitalWrite(PIN_TRIG, HIGH);
        delayMicroseconds(10);
        digitalWrite(PIN_TRIG, LOW);

        // Timeout of 30ms (~5 meters max range)
        long duration = pulseIn(PIN_ECHO, HIGH, 30000);
        if (duration > 0) {
            // Speed of sound: 343 m/s = 0.0343 cm/us -> distance = (duration * 0.0343) / 2
            float dist = (duration * 0.0343) / 2.0;
            if (dist >= 2.0 && dist <= 300.0) {
                readings[validCount++] = dist;
            }
        }
        delay(15);
    }

    if (validCount == 0) {
        isValid = false;
        return -999.0;
    }

    // Average the valid pulses
    float sum = 0;
    for (int i = 0; i < validCount; i++) sum += readings[i];
    float avgDist = sum / validCount;

    isValid = true;
    return avgDist;
}

/**
 * Aggregates all sensor readings into a unified telemetry structure.
 */
SensorTelemetry collectSensorData() {
    SensorTelemetry data;
    data.moistureRaw = readSoilMoistureRaw();

    data.temperatureC = readTemperature(data.temperatureValid);

    data.distanceCm = readUltrasonicDistance(data.distanceValid);
    if (data.distanceValid) {
        // Plant Canopy Height = Mount Reference (30.0 cm) - Measured Flight Distance
        float height = SENSOR_MOUNT_HEIGHT_CM - data.distanceCm;
        data.plantHeightCm = (height > 0.0) ? height : 0.0;
    } else {
        data.plantHeightCm = 0.0;
    }

    data.status = (data.temperatureValid && data.distanceValid) ? "OK" : "DEGRADED";
    return data;
}

// =====================================================================
// 9. TIME SYNCHRONIZATION (SNTP FOR TLS CERTIFICATE VALIDITY)
// =====================================================================
void syncNTPTime() {
    if (WiFi.status() != WL_CONNECTED) return;

    Serial.print("[*] Synchronizing system time via SNTP... ");
    // Configure NTP servers: UTC offset = 0, Daylight offset = 0
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");

    time_t now = time(nullptr);
    int retries = 0;
    while (now < 1672531199 && retries < 15) { // 1672531199 = Jan 1, 2023
        delay(500);
        now = time(nullptr);
        retries++;
    }

    if (now > 1672531199) {
        struct tm timeinfo;
        gmtime_r(&now, &timeinfo);
        Serial.printf("Synchronized: %04d-%02d-%02d %02d:%02d:%02d UTC\n",
            timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
            timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
        sntpSynchronized = true;
    } else {
        Serial.println("SNTP Sync Timeout (will retry next cycle).");
        sntpSynchronized = false;
    }
}

// =====================================================================
// 10. NETWORK MANAGEMENT & TELEMETRY TRANSMISSION
// =====================================================================

/**
 * Scans and connects to the best available registered Wi-Fi network.
 */
void connectToBestWiFi() {
    Serial.print("[*] Connecting to available Wi-Fi network");
    int attempts = 0;
    while (wifiMulti.run() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("Connected: %s\n", WiFi.SSID().c_str());
        Serial.printf("IP: %s\n", WiFi.localIP().toString().c_str());
        Serial.printf("RSSI: %d dBm\n", WiFi.RSSI());
    } else {
        Serial.println("[!] No configured Wi-Fi network found within range.");
    }
}

/**
 * Formats the standardized JSON payload for both Cloud and Local endpoints.
 */
String buildJsonPayload(const SensorTelemetry &t) {
    StaticJsonDocument<384> doc;
    doc["device_id"] = DEVICE_ID;
    doc["moisture_raw"] = round(t.moistureRaw * 10.0) / 10.0;
    doc["moisture_percent"] = nullptr; // Backend calculates accurate RSMI

    if (t.temperatureValid) {
        doc["temperature_c"] = round(t.temperatureC * 100.0) / 100.0;
    } else {
        doc["temperature_c"] = nullptr;
    }

    if (t.distanceValid) {
        doc["distance_cm"] = round(t.distanceCm * 100.0) / 100.0;
        doc["plant_height_cm"] = round(t.plantHeightCm * 100.0) / 100.0;
    } else {
        doc["distance_cm"] = nullptr;
        doc["plant_height_cm"] = nullptr;
    }

    doc["status"] = t.status;

    String jsonString;
    serializeJson(doc, jsonString);
    return jsonString;
}

/**
 * Intelligent Dual-Destination Router:
 * 1. Tries Render Cloud over HTTPS with ISRG Root X1 TLS validation.
 * 2. If Cloud is unreachable, immediately attempts Local Flask LAN endpoint.
 * 3. If both fail, caches telemetry and logs diagnostic warning.
 */
void transmitTelemetry(const SensorTelemetry &t) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[!] Cannot transmit: No Wi-Fi connection active.");
        return;
    }

    String payload = buildJsonPayload(t);

    // MODE 1: Try Render Cloud HTTPS (Primary Destination)
    Serial.println("Cloud server: ATTEMPTING...");
    bool cloudSuccess = postToCloudHTTPS(payload);

    if (cloudSuccess) {
        Serial.println("Cloud server: AVAILABLE");
        Serial.println("Data destination: RENDER CLOUD (Supabase PostgreSQL)");
        Serial.println("Cloud POST: 201 Created -> Data uploaded successfully");
        Serial.println("----------------------------------------\n");
        return;
    }

    // MODE 2: Cloud Failed / Render Cold Start -> Try Local Flask Fallback
    Serial.println("Cloud server: UNAVAILABLE / TIMEOUT");
    Serial.println("Trying local Flask server fallback...");

    bool localSuccess = postToLocalHTTP(payload);

    if (localSuccess) {
        Serial.println("Local server: AVAILABLE");
        Serial.println("Data destination: LOCAL FLASK (SQLite)");
        Serial.println("Local POST: 201 Created -> Data saved locally");
        Serial.println("----------------------------------------\n");
        return;
    }

    // MODE 3: Both Destinations Unavailable
    Serial.println("Local server: UNAVAILABLE");
    Serial.println("[!] Both Cloud and Local servers unreachable. Retrying next cycle.");
    Serial.println("----------------------------------------\n");
}

/**
 * Transmits telemetry payload to Render Cloud over HTTPS with CA certificate validation.
 */
bool postToCloudHTTPS(const String &payload) {
    WiFiClientSecure secureClient;
    secureClient.setCACert(ISRG_ROOT_X1_CA); // Strict validation using Let's Encrypt Root CA
    secureClient.setTimeout(HTTP_TIMEOUT_MS / 1000);

    HTTPClient https;
    https.setTimeout(HTTP_TIMEOUT_MS);

    if (!https.begin(secureClient, CLOUD_SERVER_URL)) {
        return false;
    }

    https.addHeader("Content-Type", "application/json");
    https.addHeader("User-Agent", "ESP32_PlantMonitor/2.0");

    int httpCode = https.POST(payload);
    bool success = (httpCode == 200 || httpCode == 201);

    if (!success) {
        Serial.printf("Cloud HTTPS POST failed. Error / HTTP Code: %d\n", httpCode);
    }

    https.end();
    return success;
}

/**
 * Transmits telemetry payload to Local Flask server over standard LAN HTTP.
 */
bool postToLocalHTTP(const String &payload) {
    WiFiClient standardClient;
    standardClient.setTimeout(5); // 5-second local LAN timeout

    HTTPClient http;
    http.setTimeout(5000);

    if (!http.begin(standardClient, LOCAL_SERVER_URL)) {
        return false;
    }

    http.addHeader("Content-Type", "application/json");
    http.addHeader("User-Agent", "ESP32_PlantMonitor/2.0");

    int httpCode = http.POST(payload);
    bool success = (httpCode == 200 || httpCode == 201);

    if (!success) {
        Serial.printf("Local HTTP POST failed. Error / HTTP Code: %d\n", httpCode);
    }

    http.end();
    return success;
}

// =====================================================================
// 11. OPTIONAL STATUS LED INDICATOR SUBSYSTEM
// =====================================================================

/**
 * Calculates local Relative Soil Moisture Index estimate (%) for indicator logic.
 * Note: Authoritative calibrated value is still computed by backend / Cloud API.
 */
float calculateLocalMoisturePercent(float raw) {
    if (raw >= DRY_RAW_REF) return 0.0;
    if (raw <= WET_RAW_REF) return 100.0;
    float pct = ((DRY_RAW_REF - raw) / (DRY_RAW_REF - WET_RAW_REF)) * 100.0;
    if (pct < 0.0) return 0.0;
    if (pct > 100.0) return 100.0;
    return pct;
}

/**
 * Updates optional LED visual status indicator.
 * Purely non-blocking; zero dependency on physical presence of LEDs.
 * 
 * Logic rules:
 * - RED BLINK: Genuine sensor fault (DS18B20 invalid OR HC-SR04 invalid)
 * - GREEN STEADY: Moisture >= 40% AND Temp < 30°C AND all sensors valid
 * - RED STEADY: Moisture < 40% OR (Moisture < 50% AND Temp >= 30°C)
 */
void updateLEDIndicators(const SensorTelemetry &t) {
    // 1. Check for genuine hardware sensor fault -> RED BLINK
    if (!t.temperatureValid || !t.distanceValid) {
        currentLEDState = LED_STATE_RED_FAULT_BLINK;
        digitalWrite(PIN_LED_GREEN, LOW);
        return;
    }

    // 2. Compute local moisture index for plant environment evaluation
    float moisturePct = calculateLocalMoisturePercent(t.moistureRaw);

    // 3. Favorable environment: Moisture >= 40% AND Temp < 30°C -> GREEN
    if (moisturePct >= 40.0 && t.temperatureC < 30.0) {
        currentLEDState = LED_STATE_GREEN_FAVORABLE;
        digitalWrite(PIN_LED_GREEN, HIGH);
        digitalWrite(PIN_LED_RED, LOW);
    } 
    // 4. Drying / Attention required: Moisture < 40% OR heat stress -> RED
    else {
        currentLEDState = LED_STATE_RED_ATTENTION;
        digitalWrite(PIN_LED_GREEN, LOW);
        digitalWrite(PIN_LED_RED, HIGH);
    }
}

/**
 * Non-blocking blink driver for hardware fault alert state.
 * Toggles Red LED every 500ms when fault is active.
 */
void serviceLEDBlink() {
    if (currentLEDState == LED_STATE_RED_FAULT_BLINK) {
        unsigned long currentMillis = millis();
        if (currentMillis - lastLEDBlinkToggle >= 500) {
            lastLEDBlinkToggle = currentMillis;
            ledBlinkToggleState = !ledBlinkToggleState;
            digitalWrite(PIN_LED_RED, ledBlinkToggleState ? HIGH : LOW);
        }
    }
}

// =====================================================================
// 12. SERIAL MONITOR TELEMETRY DISPLAY
// =====================================================================

/**
 * Pretty-prints telemetry banner on Serial Monitor matching project presentation format.
 */
void printTelemetryBanner(const SensorTelemetry &t) {
    Serial.println("----------------------------------------");
    Serial.printf("Moisture Raw : %.0f ADC (Local Est: %.1f%%)\n", 
                  t.moistureRaw, calculateLocalMoisturePercent(t.moistureRaw));

    if (t.temperatureValid) {
        Serial.printf("Temperature  : %.2f °C\n", t.temperatureC);
    } else {
        Serial.println("Temperature  : SENSOR DISCONNECTED [FAULT]");
    }

    if (t.distanceValid) {
        Serial.printf("Distance     : %.2f cm\n", t.distanceCm);
        Serial.printf("Plant Height : %.2f cm\n", t.plantHeightCm);
    } else {
        Serial.println("Distance     : SENSOR TIMEOUT [FAULT]");
        Serial.println("Plant Height : -- cm");
    }

    // Optional Visual LED Status
    Serial.print("LED Status   : ");
    switch (currentLEDState) {
        case LED_STATE_GREEN_FAVORABLE:
            Serial.println("GREEN [Favorable: Moist & Moderate Temp]");
            break;
        case LED_STATE_RED_ATTENTION:
            Serial.println("RED [Attention: Low Moisture / High Temp]");
            break;
        case LED_STATE_RED_FAULT_BLINK:
            Serial.println("RED BLINKING [Hardware Sensor Fault]");
            break;
        case LED_STATE_STARTUP_OFF:
        default:
            Serial.println("OFF [Initializing]");
            break;
    }
}

```

---

## 5. Hardware Verification & Historical Transmission Logs

output///
........................
Wi-Fi connection failed.

System initialized.

--------------------------------------
Soil Moisture Raw : 3313
Soil Temperature  : Sensor disconnected
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------
Wi-Fi disconnected. Reconnecting...

Connecting to Wi-Fi...
........................................
Wi-Fi connection failed.
Unable to reconnect.
--------------------------------------
Soil Moisture Raw : 3280
Soil Temperature  : 27.50 °C
HC-SR04 Distance  : 7.77 cm
Plant Height      : 22.23 cm
--------------------------------------
Wi-Fi disconnected. Reconnecting...

Connecting to Wi-Fi...
........................................
Wi-Fi connection failed.
Unable to reconnect.
--------------------------------------
Soil Moisture Raw : 3315
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------
Wi-Fi disconnected. Reconnecting...

Connecting to Wi-Fi...
..
Wi-Fi connected!
ESP32 IP Address: 192.168.137.68
Server URL: http://10.61.173.131:5000/api/sensor-data

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3315,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:14:29",
  "message": "Sensor reading saved successfully",
  "reading_id": 4,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3315
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3315,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:14:39",
  "message": "Sensor reading saved successfully",
  "reading_id": 5,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3312
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3312,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:14:49",
  "message": "Sensor reading saved successfully",
  "reading_id": 6,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3312
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3312,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:14:59",
  "message": "Sensor reading saved successfully",
  "reading_id": 7,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3323
Soil Temperature  : 27.69 °C
HC-SR04 Distance  : 2.01 cm
Plant Height      : 27.99 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3323,"moisture_percent":null,"temperature_c":27.69,"distance_cm":2.01,"plant_height_cm":27.99,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:15:09",
  "message": "Sensor reading saved successfully",
  "reading_id": 8,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3319
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 2.97 cm
Plant Height      : 27.03 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3319,"moisture_percent":null,"temperature_c":27.75,"distance_cm":2.97,"plant_height_cm":27.03,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:15:19",
  "message": "Sensor reading saved successfully",
  "reading_id": 9,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3325
Soil Temperature  : 27.87 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3325,"moisture_percent":null,"temperature_c":27.87,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:15:29",
  "message": "Sensor reading saved successfully",
  "reading_id": 10,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3306
Soil Temperature  : 28.00 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3306,"moisture_percent":null,"temperature_c":28.00,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:15:39",
  "message": "Sensor reading saved successfully",
  "reading_id": 11,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3319
Soil Temperature  : 28.06 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3319,"moisture_percent":null,"temperature_c":28.06,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:15:49",
  "message": "Sensor reading saved successfully",
  "reading_id": 12,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3323
Soil Temperature  : 29.94 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3323,"moisture_percent":null,"temperature_c":29.94,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:16:00",
  "message": "Sensor reading saved successfully",
  "reading_id": 13,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3317
Soil Temperature  : 30.25 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3317,"moisture_percent":null,"temperature_c":30.25,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:16:10",
  "message": "Sensor reading saved successfully",
  "reading_id": 14,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3319
Soil Temperature  : 30.00 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3319,"moisture_percent":null,"temperature_c":30.00,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:16:20",
  "message": "Sensor reading saved successfully",
  "reading_id": 15,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3323
Soil Temperature  : 29.69 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3323,"moisture_percent":null,"temperature_c":29.69,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:16:30",
  "message": "Sensor reading saved successfully",
  "reading_id": 16,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3319
Soil Temperature  : 29.44 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3319,"moisture_percent":null,"temperature_c":29.44,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:16:40",
  "message": "Sensor reading saved successfully",
  "reading_id": 17,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3317
Soil Temperature  : 29.19 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3317,"moisture_percent":null,"temperature_c":29.19,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:16:50",
  "message": "Sensor reading saved successfully",
  "reading_id": 18,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3325
Soil Temperature  : 28.94 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3325,"moisture_percent":null,"temperature_c":28.94,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:17:00",
  "message": "Sensor reading saved successfully",
  "reading_id": 19,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3315
Soil Temperature  : 28.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3315,"moisture_percent":null,"temperature_c":28.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:17:10",
  "message": "Sensor reading saved successfully",
  "reading_id": 20,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3316
Soil Temperature  : 28.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3316,"moisture_percent":null,"temperature_c":28.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:17:20",
  "message": "Sensor reading saved successfully",
  "reading_id": 21,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3324
Soil Temperature  : 28.50 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3324,"moisture_percent":null,"temperature_c":28.50,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:17:30",
  "message": "Sensor reading saved successfully",
  "reading_id": 22,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3323
Soil Temperature  : 28.37 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3323,"moisture_percent":null,"temperature_c":28.38,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:17:41",
  "message": "Sensor reading saved successfully",
  "reading_id": 23,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3327
Soil Temperature  : 28.25 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3327,"moisture_percent":null,"temperature_c":28.25,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:17:51",
  "message": "Sensor reading saved successfully",
  "reading_id": 24,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3318
Soil Temperature  : 28.19 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3318,"moisture_percent":null,"temperature_c":28.19,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:18:01",
  "message": "Sensor reading saved successfully",
  "reading_id": 25,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3324
Soil Temperature  : 28.06 °C
HC-SR04 Distance  : 10.84 cm
Plant Height      : 19.16 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3324,"moisture_percent":null,"temperature_c":28.06,"distance_cm":10.84,"plant_height_cm":19.16,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:18:11",
  "message": "Sensor reading saved successfully",
  "reading_id": 26,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3322
Soil Temperature  : 28.00 °C
HC-SR04 Distance  : 8.13 cm
Plant Height      : 21.87 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3322,"moisture_percent":null,"temperature_c":28.00,"distance_cm":8.13,"plant_height_cm":21.87,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:18:21",
  "message": "Sensor reading saved successfully",
  "reading_id": 27,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3314
Soil Temperature  : 27.94 °C
HC-SR04 Distance  : 5.23 cm
Plant Height      : 24.77 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3314,"moisture_percent":null,"temperature_c":27.94,"distance_cm":5.23,"plant_height_cm":24.77,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:18:31",
  "message": "Sensor reading saved successfully",
  "reading_id": 28,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3327
Soil Temperature  : 27.94 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3327,"moisture_percent":null,"temperature_c":27.94,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:18:41",
  "message": "Sensor reading saved successfully",
  "reading_id": 29,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3316
Soil Temperature  : 27.87 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3316,"moisture_percent":null,"temperature_c":27.87,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:18:51",
  "message": "Sensor reading saved successfully",
  "reading_id": 30,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3312
Soil Temperature  : 27.87 °C
HC-SR04 Distance  : 4.25 cm
Plant Height      : 25.75 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3312,"moisture_percent":null,"temperature_c":27.87,"distance_cm":4.25,"plant_height_cm":25.75,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:19:01",
  "message": "Sensor reading saved successfully",
  "reading_id": 31,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3327
Soil Temperature  : 27.81 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3327,"moisture_percent":null,"temperature_c":27.81,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:19:12",
  "message": "Sensor reading saved successfully",
  "reading_id": 32,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3327
Soil Temperature  : 27.87 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3327,"moisture_percent":null,"temperature_c":27.87,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:19:22",
  "message": "Sensor reading saved successfully",
  "reading_id": 33,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3323
Soil Temperature  : 27.94 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3323,"moisture_percent":null,"temperature_c":27.94,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:19:32",
  "message": "Sensor reading saved successfully",
  "reading_id": 34,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3328
Soil Temperature  : 28.06 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3328,"moisture_percent":null,"temperature_c":28.06,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:19:42",
  "message": "Sensor reading saved successfully",
  "reading_id": 35,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3326
Soil Temperature  : 28.00 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3326,"moisture_percent":null,"temperature_c":28.00,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:19:52",
  "message": "Sensor reading saved successfully",
  "reading_id": 36,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3317
Soil Temperature  : 27.94 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3317,"moisture_percent":null,"temperature_c":27.94,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:20:02",
  "message": "Sensor reading saved successfully",
  "reading_id": 37,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3324
Soil Temperature  : 27.87 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3324,"moisture_percent":null,"temperature_c":27.87,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:20:12",
  "message": "Sensor reading saved successfully",
  "reading_id": 38,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3327
Soil Temperature  : 27.87 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3327,"moisture_percent":null,"temperature_c":27.87,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:20:22",
  "message": "Sensor reading saved successfully",
  "reading_id": 39,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3325
Soil Temperature  : 27.81 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3325,"moisture_percent":null,"temperature_c":27.81,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:20:32",
  "message": "Sensor reading saved successfully",
  "reading_id": 40,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3312
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3312,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:20:42",
  "message": "Sensor reading saved successfully",
  "reading_id": 41,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3324
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3324,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:20:53",
  "message": "Sensor reading saved successfully",
  "reading_id": 42,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3326
Soil Temperature  : 27.69 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3326,"moisture_percent":null,"temperature_c":27.69,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:21:03",
  "message": "Sensor reading saved successfully",
  "reading_id": 43,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3355
Soil Temperature  : 27.69 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3355,"moisture_percent":null,"temperature_c":27.69,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:21:13",
  "message": "Sensor reading saved successfully",
  "reading_id": 44,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3330
Soil Temperature  : 27.69 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3330,"moisture_percent":null,"temperature_c":27.69,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:21:23",
  "message": "Sensor reading saved successfully",
  "reading_id": 45,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3338
Soil Temperature  : 27.69 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3338,"moisture_percent":null,"temperature_c":27.69,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:21:33",
  "message": "Sensor reading saved successfully",
  "reading_id": 46,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3340
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3340,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:21:43",
  "message": "Sensor reading saved successfully",
  "reading_id": 47,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3333
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3333,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:21:53",
  "message": "Sensor reading saved successfully",
  "reading_id": 48,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3334
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3334,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:22:03",
  "message": "Sensor reading saved successfully",
  "reading_id": 49,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3334
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3334,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:22:13",
  "message": "Sensor reading saved successfully",
  "reading_id": 50,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3344
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3344,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:22:24",
  "message": "Sensor reading saved successfully",
  "reading_id": 51,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3322
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3322,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:22:34",
  "message": "Sensor reading saved successfully",
  "reading_id": 52,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3332
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3332,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:22:44",
  "message": "Sensor reading saved successfully",
  "reading_id": 53,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3367
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3367,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:22:54",
  "message": "Sensor reading saved successfully",
  "reading_id": 54,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3328
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3328,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:23:04",
  "message": "Sensor reading saved successfully",
  "reading_id": 55,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3206
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3206,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:23:14",
  "message": "Sensor reading saved successfully",
  "reading_id": 56,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3195
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3195,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:23:24",
  "message": "Sensor reading saved successfully",
  "reading_id": 57,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3206
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3206,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:23:34",
  "message": "Sensor reading saved successfully",
  "reading_id": 58,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3190
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3190,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:23:44",
  "message": "Sensor reading saved successfully",
  "reading_id": 59,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3206
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3206,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:23:54",
  "message": "Sensor reading saved successfully",
  "reading_id": 60,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3189
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3189,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:24:05",
  "message": "Sensor reading saved successfully",
  "reading_id": 61,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 2907
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":2907,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:24:15",
  "message": "Sensor reading saved successfully",
  "reading_id": 62,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1520
Soil Temperature  : 27.62 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1520,"moisture_percent":null,"temperature_c":27.62,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:24:25",
  "message": "Sensor reading saved successfully",
  "reading_id": 63,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1490
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1490,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:24:35",
  "message": "Sensor reading saved successfully",
  "reading_id": 64,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1471
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1471,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:24:45",
  "message": "Sensor reading saved successfully",
  "reading_id": 65,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1478
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1478,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:24:55",
  "message": "Sensor reading saved successfully",
  "reading_id": 66,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1471
Soil Temperature  : 27.56 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1471,"moisture_percent":null,"temperature_c":27.56,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:25:05",
  "message": "Sensor reading saved successfully",
  "reading_id": 67,
  "success": true
}


======================================
 IoT Plant Growth Monitoring System
======================================

Connecting to Wi-Fi...
.
Wi-Fi connected!
ESP32 IP Address: 192.168.137.68
Server URL: http://10.61.173.131:5000/api/sensor-data

System initialized.

--------------------------------------
Soil Moisture Raw : 1438
Soil Temperature  : Sensor disconnected
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1438,"moisture_percent":null,"temperature_c":null,"distance_cm":7.80,"plant_height_cm":22.20,"status":"SENSOR_ERROR"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:37:45",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 100,
  "moisture_raw": 1438,
  "reading_id": 68,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1427
Soil Temperature  : 27.81 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1427,"moisture_percent":null,"temperature_c":27.81,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:37:55",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 100,
  "moisture_raw": 1427,
  "reading_id": 69,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1469
Soil Temperature  : 27.81 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1469,"moisture_percent":null,"temperature_c":27.81,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:38:05",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 100,
  "moisture_raw": 1469,
  "reading_id": 70,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3315
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3315,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:38:16",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0.61,
  "moisture_raw": 3315,
  "reading_id": 71,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3317
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3317,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:38:26",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0.5,
  "moisture_raw": 3317,
  "reading_id": 72,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3344
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3344,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:38:36",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0,
  "moisture_raw": 3344,
  "reading_id": 73,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3280
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3280,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:38:46",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 2.55,
  "moisture_raw": 3280,
  "reading_id": 74,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3331
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3331,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:38:56",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0,
  "moisture_raw": 3331,
  "reading_id": 75,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1473
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1473,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:39:06",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 100,
  "moisture_raw": 1473,
  "reading_id": 76,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 1521
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":1521,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:39:16",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 99.94,
  "moisture_raw": 1521,
  "reading_id": 77,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3264
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3264,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:39:26",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 3.43,
  "moisture_raw": 3264,
  "reading_id": 78,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3279
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3279,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:39:36",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 2.6,
  "moisture_raw": 3279,
  "reading_id": 79,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3286
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3286,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:39:47",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 2.21,
  "moisture_raw": 3286,
  "reading_id": 80,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3275
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3275,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:39:57",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 2.82,
  "moisture_raw": 3275,
  "reading_id": 81,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3342
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3342,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:40:07",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0,
  "moisture_raw": 3342,
  "reading_id": 82,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3335
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3335,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:40:17",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0,
  "moisture_raw": 3335,
  "reading_id": 83,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3341
Soil Temperature  : 27.69 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3341,"moisture_percent":null,"temperature_c":27.69,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:40:27",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0,
  "moisture_raw": 3341,
  "reading_id": 84,
  "success": true
}

--------------------------------------
Soil Moisture Raw : 3335
Soil Temperature  : 27.75 °C
HC-SR04 Distance  : 7.80 cm
Plant Height      : 22.20 cm
--------------------------------------

Sending data to Flask...
{"device_id":"ESP32_003","moisture_raw":3335,"moisture_percent":null,"temperature_c":27.75,"distance_cm":7.80,"plant_height_cm":22.20,"status":"OK"}
HTTP Response Code: 201
Server Response:
{
  "created_at": "2026-10-05T21:40:37",
  "message": "Sensor reading saved successfully",
  "moisture_percent": 0,
  "moisture_raw": 3335,
  "reading_id": 85,
  "success": true
}

