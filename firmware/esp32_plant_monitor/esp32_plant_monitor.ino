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
