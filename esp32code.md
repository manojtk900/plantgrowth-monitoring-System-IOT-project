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
 * IoT-Based Plant Growth & Environmental Monitoring System
 * Edge Node Firmware — ESP32 DevKit V1 (Device ID: ESP32_003)
 * 
 * Features:
 *   - NVS Wi-Fi Provisioning via Web Portal (Preferences + SoftAP + WebServer)
 *   - Multi-Wi-Fi fallback (WiFiMulti with 3 persistent NVS credential slots)
 *   - Dual-destination telemetry (Render Cloud HTTPS first, local Flask LAN fallback)
 *   - Strict TLS validation (Google Trust Services GTS Root R4 + ISRG Root X1 CA)
 *   - SNTP time synchronization for certificate validity
 *   - Capacitive Soil Moisture (GPIO 34)
 *   - DS18B20 Temperature (GPIO 4)
 *   - HC-SR04 Ultrasonic Distance & Canopy Height (TRIG GPIO 5, ECHO GPIO 18)
 *   - Optional visual status indicators (Green LED GPIO 25, Red LED GPIO 26)
 *   - Authoritative backend calibration contract (moisture_percent: null)
 */

#include <WiFi.h>
#include <WiFiMulti.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include "time.h"

// 1. Hardware Configuration & Pins
#define PIN_SOIL_MOISTURE  34   // ADC1_CH6 (Capacitive sensor analog output)
#define PIN_ONE_WIRE_BUS    4   // DS18B20 Data (4.7kΩ pull-up to 3.3V)
#define PIN_TRIG            5   // HC-SR04 Trigger
#define PIN_ECHO           18   // HC-SR04 Echo (1kΩ/2kΩ voltage divider)

// Optional Visual Indicators (Plug-and-play, zero-dependency)
#define PIN_LED_GREEN      25   // Optional Green LED (220Ω series resistor to GND)
#define PIN_LED_RED        26   // Optional Red LED (220Ω series resistor to GND)

// Relative Soil Moisture Index (RSMI) Local Calibration Reference
const float DRY_RAW_REF = 3326.0; // Air / Dry reference (0% RSMI)
const float WET_RAW_REF = 1520.0; // Water / Wet reference (100% RSMI)

const char* DEVICE_ID = "ESP32_003";
const float SENSOR_MOUNT_HEIGHT_CM = 30.0;
const unsigned long TRANSMISSION_INTERVAL_MS = 10000;

// 2. Provisioning & NVS Preferences
Preferences prefs;
WebServer setupServer(80);
DNSServer dnsServer;
bool inSetupPortalMode = false;
unsigned long portalStartTime = 0;
const unsigned long PORTAL_TIMEOUT_MS = 180000; // 3 minutes portal timeout

// Default Wi-Fi (Baked-in default for Slot 1)
const char* DEFAULT_SSID_1 = "manojtk";
const char* DEFAULT_PASS_1 = "manojtk900";

// 3. Server Endpoints & TLS Root Certificates
const char* CLOUD_SERVER_URL = "https://plantgrowth-monitoring-system-iot-project.onrender.com/api/sensor-data";
const char* LOCAL_SERVER_URL = "http://10.61.173.131:5000/api/sensor-data";
const int HTTP_TIMEOUT_MS = 15000;

const char* ROOT_CA_BUNDLE = \
"-----BEGIN CERTIFICATE-----\n" \
"MIICCTCCAY6gAwIBAgINAgPlwGjvYxqccpBQUjAKBggqhkjOPQQDAzBHMQswCQYD\n" \
"VQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZpY2VzIExMQzEUMBIG\n" \
"A1UEAxMLR1RTIFJvb3QgUjQwHhcNMTYwNjIyMDAwMDAwWhcNMzYwNjIyMDAwMDAw\n" \
"WjBHMQswCQYDVQQGEwJVUzEiMCAGA1UEChMZR29vZ2xlIFRydXN0IFNlcnZpY2Vz\n" \
"IExMQzEUMBIGA1UEAxMLR1RTIFJvb3QgUjQwdjAQBgcqhkjOPQIBBgUrgQQAIgNi\n" \
"AATzdHOnaItgrkO4NcWBMHtLSZ37wWHO5t5GvWvVYRg1rkDdc/eJkTBa6zzuhXyi\n" \
"QHY7qca4R9gq55KRanPpsXI5nymfopjTX15YhmUPoYRlBtHci8nHc8iMai/lxKvR\n" \
"HYqjQjBAMA4GA1UdDwEB/wQEAwIBhjAPBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQW\n" \
"BBSATNbrdP9JNqPV2Py1PsVq8JQdjDAKBggqhkjOPQQDAwNpADBmAjEA6ED/g94D\n" \
"9J+uHXqnLrmvT/aDHQ4thQEd0dlq7A/Cr8deVl5c1RxYIigL9zC2L7F8AjEA8GE8\n" \
"p/SgguMh1YQdc4acLa/KNJvxn7kjNuK8YAOdgLOaVsjh4rsUecrNIdSUtUlD\n" \
"-----END CERTIFICATE-----\n" \
"-----BEGIN CERTIFICATE-----\n" \
"MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw\n" \
"TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh\n" \
"cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4\n" \
"WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu\n" \
"ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY\n" \
"MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc\n" \
"h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+\n" \
"0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U\n" \
"A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW\n" \
"T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH\n" \
"B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC\n" \
"B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv\n" \
"KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn\n" \
"OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn\n" \
"jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw\n" \
"qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI\n" \
"rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV\n" \
"HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq\n" \
"hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL\n" \
"ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ\n" \
"3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK\n" \
"NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5\n" \
"ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur\n" \
"TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC\n" \
"jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc\n" \
"oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq\n" \
"4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA\n" \
"mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d\n"
"emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=\n" \
"-----END CERTIFICATE-----\n";

// 4. Drivers & State Variables
WiFiMulti wifiMulti;
OneWire oneWire(PIN_ONE_WIRE_BUS);
DallasTemperature tempSensors(&oneWire);

unsigned long lastTransmissionTime = 0;
bool sntpSynchronized = false;
int consecutiveFaultCycles = 0;
const int FAULT_THRESHOLD = 2;

enum LEDIndicatorState {
    LED_STATE_STARTUP_OFF,     // Startup default: Both LEDs OFF
    LED_STATE_GREEN_FAVORABLE, // Green Steady: Moisture >= 40% AND Temp < 30°C AND sensors valid
    LED_STATE_RED_ATTENTION,   // Red Steady: Moisture < 40% OR heat stress
    LED_STATE_RED_FAULT_BLINK, // Red Blink: Persistent hardware sensor fault
    LED_STATE_SETUP_PORTAL     // Alternating Green/Red Blink: Provisioning portal active
};

LEDIndicatorState currentLEDState = LED_STATE_STARTUP_OFF;
unsigned long lastLEDBlinkToggle = 0;
bool ledBlinkToggleState = false;

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
void loadSavedWiFiCredentials();
bool connectToConfiguredWiFi();
void startSetupPortal();
void handlePortalRoot();
void handlePortalSave();
void syncNTPTime();
SensorTelemetry collectSensorData();
float calculateLocalMoisturePercent(float raw);
void updateLEDIndicators(const SensorTelemetry &t);
void serviceLEDBlink();
void printTelemetryBanner(const SensorTelemetry &t);
void transmitTelemetry(const SensorTelemetry &t);
bool postToCloudHTTPS(const String &payload);
bool postToLocalHTTP(const String &payload);

// 5. Setup Routine
void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println("\n========================================");
    Serial.println(" IoT Plant Growth Monitoring System");
    Serial.printf (" Device ID: %s\n", DEVICE_ID);
    Serial.println("========================================");

    // Initialize Sensor GPIOs (Strictly unchanged wiring)
    pinMode(PIN_SOIL_MOISTURE, INPUT);
    pinMode(PIN_TRIG, OUTPUT);
    digitalWrite(PIN_TRIG, LOW);
    pinMode(PIN_ECHO, INPUT);

    // Initialize Optional Visual Indicator LEDs
    pinMode(PIN_LED_GREEN, OUTPUT);
    pinMode(PIN_LED_RED, OUTPUT);
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_RED, LOW);

    // Initialize DS18B20 Temperature Sensor
    tempSensors.begin();
    tempSensors.setResolution(11);

    // Open NVS Preferences namespace
    prefs.begin("plant_wifi", false);

    // Load credentials from NVS into WiFiMulti
    loadSavedWiFiCredentials();

    // Attempt connecting to saved Wi-Fi networks
    if (!connectToConfiguredWiFi()) {
        Serial.println("[!] No saved Wi-Fi network reachable.");
        Serial.println("[*] Entering Provisioning Mode: Broadcasting Setup Portal...");
        startSetupPortal();
    } else {
        syncNTPTime();
    }
}

// 6. Main Loop
void loop() {
    // A. Provisioning Portal Mode
    if (inSetupPortalMode) {
        dnsServer.processNextRequest();
        setupServer.handleClient();

        // Distinctive alternating visual cue on LEDs during setup mode
        unsigned long now = millis();
        if (now - lastLEDBlinkToggle >= 300) {
            lastLEDBlinkToggle = now;
            ledBlinkToggleState = !ledBlinkToggleState;
            digitalWrite(PIN_LED_GREEN, ledBlinkToggleState ? HIGH : LOW);
            digitalWrite(PIN_LED_RED, ledBlinkToggleState ? LOW : HIGH);
        }

        // Automatic timeout to re-attempt saved networks
        if (now - portalStartTime > PORTAL_TIMEOUT_MS) {
            Serial.println("[*] Portal timeout reached. Retrying saved Wi-Fi networks...");
            ESP.restart();
        }
        delay(10);
        return;
    }

    // B. Normal Telemetry Mode
    unsigned long currentMillis = millis();

    // Maintain non-blocking LED blink service (if fault alert active)
    serviceLEDBlink();

    // Telemetry transmission cycle
    if (currentMillis - lastTransmissionTime >= TRANSMISSION_INTERVAL_MS || lastTransmissionTime == 0) {
        lastTransmissionTime = currentMillis;

        if (wifiMulti.run() != WL_CONNECTED) {
            Serial.println("[!] Wi-Fi disconnected. Reconnecting via WiFiMulti...");
            if (!connectToConfiguredWiFi()) {
                Serial.println("[!] Connection failed. Launching setup portal...");
                startSetupPortal();
                return;
            }
        }

        if (!sntpSynchronized && WiFi.status() == WL_CONNECTED) {
            syncNTPTime();
        }

        SensorTelemetry telemetry = collectSensorData();
        updateLEDIndicators(telemetry);
        printTelemetryBanner(telemetry);
        transmitTelemetry(telemetry);
    }

    delay(20);
}

// 7. Wi-Fi Management & NVS Provisioning
void loadSavedWiFiCredentials() {
    // Slot 1: Default preferred network (defaults to manojtk)
    String s1 = prefs.getString("ssid1", DEFAULT_SSID_1);
    String p1 = prefs.getString("pass1", DEFAULT_PASS_1);
    // Slot 2: Optional saved network
    String s2 = prefs.getString("ssid2", "");
    String p2 = prefs.getString("pass2", "");
    // Slot 3: Optional saved network
    String s3 = prefs.getString("ssid3", "");
    String p3 = prefs.getString("pass3", "");

    Serial.println("Registered Wi-Fi Networks (NVS):");
    if (s1.length() > 0) {
        wifiMulti.addAP(s1.c_str(), p1.c_str());
        Serial.printf(" [Slot 1] %s (Default/Active)\n", s1.c_str());
    }
    if (s2.length() > 0) {
        wifiMulti.addAP(s2.c_str(), p2.c_str());
        Serial.printf(" [Slot 2] %s (Saved)\n", s2.c_str());
    }
    if (s3.length() > 0) {
        wifiMulti.addAP(s3.c_str(), p3.c_str());
        Serial.printf(" [Slot 3] %s (Saved)\n", s3.c_str());
    }
}

bool connectToConfiguredWiFi() {
    Serial.print("[*] Connecting to available Wi-Fi");
    int attempts = 0;
    while (wifiMulti.run() != WL_CONNECTED && attempts < 25) {
        delay(400);
        Serial.print(".");
        attempts++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("Connected: %s (IP: %s, RSSI: %d dBm)\n",
                      WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
        return true;
    }
    return false;
}

void startSetupPortal() {
    inSetupPortalMode = true;
    currentLEDState = LED_STATE_SETUP_PORTAL;
    portalStartTime = millis();

    WiFi.disconnect(true);
    delay(100);
    WiFi.mode(WIFI_AP);
    WiFi.softAP("ESP32-PlantMonitor-Setup");
    delay(500);

    IPAddress apIP = WiFi.softAPIP();
    dnsServer.start(53, "*", apIP);

    setupServer.on("/", handlePortalRoot);
    setupServer.on("/save", HTTP_POST, handlePortalSave);
    setupServer.onNotFound(handlePortalRoot);
    setupServer.begin();

    Serial.println("\n========================================");
    Serial.println(" Wi-Fi Setup Portal Active!");
    Serial.println(" 1. Connect phone/laptop to Wi-Fi:");
    Serial.println("    SSID: ESP32-PlantMonitor-Setup (No password)");
    Serial.printf (" 2. Open Browser: http://%s\n", apIP.toString().c_str());
    Serial.println("========================================\n");
}

void handlePortalRoot() {
    String s1 = prefs.getString("ssid1", DEFAULT_SSID_1);
    String s2 = prefs.getString("ssid2", "(None)");
    String s3 = prefs.getString("ssid3", "(None)");

    // Scan for nearby Wi-Fi networks
    int n = WiFi.scanNetworks();
    String scanOptions = "";
    if (n > 0) {
        for (int i = 0; i < n; ++i) {
            String ssid = WiFi.SSID(i);
            int rssi = WiFi.RSSI(i);
            scanOptions += "<option value='" + ssid + "'>" + ssid + " (" + String(rssi) + " dBm)</option>";
        }
    } else {
        scanOptions = "<option value=''>No networks detected</option>";
    }

    String html = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>ESP32 Plant Monitor Setup</title>"
        "<style>"
        "body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;padding:20px;margin:0;display:flex;justify-content:center;}"
        ".card{background:#1e293b;border-radius:12px;padding:24px;max-width:400px;width:100%;box-shadow:0 10px 25px rgba(0,0,0,0.5);border:1px solid #334155;}"
        "h2{color:#10b981;margin-top:0;font-size:20px;display:flex;align-items:center;gap:8px;}"
        ".badge{background:#064e3b;color:#34d399;padding:4px 8px;border-radius:6px;font-size:12px;font-weight:600;}"
        "label{display:block;font-size:13px;color:#94a3b8;margin-top:14px;margin-bottom:6px;font-weight:500;}"
        "select,input{width:100%;padding:10px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#f8fafc;font-size:14px;box-sizing:border-box;}"
        "select:focus,input:focus{outline:none;border-color:#10b981;}"
        "button{width:100%;background:#10b981;color:#0f172a;font-weight:700;border:none;padding:12px;border-radius:8px;font-size:15px;margin-top:20px;cursor:pointer;}"
        "button:hover{background:#059669;}"
        ".saved{background:#0f172a;border-radius:8px;padding:12px;margin-top:16px;font-size:13px;border:1px solid #334155;}"
        ".saved div{margin-bottom:4px;color:#cbd5e1;}"
        ".saved span{color:#10b981;font-weight:600;}"
        "</style></head><body>"
        "<div class='card'>"
        "<h2>🌱 ESP32 Plant Monitor <span class='badge'>Device: ESP32_003</span></h2>"
        "<div class='saved'>"
        "<strong>Currently Saved Networks:</strong>"
        "<div>Slot 1: <span>" + s1 + "</span></div>"
        "<div>Slot 2: <span>" + s2 + "</span></div>"
        "<div>Slot 3: <span>" + s3 + "</span></div>"
        "</div>"
        "<form method='POST' action='/save'>"
        "<label>Select Scanned Network:</label>"
        "<select onchange='if(this.value)document.getElementById(\"c_ssid\").value=this.value;'>"
        "<option value=''>-- Select detected Wi-Fi --</option>" + scanOptions + "</select>"
        "<label>Or Enter SSID Manually:</label>"
        "<input type='text' id='c_ssid' name='ssid' placeholder='Wi-Fi Name (SSID)' required>"
        "<label>Password:</label>"
        "<input type='password' name='password' placeholder='Wi-Fi Password'>"
        "<label>Save to Slot:</label>"
        "<select name='slot'>"
        "<option value='2' selected>Slot 2 (College / Secondary Wi-Fi)</option>"
        "<option value='3'>Slot 3 (Hotspot / Alternate)</option>"
        "<option value='1'>Slot 1 (Override Default 'manojtk')</option>"
        "</select>"
        "<button type='submit'>💾 Save Credentials & Connect</button>"
        "</form></div></body></html>";

    setupServer.send(200, "text/html", html);
}

void handlePortalSave() {
    if (setupServer.hasArg("ssid")) {
        String newSSID = setupServer.arg("ssid");
        String newPass = setupServer.arg("password");
        int slot = setupServer.hasArg("slot") ? setupServer.arg("slot").toInt() : 2;
        if (slot < 1 || slot > 3) slot = 2;

        String keyS = "ssid" + String(slot);
        String keyP = "pass" + String(slot);
        prefs.putString(keyS.c_str(), newSSID);
        prefs.putString(keyP.c_str(), newPass);

        String resp = "<!DOCTYPE html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>body{font-family:system-ui;background:#0f172a;color:#f8fafc;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;}"
            ".card{background:#1e293b;padding:30px;border-radius:12px;text-align:center;border:1px solid #10b981;}</style></head>"
            "<body><div class='card'><h2>✅ Wi-Fi Saved!</h2>"
            "<p>Saved <strong>" + newSSID + "</strong> to Slot " + String(slot) + ".</p>"
            "<p>Restarting ESP32 and connecting now...</p></div></body></html>";

        setupServer.send(200, "text/html", resp);
        Serial.printf("\n[+] Saved new Wi-Fi credentials to Slot %d (SSID: %s)!\n", slot, newSSID.c_str());
        Serial.println("[*] Rebooting ESP32 in 2 seconds...");
        delay(2000);
        ESP.restart();
    } else {
        setupServer.send(400, "text/plain", "Missing SSID parameter.");
    }
}

// 8. Sensor Acquisition
float readSoilMoistureRaw() {
    long sum = 0;
    const int SAMPLES = 10;
    for (int i = 0; i < SAMPLES; i++) {
        sum += analogRead(PIN_SOIL_MOISTURE);
        delay(10);
    }
    return (float)sum / SAMPLES;
}

float readTemperature(bool &isValid) {
    tempSensors.requestTemperatures();
    float tempC = tempSensors.getTempCByIndex(0);

    if (tempC <= -120.0 || tempC >= 85.0 || tempC == DEVICE_DISCONNECTED_C) {
        isValid = false;
        return -999.0;
    }
    isValid = true;
    return tempC;
}

float readUltrasonicDistance(bool &isValid) {
    float readings[3];
    int validCount = 0;

    for (int i = 0; i < 3; i++) {
        digitalWrite(PIN_TRIG, LOW);
        delayMicroseconds(2);
        digitalWrite(PIN_TRIG, HIGH);
        delayMicroseconds(10);
        digitalWrite(PIN_TRIG, LOW);

        long duration = pulseIn(PIN_ECHO, HIGH, 30000);
        if (duration > 0) {
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

    // Average up to 3 valid readings
    float sum = 0;
    for (int i = 0; i < validCount; i++) sum += readings[i];
    isValid = true;
    return sum / validCount;
}

SensorTelemetry collectSensorData() {
    SensorTelemetry data;
    data.moistureRaw = readSoilMoistureRaw();
    data.temperatureC = readTemperature(data.temperatureValid);
    data.distanceCm = readUltrasonicDistance(data.distanceValid);

    if (data.distanceValid) {
        float height = SENSOR_MOUNT_HEIGHT_CM - data.distanceCm;
        data.plantHeightCm = (height > 0.0) ? height : 0.0;
    } else {
        data.plantHeightCm = 0.0;
    }

    bool cycleFault = (!data.temperatureValid || !data.distanceValid);
    if (cycleFault) {
        consecutiveFaultCycles++;
    } else {
        consecutiveFaultCycles = 0;
    }

    data.status = (consecutiveFaultCycles == 0) ? "OK" : "DEGRADED";
    return data;
}

// 9. Time Synchronization (SNTP)
void syncNTPTime() {
    if (WiFi.status() != WL_CONNECTED) return;

    Serial.print("[*] Synchronizing system time via SNTP... ");
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
        Serial.println("Timeout (will retry next cycle).");
        sntpSynchronized = false;
    }
}

// 10. Telemetry Transmission
String buildJsonPayload(const SensorTelemetry &t) {
    StaticJsonDocument<384> doc;
    doc["device_id"] = DEVICE_ID;
    doc["moisture_raw"] = round(t.moistureRaw * 10.0) / 10.0;
    doc["moisture_percent"] = nullptr; // Backend calculates authoritative RSMI

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

void transmitTelemetry(const SensorTelemetry &t) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[!] Cannot transmit: No Wi-Fi connection active.");
        return;
    }

    String payload = buildJsonPayload(t);

    // Primary: Render Cloud HTTPS
    Serial.println("Cloud server: ATTEMPTING...");
    if (postToCloudHTTPS(payload)) {
        Serial.println("Cloud server: AVAILABLE");
        Serial.println("Data destination: RENDER CLOUD (Supabase PostgreSQL)");
        Serial.println("Cloud POST: 201 Created -> Data uploaded successfully");
        Serial.println("----------------------------------------\n");
        return;
    }

    // Fallback: Local Flask LAN HTTP
    Serial.println("Cloud server: UNAVAILABLE / TIMEOUT");
    Serial.println("Trying local Flask server fallback...");
    if (postToLocalHTTP(payload)) {
        Serial.println("Local server: AVAILABLE");
        Serial.println("Data destination: LOCAL FLASK (SQLite)");
        Serial.println("Local POST: 201 Created -> Data saved locally");
        Serial.println("----------------------------------------\n");
        return;
    }

    Serial.println("Local server: UNAVAILABLE");
    Serial.println("[!] Both Cloud and Local servers unreachable. Retrying next cycle.");
    Serial.println("----------------------------------------\n");
}

bool postToCloudHTTPS(const String &payload) {
    WiFiClientSecure secureClient;
    secureClient.setCACert(ROOT_CA_BUNDLE);
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
    https.end();
    return success;
}

bool postToLocalHTTP(const String &payload) {
    WiFiClient standardClient;
    standardClient.setTimeout(5);

    HTTPClient http;
    http.setTimeout(5000);

    if (!http.begin(standardClient, LOCAL_SERVER_URL)) {
        return false;
    }

    http.addHeader("Content-Type", "application/json");
    http.addHeader("User-Agent", "ESP32_PlantMonitor/2.0");

    int httpCode = http.POST(payload);
    bool success = (httpCode == 200 || httpCode == 201);
    http.end();
    return success;
}

// 11. Status LED Subsystem (Optional, Non-Blocking)
float calculateLocalMoisturePercent(float raw) {
    if (raw >= DRY_RAW_REF) return 0.0;
    if (raw <= WET_RAW_REF) return 100.0;
    float pct = ((DRY_RAW_REF - raw) / (DRY_RAW_REF - WET_RAW_REF)) * 100.0;
    if (pct < 0.0) return 0.0;
    if (pct > 100.0) return 100.0;
    return pct;
}

void updateLEDIndicators(const SensorTelemetry &t) {
    // 1. Persistent hardware sensor fault -> RED BLINK
    if (consecutiveFaultCycles >= FAULT_THRESHOLD) {
        currentLEDState = LED_STATE_RED_FAULT_BLINK;
        digitalWrite(PIN_LED_GREEN, LOW);
        return;
    }

    // 2. Favorable environment: Moisture >= 40% AND Temp < 30°C -> GREEN
    float moisturePct = calculateLocalMoisturePercent(t.moistureRaw);
    if (moisturePct >= 40.0 && t.temperatureC < 30.0 && t.temperatureValid && t.distanceValid) {
        currentLEDState = LED_STATE_GREEN_FAVORABLE;
        digitalWrite(PIN_LED_GREEN, HIGH);
        digitalWrite(PIN_LED_RED, LOW);
    } 
    // 3. Attention / Drying required -> RED
    else {
        currentLEDState = LED_STATE_RED_ATTENTION;
        digitalWrite(PIN_LED_GREEN, LOW);
        digitalWrite(PIN_LED_RED, HIGH);
    }
}

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

// 12. Serial Monitor Telemetry Display
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

    Serial.print("LED Status   : ");
    switch (currentLEDState) {
        case LED_STATE_GREEN_FAVORABLE:
            Serial.println("GREEN [Favorable: Moist & Moderate Temp]");
            break;
        case LED_STATE_RED_ATTENTION:
            Serial.println("RED [Attention: Low Moisture / Elevated Temp]");
            break;
        case LED_STATE_RED_FAULT_BLINK:
            Serial.printf("RED BLINKING [Sensor Warning: %d cycles missed]\n", consecutiveFaultCycles);
            break;
        case LED_STATE_SETUP_PORTAL:
            Serial.println("ALTERNATING GREEN/RED [Setup Portal Active]");
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

