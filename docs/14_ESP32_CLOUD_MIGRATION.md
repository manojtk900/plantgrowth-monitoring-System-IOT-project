# ESP32 Edge Device Cloud Migration Specification (HTTPS & TLS)

**Document ID:** `DOC-014`  
**Phase:** 7B — Cloud Deployment Preparation  
**Hardware Node:** ESP32 DevKit V1 (`ESP32_003`)  
**Status:** Staged Specification (DO NOT FLASH FIRMWARE YET)  

---

## 1. Safety Mandate

> [!CRITICAL]
> **DO NOT FLASH FIRMWARE NOW.**
> This document specifies the future edge modifications required ONLY AFTER:
> 1. Supabase PostgreSQL is provisioned and hydrated with all 89 records.
> 2. Render Flask Web Service is deployed, healthy, and verified via browser.
> 
> Until cloud infrastructure is 100% verified, `ESP32_003` must continue operating with its verified local configuration.

---

## 2. Hardware & Pinout Baseline (Preserved)

No physical hardware changes are required. Pin assignments remain identical:
- **Capacitive Soil Moisture Sensor (v1.2):** Analog Out ➔ `GPIO 34` (ADC1_CH6, Input Only)
- **DS18B20 Waterproof Temperature Sensor:** OneWire Data ➔ `GPIO 4` (with 4.7kΩ pull-up resistor to 3.3V)
- **HC-SR04 Ultrasonic Sensor:**
  - Trigger ➔ `GPIO 5`
  - Echo ➔ `GPIO 18` (via 1kΩ / 2kΩ resistive voltage divider stepping 5V ➔ 3.3V)

---

## 3. Cloud Communication Architecture

### Transition:
- **Current Local Mode:** `ESP32_003` ➔ HTTP ➔ `http://192.168.1.100:5000/api/sensor-data`
- **Future Cloud Mode:** `ESP32_003` ➔ HTTPS (TLS 1.3) ➔ `https://<render-service-name>.onrender.com/api/sensor-data`

---

## 4. Cryptographic TLS Security Strategy

### Why `client.setInsecure()` is Prohibited:
Using `client.setInsecure()` disables certificate validation entirely. In an Internet deployment, this leaves the edge node vulnerable to Man-in-the-Middle (MitM) attacks, spoofed endpoints, and DNS hijacking.

### Production TLS Architecture:
1. **Network Security:** Use `WiFiClientSecure` rather than unencrypted `WiFiClient`.
2. **Certificate Authority (CA):** Render hosts domains using certificates issued by **Let's Encrypt**. The root certificate is the **ISRG Root X1** root CA (valid through 2035).
3. **SNTP Real-Time Clock Synchronization:**
   - X.509 certificate validation requires the ESP32 to know the current real-world time to verify the certificate's `notBefore` and `notAfter` validity periods.
   - Synchronize time upon Wi-Fi connection using SNTP:
     ```cpp
     configTime(0, 0, "pool.ntp.org", "time.nist.gov");
     ```
4. **Root CA Attachment:** Attach the ISRG Root X1 certificate in PEM format to `WiFiClientSecure`:
   ```cpp
   client.setCACert(ISRG_ROOT_X1_CA);
   ```

---

## 5. ISRG Root X1 Certificate (PEM Format)

Embed this root certificate into the future firmware configuration:

```cpp
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
```

---

## 6. Edge/Cloud API Payload Contract

The cloud endpoint preserves the exact JSON schema currently verified locally:

### Request Contract:
- **HTTP Method:** `POST`
- **URL:** `https://<render-url>.onrender.com/api/sensor-data`
- **Headers:** `Content-Type: application/json`
- **Body Schema:**
  ```json
  {
    "device_id": "ESP32_003",
    "moisture_raw": 2840.0,
    "moisture_percent": null,
    "temperature_c": 24.6,
    "distance_cm": 12.3,
    "plant_height_cm": 17.7,
    "status": "OK"
  }
  ```

### Critical Rules:
1. `moisture_raw` **Must Be Provided:** Backend maintains calibration responsibility (`DRY_RAW = 3326.0`, `WET_RAW = 1520.0`).
2. `moisture_percent` **Left Null or Omitted:** The Flask backend calculates the relative index to guarantee calibration consistency.
3. **Response Verification:** The ESP32 must check for `HTTP 201 Created` with `{"success": true}` in the response body.
