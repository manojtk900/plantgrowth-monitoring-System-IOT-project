/**
 * IoT-Based Plant Growth & Environmental Monitoring System
 * Edge Node Firmware — ESP32 DevKit V1 (Device ID: ESP32_003)
 * 
 * Features:
 *   - Multi-Wi-Fi fallback (WiFiMulti with 3 credential slots)
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

// 2. Wi-Fi & Destination Endpoints
struct WiFiCredential {
    const char* ssid;
    const char* password;
};

// Slot 1 is default; slots 2 and 3 are optional fallbacks
const WiFiCredential WIFI_NETWORKS[3] = {
    {"manojtk", "manojtk900"}, // 1. DEFAULT — preferred
    {"", ""},                  // 2. Optional fallback
    {"", ""}                   // 3. Optional fallback
};

const char* CLOUD_SERVER_URL = "https://plantgrowth-monitoring-system-iot-project.onrender.com/api/sensor-data";
const char* LOCAL_SERVER_URL = "http://10.61.173.131:5000/api/sensor-data";
const int HTTP_TIMEOUT_MS = 15000;

// 3. TLS Root Certificates
// Bundle containing GTS Root R4 (Render *.onrender.com root) and ISRG Root X1 (Let's Encrypt)
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
"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\n" \
"-----END CERTIFICATE-----\n";

// 4. Drivers & State Variables
WiFiMulti wifiMulti;
OneWire oneWire(PIN_ONE_WIRE_BUS);
DallasTemperature tempSensors(&oneWire);

unsigned long lastTransmissionTime = 0;
bool sntpSynchronized = false;
int consecutiveFaultCycles = 0;
const int FAULT_THRESHOLD = 2; // Require 2 consecutive failed reading cycles before red fault blink

enum LEDIndicatorState {
    LED_STATE_STARTUP_OFF,     // Startup default: Both LEDs OFF until first valid reading
    LED_STATE_GREEN_FAVORABLE, // Green Steady: Moisture >= 40% AND Temp < 30°C AND sensors valid
    LED_STATE_RED_ATTENTION,   // Red Steady: Moisture < 40% OR (Moisture < 50% AND Temp >= 30°C)
    LED_STATE_RED_FAULT_BLINK  // Red Blink: Persistent hardware sensor fault
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
void connectToBestWiFi();
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

    // Initialize Optional Visual Indicator LEDs (Zero-dependency outputs)
    pinMode(PIN_LED_GREEN, OUTPUT);
    pinMode(PIN_LED_RED, OUTPUT);
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_RED, LOW);

    // Initialize DS18B20 Temperature Sensor
    tempSensors.begin();
    tempSensors.setResolution(11);

    // Register configured Wi-Fi networks (skipping empty slots cleanly)
    Serial.println("Configuring Wi-Fi Credentials:");
    for (int i = 0; i < 3; i++) {
        if (strlen(WIFI_NETWORKS[i].ssid) > 0) {
            wifiMulti.addAP(WIFI_NETWORKS[i].ssid, WIFI_NETWORKS[i].password);
            Serial.printf(" [%d] %s (registered)\n", i + 1, WIFI_NETWORKS[i].ssid);
        } else {
            Serial.printf(" [%d] (empty slot - skipped)\n", i + 1);
        }
    }

    connectToBestWiFi();
    syncNTPTime();
}

// 6. Main Loop
void loop() {
    unsigned long currentMillis = millis();

    // Maintain non-blocking LED blink service
    serviceLEDBlink();

    // Telemetry transmission cycle
    if (currentMillis - lastTransmissionTime >= TRANSMISSION_INTERVAL_MS || lastTransmissionTime == 0) {
        lastTransmissionTime = currentMillis;

        if (wifiMulti.run() != WL_CONNECTED) {
            Serial.println("[!] Wi-Fi disconnected. Reconnecting via WiFiMulti...");
            connectToBestWiFi();
        }

        if (!sntpSynchronized && WiFi.status() == WL_CONNECTED) {
            syncNTPTime();
        }

        SensorTelemetry telemetry = collectSensorData();
        updateLEDIndicators(telemetry);
        printTelemetryBanner(telemetry);
        transmitTelemetry(telemetry);
    }

    delay(20); // Responsive tick for smooth non-blocking blinking
}

// 7. Sensor Acquisition
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

// 8. Time Synchronization (SNTP)
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

// 9. Network & Telemetry Transmission
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
        Serial.printf("Connected: %s (IP: %s, RSSI: %d dBm)\n",
                      WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
    } else {
        Serial.println("[!] No configured Wi-Fi network found within range.");
    }
}

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

// 10. Status LED Subsystem (Optional, Non-Blocking)
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

// 11. Serial Monitor Telemetry Display
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
        case LED_STATE_STARTUP_OFF:
        default:
            Serial.println("OFF [Initializing]");
            break;
    }
}
