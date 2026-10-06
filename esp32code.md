#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ====================================================
// WIFI SETTINGS
// ====================================================

const char* WIFI_SSID = "manojtk";
const char* WIFI_PASSWORD = "manojtk900";

// IMPORTANT:
// Replace XXX with your laptop's actual IPv4 last number.
const char* SERVER_URL =
    "http://10.61.173.131:5000/api/sensor-data";


// ====================================================
// DEVICE
// ====================================================

const char* DEVICE_ID = "ESP32_003";


// ====================================================
// PIN DEFINITIONS
// ====================================================

#define MOISTURE_PIN 34
#define DS18B20_PIN 4

#define TRIG_PIN 5
#define ECHO_PIN 18


// ====================================================
// DS18B20
// ====================================================

OneWire oneWire(DS18B20_PIN);

DallasTemperature temperatureSensor(&oneWire);


// ====================================================
// PLANT HEIGHT
// ====================================================

// Distance from HC-SR04 to soil/reference point.
// Change this after physical mounting if required.

const float SENSOR_TO_SOIL_CM = 30.0;


// ====================================================
// CONNECT TO WIFI
// ====================================================

void connectWiFi()
{
  Serial.println();
  Serial.println("Connecting to Wi-Fi...");

  WiFi.mode(WIFI_STA);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED && attempts < 40)
  {
    delay(500);

    Serial.print(".");

    attempts++;
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("Wi-Fi connected!");

    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());

    Serial.print("Server URL: ");
    Serial.println(SERVER_URL);
  }
  else
  {
    Serial.println("Wi-Fi connection failed.");
  }
}


// ====================================================
// READ SOIL MOISTURE
// ====================================================

int readMoisture()
{
  int rawValue = analogRead(MOISTURE_PIN);

  return rawValue;
}


// ====================================================
// READ TEMPERATURE
// ====================================================

float readTemperature()
{
  temperatureSensor.requestTemperatures();

  float temperature =
      temperatureSensor.getTempCByIndex(0);

  return temperature;
}


// ====================================================
// READ HC-SR04 DISTANCE
// ====================================================

float readDistance()
{
  digitalWrite(TRIG_PIN, LOW);

  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);

  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);

  long duration =
      pulseIn(ECHO_PIN, HIGH, 30000);

  if (duration == 0)
  {
    return -1;
  }

  float distance =
      duration * 0.0343 / 2.0;

  return distance;
}


// ====================================================
// CALCULATE PLANT HEIGHT
// ====================================================

float calculatePlantHeight(float distance)
{
  if (distance < 0)
  {
    return -1;
  }

  float height =
      SENSOR_TO_SOIL_CM - distance;

  if (height < 0)
  {
    height = 0;
  }

  return height;
}


// ====================================================
// SEND DATA TO FLASK SERVER
// ====================================================

void sendDataToServer(
    int moistureRaw,
    float temperature,
    float distance,
    float plantHeight)
{
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("Wi-Fi disconnected. Reconnecting...");

    connectWiFi();

    if (WiFi.status() != WL_CONNECTED)
    {
      Serial.println("Unable to reconnect.");
      return;
    }
  }


  // --------------------------------------------
  // Prepare values for JSON
  // --------------------------------------------

  String temperatureJSON;

  if (temperature == DEVICE_DISCONNECTED_C)
  {
    temperatureJSON = "null";
  }
  else
  {
    temperatureJSON = String(temperature, 2);
  }


  String distanceJSON;

  if (distance < 0)
  {
    distanceJSON = "null";
  }
  else
  {
    distanceJSON = String(distance, 2);
  }


  String heightJSON;

  if (plantHeight < 0)
  {
    heightJSON = "null";
  }
  else
  {
    heightJSON = String(plantHeight, 2);
  }


  // --------------------------------------------
  // Determine sensor status
  // --------------------------------------------

  String status = "OK";

  if (temperature == DEVICE_DISCONNECTED_C ||
      distance < 0)
  {
    status = "SENSOR_ERROR";
  }


  // --------------------------------------------
  // Create JSON
  // --------------------------------------------

  String json = "{";

  json += "\"device_id\":\"";
  json += DEVICE_ID;
  json += "\",";

  json += "\"moisture_raw\":";
  json += String(moistureRaw);
  json += ",";

  // Moisture percentage is NOT sent yet.
  // Calibration will be done later.
  json += "\"moisture_percent\":null,";

  json += "\"temperature_c\":";
  json += temperatureJSON;
  json += ",";

  json += "\"distance_cm\":";
  json += distanceJSON;
  json += ",";

  json += "\"plant_height_cm\":";
  json += heightJSON;
  json += ",";

  json += "\"status\":\"";
  json += status;
  json += "\"";

  json += "}";


  // --------------------------------------------
  // Display JSON
  // --------------------------------------------

  Serial.println();
  Serial.println("Sending data to Flask...");
  Serial.println(json);


  // --------------------------------------------
  // HTTP POST
  // --------------------------------------------

  HTTPClient http;

  http.setTimeout(5000);

  http.begin(SERVER_URL);

  http.addHeader(
      "Content-Type",
      "application/json"
  );


  int httpResponseCode =
      http.POST(json);


  Serial.print("HTTP Response Code: ");
  Serial.println(httpResponseCode);


  if (httpResponseCode > 0)
  {
    String response =
        http.getString();

    Serial.println("Server Response:");
    Serial.println(response);
  }
  else
  {
    Serial.println("HTTP request failed.");

    Serial.print("Error: ");
    Serial.println(
        http.errorToString(httpResponseCode)
    );
  }


  http.end();
}


// ====================================================
// SETUP
// ====================================================

void setup()
{
  Serial.begin(115200);

  delay(1000);


  Serial.println();
  Serial.println("======================================");
  Serial.println(" IoT Plant Growth Monitoring System");
  Serial.println("======================================");


  // --------------------------------------------
  // Start DS18B20
  // --------------------------------------------

  temperatureSensor.begin();


  // --------------------------------------------
  // Start HC-SR04
  // --------------------------------------------

  pinMode(TRIG_PIN, OUTPUT);

  pinMode(ECHO_PIN, INPUT);

  digitalWrite(TRIG_PIN, LOW);


  // --------------------------------------------
  // Connect Wi-Fi
  // --------------------------------------------

  connectWiFi();


  Serial.println();
  Serial.println("System initialized.");
  Serial.println();
}


// ====================================================
// MAIN LOOP
// ====================================================

void loop()
{
  // --------------------------------------------
  // SOIL MOISTURE
  // --------------------------------------------

  int moistureRaw =
      readMoisture();


  // --------------------------------------------
  // TEMPERATURE
  // --------------------------------------------

  float temperature =
      readTemperature();


  // --------------------------------------------
  // HC-SR04 DISTANCE
  // --------------------------------------------

  float distance =
      readDistance();


  // --------------------------------------------
  // PLANT HEIGHT
  // --------------------------------------------

  float plantHeight =
      calculatePlantHeight(distance);


  // --------------------------------------------
  // SERIAL MONITOR
  // --------------------------------------------

  Serial.println("--------------------------------------");

  Serial.print("Soil Moisture Raw : ");
  Serial.println(moistureRaw);


  Serial.print("Soil Temperature  : ");

  if (temperature == DEVICE_DISCONNECTED_C)
  {
    Serial.println("Sensor disconnected");
  }
  else
  {
    Serial.print(temperature);
    Serial.println(" °C");
  }


  Serial.print("HC-SR04 Distance  : ");

  if (distance < 0)
  {
    Serial.println("No measurement");
  }
  else
  {
    Serial.print(distance);
    Serial.println(" cm");
  }


  Serial.print("Plant Height      : ");

  if (plantHeight < 0)
  {
    Serial.println("No measurement");
  }
  else
  {
    Serial.print(plantHeight);
    Serial.println(" cm");
  }


  Serial.println("--------------------------------------");


  // --------------------------------------------
  // SEND TO FLASK
  // --------------------------------------------

  sendDataToServer(
      moistureRaw,
      temperature,
      distance,
      plantHeight
  );


  // --------------------------------------------
  // WAIT 10 SECONDS
  // --------------------------------------------

  delay(10000);
}










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

