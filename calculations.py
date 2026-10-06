"""
calculations.py
================
Centralized calibration, validation, classification, drying-risk,
and condition-scoring engine for the IoT Plant Growth Monitor.
Supports dynamic runtime calibration configuration and trend analytics.
"""

from datetime import datetime, timezone
import math

# =====================================================================
# CALIBRATION CONSTANTS & CONFIGURATION (DEFAULTS)
# =====================================================================

# Empirically measured calibration points for Capacitive Soil Moisture Sensor v1.2
DRY_RAW = 3326.0   # Sensor reading in dry soil / air
WET_RAW = 1520.0   # Sensor reading submerged in water / saturated soil

# Overhead ultrasonic sensor mounting reference height (cm)
SENSOR_MOUNT_HEIGHT_CM = 30.0

# Temperature / Drying Risk Configurable Thresholds
DRYING_RISK_TEMP_THRESHOLD = 30.0   # °C (Hot condition accelerating drying)
LOW_MOISTURE_THRESHOLD = 25.0       # % (Dry boundary)

# Device liveness timeout thresholds (seconds)
HEARTBEAT_TIMEOUTS = {
    "online": 30,      # < 30s: Active real-time transmission
    "recent": 90,      # 30-90s: Missed 1-2 transmissions, still warm
    "stale": 300,      # 90-300s: Delayed / potential intermittent connection
    "offline": 300     # > 300s: Device disconnected / unpowered
}

# Configurable Relative Soil Moisture Index (RSMI) classification bands
MOISTURE_CLASSIFICATIONS = [
    {"min": 0,  "max": 10,  "label": "Very Dry",                 "color": "#ef4444", "status_key": "danger"},
    {"min": 10, "max": 25,  "label": "Dry",                      "color": "#f97316", "status_key": "warning"},
    {"min": 25, "max": 40,  "label": "Low",                      "color": "#eab308", "status_key": "warning"},
    {"min": 40, "max": 60,  "label": "Moderate",                 "color": "#84cc16", "status_key": "good"},
    {"min": 60, "max": 75,  "label": "Good",                     "color": "#10b981", "status_key": "good"},
    {"min": 75, "max": 90,  "label": "Moist",                    "color": "#06b6d4", "status_key": "good"},
    {"min": 90, "max": 100, "label": "Very Moist / Wet Reference", "color": "#3b82f6", "status_key": "info"}
]

# Temperature ranges for soil / root zone (°C)
TEMP_RANGES = {
    "cold_stress": 10.0,
    "cool_suboptimal": 18.0,
    "optimal_min": 20.0,
    "optimal_max": 28.0,
    "warm_suboptimal": 32.0,
    "heat_stress": 36.0
}


def get_calibration():
    """Returns current active calibration and threshold constants."""
    return {
        "dry_raw": DRY_RAW,
        "wet_raw": WET_RAW,
        "sensor_mount_height_cm": SENSOR_MOUNT_HEIGHT_CM,
        "drying_risk_temp_threshold": DRYING_RISK_TEMP_THRESHOLD,
        "low_moisture_threshold": LOW_MOISTURE_THRESHOLD
    }


def set_calibration(dry_raw=None, wet_raw=None, sensor_mount_height_cm=None,
                    mount_height_cm=None, drying_risk_temp_threshold=None, low_moisture_threshold=None):
    """
    Safely updates active runtime calibration parameters in memory.
    """
    global DRY_RAW, WET_RAW, SENSOR_MOUNT_HEIGHT_CM
    global DRYING_RISK_TEMP_THRESHOLD, LOW_MOISTURE_THRESHOLD

    if dry_raw is not None:
        DRY_RAW = float(dry_raw)
    if wet_raw is not None:
        WET_RAW = float(wet_raw)
    
    height_val = sensor_mount_height_cm if sensor_mount_height_cm is not None else mount_height_cm
    if height_val is not None:
        SENSOR_MOUNT_HEIGHT_CM = float(height_val)

    if drying_risk_temp_threshold is not None:
        DRYING_RISK_TEMP_THRESHOLD = float(drying_risk_temp_threshold)
    if low_moisture_threshold is not None:
        LOW_MOISTURE_THRESHOLD = float(low_moisture_threshold)


def validate_calibration_settings(dry_raw, wet_raw, mount_height_cm=30.0,
                                  drying_risk_temp_threshold=30.0, low_moisture_threshold=25.0):
    """
    Validates calibration input settings.
    Rules:
      1. Both raw values must be between 0 and 4095 (12-bit ADC).
      2. DRY_RAW must be strictly greater than WET_RAW (for this sensor orientation).
      3. Minimum difference of 100 between DRY_RAW and WET_RAW to prevent unstable scaling.
      4. Mount height must be between 5.0 and 300.0 cm.
      5. Temperature threshold must be between 15.0 and 50.0 °C.
      6. Low moisture threshold must be between 5.0 and 50.0 %.
    Returns (is_valid: bool, error_message: str, sanitized_values: dict).
    """
    try:
        dry = float(dry_raw)
        wet = float(wet_raw)
    except (ValueError, TypeError):
        return False, "Calibration raw values must be valid numbers.", None

    if not (0.0 <= dry <= 4095.0) or not (0.0 <= wet <= 4095.0):
        return False, "Raw ADC reference points must be within the 12-bit range 0 to 4095.", None

    if dry <= wet:
        return False, "Dry reference ADC must be strictly greater than Wet reference ADC for capacitive sensors.", None

    if (dry - wet) < 100.0:
        return False, f"Span between Dry ({dry}) and Wet ({wet}) is too narrow (minimum difference 100 required).", None

    try:
        height = float(mount_height_cm)
    except (ValueError, TypeError):
        return False, "Sensor mount height must be a valid number.", None

    if not (5.0 <= height <= 300.0):
        return False, "Sensor mount height must be between 5.0 cm and 300.0 cm.", None

    try:
        temp_thresh = float(drying_risk_temp_threshold)
        moist_thresh = float(low_moisture_threshold)
    except (ValueError, TypeError):
        return False, "Threshold values must be numbers.", None

    if not (15.0 <= temp_thresh <= 50.0):
        return False, "Drying risk temperature threshold must be between 15°C and 50°C.", None

    if not (5.0 <= moist_thresh <= 50.0):
        return False, "Low moisture threshold must be between 5% and 50%.", None

    sanitized = {
        "dry_raw": round(dry, 1),
        "wet_raw": round(wet, 1),
        "sensor_mount_height_cm": round(height, 2),
        "drying_risk_temp_threshold": round(temp_thresh, 1),
        "low_moisture_threshold": round(moist_thresh, 1)
    }
    return True, "", sanitized


# =====================================================================
# SENSOR VALIDATION
# =====================================================================

def validate_moisture_raw(val):
    """
    Validate 12-bit ADC raw soil moisture value.
    Valid range: 0 to 4095.
    Returns float or None if invalid.
    """
    if val is None:
        return None
    try:
        val = float(val)
    except (ValueError, TypeError):
        return None

    if math.isnan(val) or math.isinf(val):
        return None

    if 0.0 <= val <= 4095.0:
        return round(val, 1)
    return None


def validate_temperature_c(val):
    """
    Validate DS18B20 1-Wire temperature reading in Celsius.
    Filters out hardware error codes:
      -127.0: Disconnected sensor (no response on 1-Wire bus)
       85.0: Power-on reset state without conversion
    Accepts reasonable agronomic range: -10°C to 65°C.
    Returns float or None if invalid.
    """
    if val is None:
        return None
    try:
        val = float(val)
    except (ValueError, TypeError):
        return None

    if math.isnan(val) or math.isinf(val):
        return None

    # DS18B20 disconnect flag
    if abs(val - (-127.0)) < 0.1:
        return None

    # DS18B20 power-on unconverted reset register
    if abs(val - 85.0) < 0.05:
        return None

    if -10.0 <= val <= 65.0:
        return round(val, 2)
    return None


def validate_distance_cm(val):
    """
    Validate HC-SR04 ultrasonic distance reading in centimeters.
    Valid physical range: 2.0 cm to 400.0 cm.
    Must never be negative.
    Returns float or None if invalid.
    """
    if val is None:
        return None
    try:
        val = float(val)
    except (ValueError, TypeError):
        return None

    if math.isnan(val) or math.isinf(val):
        return None

    if 0.0 <= val <= 400.0:
        return round(val, 2)
    return None


def validate_plant_height_cm(val, distance_cm=None):
    """
    Validate calculated plant height.
    Must never be negative.
    If plant_height_cm is None but valid distance_cm is provided,
    calculates plant height using SENSOR_MOUNT_HEIGHT_CM - distance_cm.
    """
    if val is not None:
        try:
            val = float(val)
            if not math.isnan(val) and not math.isinf(val):
                return max(0.0, round(val, 2))
        except (ValueError, TypeError):
            pass

    if distance_cm is not None:
        valid_dist = validate_distance_cm(distance_cm)
        if valid_dist is not None:
            height = SENSOR_MOUNT_HEIGHT_CM - valid_dist
            return max(0.0, round(height, 2))

    return None


# =====================================================================
# MOISTURE ENGINE: RSMI & CLASSIFICATION
# =====================================================================

def calculate_moisture_percent(moisture_raw):
    """
    Calculate the Relative Soil Moisture Index (RSMI, %).
    Formula:
        ((DRY_RAW - raw) / (DRY_RAW - WET_RAW)) * 100
    Higher raw ADC = drier soil.
    Lower raw ADC = wetter soil.
    Clamped strictly between 0.0 and 100.0.
    Returns float rounded to 2 decimal places, or None.
    """
    valid_raw = validate_moisture_raw(moisture_raw)
    if valid_raw is None:
        return None

    span = DRY_RAW - WET_RAW
    if span <= 0:
        span = 1.0  # Safety fallback to prevent zero division

    moisture_percent = ((DRY_RAW - valid_raw) / span) * 100.0
    moisture_percent = max(0.0, min(100.0, moisture_percent))
    return round(moisture_percent, 2)


def classify_moisture(moisture_percent):
    """
    Classify relative moisture percentage into human-readable tier.
    Returns dict with label, color, and status_key.
    """
    if moisture_percent is None:
        return {
            "label": "Sensor Offline",
            "color": "#9ca3af",
            "status_key": "unknown"
        }

    for tier in MOISTURE_CLASSIFICATIONS:
        if tier["min"] <= moisture_percent <= tier["max"]:
            return {
                "label": tier["label"],
                "color": tier["color"],
                "status_key": tier["status_key"]
            }

    # Fallback bounds
    if moisture_percent > 100.0:
        return {
            "label": "Saturated Reference",
            "color": "#3b82f6",
            "status_key": "info"
        }

    return {
        "label": "Very Dry",
        "color": "#ef4444",
        "status_key": "danger"
    }


# =====================================================================
# TEMPERATURE-AWARE DRYING RISK ENGINE
# =====================================================================

def calculate_drying_risk(moisture_percent, temperature_c):
    """
    Transparent rule-based decision engine cross-correlating
    moisture percentage and soil temperature.
    Does NOT modify the moisture percentage itself.
    """
    if moisture_percent is None:
        return {
            "risk_level": "Unknown",
            "color": "#9ca3af",
            "badge_class": "unknown",
            "explanation": "Soil moisture data is currently unavailable.",
            "recommendation": "Inspect capacitive moisture probe connection."
        }

    temp_available = (temperature_c is not None)
    temp = temperature_c if temp_available else 25.0

    # Case 1: Very Dry or Dry soil (<= LOW_MOISTURE_THRESHOLD)
    if moisture_percent <= LOW_MOISTURE_THRESHOLD:
        if temp > DRYING_RISK_TEMP_THRESHOLD:
            return {
                "risk_level": "High",
                "color": "#ef4444",
                "badge_class": "danger",
                "explanation": f"Low soil moisture ({moisture_percent:.1f}%) combined with high temperature ({temp:.1f}°C) causes rapid evaporative drying and plant wilting risk.",
                "recommendation": "High drying risk. Inspect soil immediately and consider scheduled irrigation."
            }
        elif temp >= 20.0:
            return {
                "risk_level": "Moderate-High",
                "color": "#f97316",
                "badge_class": "warning",
                "explanation": f"Low soil moisture ({moisture_percent:.1f}%) under warm ambient conditions ({temp:.1f}°C).",
                "recommendation": "Soil moisture is getting low. Irrigation recommended soon."
            }
        else:
            return {
                "risk_level": "Moderate",
                "color": "#eab308",
                "badge_class": "warning",
                "explanation": f"Soil moisture is dry ({moisture_percent:.1f}%), but cool temperature ({temp:.1f}°C) moderates evaporation rate.",
                "recommendation": "Soil is dry. Plan irrigation before temperatures rise."
            }

    # Case 2: Low moisture (between LOW_MOISTURE_THRESHOLD and 40%)
    elif moisture_percent <= 40.0:
        if temp > DRYING_RISK_TEMP_THRESHOLD:
            return {
                "risk_level": "Moderate-High",
                "color": "#f97316",
                "badge_class": "warning",
                "explanation": f"Sub-optimal moisture ({moisture_percent:.1f}%) with warm temperature ({temp:.1f}°C) accelerating evapotranspiration.",
                "recommendation": "Warm weather accelerating drying. Monitor closely."
            }
        else:
            return {
                "risk_level": "Moderate",
                "color": "#eab308",
                "badge_class": "warning",
                "explanation": f"Moisture is in lower operational zone ({moisture_percent:.1f}%).",
                "recommendation": "Monitor moisture trends. No emergency watering required."
            }

    # Case 3: Moderate / Good moisture (40 - 75%)
    elif moisture_percent <= 75.0:
        if temp > 32.0:
            return {
                "risk_level": "Moderate",
                "color": "#eab308",
                "badge_class": "warning",
                "explanation": f"Moisture is adequate ({moisture_percent:.1f}%), but high temperature ({temp:.1f}°C) increases canopy transpiration.",
                "recommendation": "Good soil moisture. Monitor midday heat impact."
            }
        else:
            return {
                "risk_level": "Low",
                "color": "#10b981",
                "badge_class": "good",
                "explanation": f"Favorable root-zone hydration ({moisture_percent:.1f}%) and stable temperature ({temp:.1f}°C).",
                "recommendation": "Optimal condition. No irrigation required at this time."
            }

    # Case 4: Moist / Saturated (75 - 100%)
    else:
        return {
            "risk_level": "Low",
            "color": "#06b6d4",
            "badge_class": "good",
            "explanation": f"Soil moisture is abundant ({moisture_percent:.1f}% relative index).",
            "recommendation": "Avoid unnecessary watering to maintain soil oxygenation."
        }


# =====================================================================
# EXPLAINABLE PLANT CONDITION SCORE ENGINE
# =====================================================================

def calculate_plant_condition_score(moisture_percent, temperature_c, drying_risk_level="Low", sensor_status="OK"):
    """
    Calculates an explainable Environmental Plant Condition Score (0 to 100).
    Explicitly labeled as an environmental condition metric, NOT a clinical plant disease diagnosis.
    """
    score = 100
    reasons = []
    breakdown = {}

    # 1. Soil Moisture Assessment (Max deduction: 45)
    if moisture_percent is None:
        score -= 25
        reasons.append("Moisture sensor unavailable (-25)")
        breakdown["moisture"] = "Unavailable"
    elif 60.0 <= moisture_percent <= 75.0:
        reasons.append("Soil moisture is in the optimal growth band (60-75%)")
        breakdown["moisture"] = "Optimal"
    elif 40.0 <= moisture_percent < 60.0:
        score -= 5
        reasons.append("Soil moisture is moderate (40-60%) (-5)")
        breakdown["moisture"] = "Moderate"
    elif 75.0 < moisture_percent <= 90.0:
        score -= 5
        reasons.append("Soil moisture is elevated (75-90%) (-5)")
        breakdown["moisture"] = "Elevated"
    elif 25.0 <= moisture_percent < 40.0:
        score -= 15
        reasons.append("Soil moisture is low (25-40%) (-15)")
        breakdown["moisture"] = "Low"
    elif 10.0 <= moisture_percent < 25.0:
        score -= 30
        reasons.append("Soil moisture is dry (10-25%) (-30)")
        breakdown["moisture"] = "Dry"
    elif moisture_percent < 10.0:
        score -= 45
        reasons.append("Soil moisture is critically dry (<10%) (-45)")
        breakdown["moisture"] = "Very Dry"
    else:  # > 90%
        score -= 10
        reasons.append("Soil is near saturated reference (>90%), watch aeration (-10)")
        breakdown["moisture"] = "Near Saturated"

    # 2. Temperature Assessment (Max deduction: 25)
    if temperature_c is None:
        score -= 15
        reasons.append("Temperature sensor unavailable (-15)")
        breakdown["temperature"] = "Unavailable"
    elif 20.0 <= temperature_c <= 28.0:
        reasons.append(f"Soil temperature ({temperature_c:.1f}°C) is ideal for root uptake")
        breakdown["temperature"] = "Ideal"
    elif (18.0 <= temperature_c < 20.0) or (28.0 < temperature_c <= 32.0):
        score -= 5
        reasons.append(f"Temperature ({temperature_c:.1f}°C) is slightly outside optimal band (-5)")
        breakdown["temperature"] = "Suboptimal"
    elif (10.0 <= temperature_c < 18.0) or (32.0 < temperature_c <= 36.0):
        score -= 15
        reasons.append(f"Temperature ({temperature_c:.1f}°C) represents thermal stress (-15)")
        breakdown["temperature"] = "Thermal Stress"
    else:  # < 10 or > 36
        score -= 25
        reasons.append(f"Severe temperature stress ({temperature_c:.1f}°C) (-25)")
        breakdown["temperature"] = "Severe Stress"

    # 3. Drying Risk Assessment (Max deduction: 15)
    if drying_risk_level == "High":
        score -= 15
        reasons.append("Elevated heat and moisture deficit create High drying risk (-15)")
        breakdown["drying_risk"] = "High Risk"
    elif drying_risk_level == "Moderate-High":
        score -= 10
        reasons.append("Warm conditions accelerating soil moisture depletion (-10)")
        breakdown["drying_risk"] = "Moderate-High Risk"
    elif drying_risk_level == "Moderate":
        score -= 5
        reasons.append("Moderate drying risk requires routine monitoring (-5)")
        breakdown["drying_risk"] = "Moderate Risk"
    else:
        breakdown["drying_risk"] = "Low Risk"

    # 4. Sensor Availability
    if sensor_status != "OK":
        score -= 10
        reasons.append(f"Sensor status reporting warning: {sensor_status} (-10)")
        breakdown["sensor_health"] = sensor_status
    else:
        breakdown["sensor_health"] = "Active"

    score = max(0, min(100, score))

    if score >= 85:
        status_label = "Optimal"
        badge_color = "#10b981"
    elif score >= 65:
        status_label = "Good"
        badge_color = "#84cc16"
    elif score >= 45:
        status_label = "Attention"
        badge_color = "#f59e0b"
    else:
        status_label = "Critical"
        badge_color = "#ef4444"

    return {
        "score": score,
        "status": status_label,
        "badge_color": badge_color,
        "reasons": reasons,
        "breakdown": breakdown
    }


# =====================================================================
# TIMESTAMP PARSING & NORMALIZATION
# =====================================================================

def parse_iso_timestamp(ts_input):
    """
    Safely parses an ISO timestamp string or datetime object into a UTC-aware datetime.
    Supports:
      - Naive SQLite timestamps: '2026-10-05T17:32:46' or '2026-10-05 17:32:46'
      - Aware PostgreSQL timestamps: '2026-10-05T17:32:46+00:00'
      - UTC Z timestamps: '2026-10-05T17:32:46Z'
      - Existing datetime objects (both naive and aware)
    Returns:
      UTC-aware datetime or None if invalid.
    """
    if ts_input is None:
        return None
    if isinstance(ts_input, datetime):
        if ts_input.tzinfo is None:
            return ts_input.replace(tzinfo=timezone.utc)
        return ts_input.astimezone(timezone.utc)

    s = str(ts_input).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = s.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


# =====================================================================
# DEVICE LIVENESS EVALUATION
# =====================================================================

def evaluate_device_liveness(created_at_str, current_time=None):
    """
    Evaluates hardware liveness by comparing the timestamp of the latest
    ESP32 reading against the server clock.
    Normalizes all timestamps to UTC-aware datetimes to prevent offset-naive
    vs offset-aware subtraction errors across SQLite and PostgreSQL.
    """
    if not created_at_str:
        return {
            "online": False,
            "state": "OFFLINE",
            "seconds_since_last_seen": None,
            "badge_class": "danger",
            "label": "● OFFLINE"
        }

    reading_dt = parse_iso_timestamp(created_at_str)
    if not reading_dt:
        return {
            "online": False,
            "state": "OFFLINE",
            "seconds_since_last_seen": None,
            "badge_class": "danger",
            "label": "● OFFLINE"
        }

    if current_time:
        now = parse_iso_timestamp(current_time)
        if not now:
            now = datetime.now(timezone.utc)
    else:
        now = datetime.now(timezone.utc)

    diff_seconds = max(0, int((now - reading_dt).total_seconds()))

    if diff_seconds < HEARTBEAT_TIMEOUTS["online"]:
        return {
            "online": True,
            "state": "ONLINE",
            "seconds_since_last_seen": diff_seconds,
            "badge_class": "good",
            "label": "● ONLINE"
        }
    elif diff_seconds < HEARTBEAT_TIMEOUTS["recent"]:
        return {
            "online": True,
            "state": "RECENT",
            "seconds_since_last_seen": diff_seconds,
            "badge_class": "warning",
            "label": "● RECENT"
        }
    elif diff_seconds <= HEARTBEAT_TIMEOUTS["stale"]:
        return {
            "online": False,
            "state": "STALE",
            "seconds_since_last_seen": diff_seconds,
            "badge_class": "warning",
            "label": "● STALE"
        }
    else:
        return {
            "online": False,
            "state": "OFFLINE",
            "seconds_since_last_seen": diff_seconds,
            "badge_class": "danger",
            "label": "● OFFLINE"
        }


# =====================================================================
# TRENDS & RATES CALCULATION ENGINE
# =====================================================================

def calculate_trends_and_rates(readings):
    """
    Computes verifiable trends and rates from chronological readings.
    Input: list of dicts with 'created_at', 'moisture_percent',
           'temperature_c', 'plant_height_cm' ordered oldest -> newest.
    Guarantees:
      - Only calculates rates when sufficient valid timestamped data exists.
      - Never fabricates trends or rates.
    """
    if not readings or len(readings) < 2:
        return {
            "moisture_trend": "No valid trend",
            "temperature_trend": "No valid trend",
            "plant_growth_trend": "No valid trend",
            "moisture_rate_pct_per_hour": None,
            "moisture_rate_label": "Insufficient data",
            "plant_growth_rate_cm_per_day": None,
            "growth_rate_label": "Insufficient data",
            "time_span_seconds": 0,
            "time_span_hours": 0.0
        }

    first = readings[0]
    last = readings[-1]

    try:
        t_start = parse_iso_timestamp(first.get("created_at"))
        t_end = parse_iso_timestamp(last.get("created_at"))
        if t_start and t_end:
            time_span_seconds = max(0, int((t_end - t_start).total_seconds()))
        else:
            time_span_seconds = 0
    except Exception:
        time_span_seconds = 0

    time_span_hours = time_span_seconds / 3600.0
    time_span_days = time_span_seconds / 86400.0

    # 1. MOISTURE TREND & RATE
    # Compare first valid moisture to last valid moisture
    first_moist = first.get("moisture_percent")
    last_moist = last.get("moisture_percent")

    if first_moist is not None and last_moist is not None:
        delta_m = last_moist - first_moist
        if delta_m > 2.0:
            moisture_trend = "Increasing"
        elif delta_m < -2.0:
            moisture_trend = "Falling"
        else:
            moisture_trend = "Stable"

        # Rate requirement: At least 15 minutes (900 seconds) between samples
        if time_span_seconds >= 900 and time_span_hours > 0:
            rate_m = round(delta_m / time_span_hours, 2)
            moisture_rate_pct_per_hour = rate_m
            moisture_rate_label = f"{rate_m:+.1f} % / hour"
        else:
            moisture_rate_pct_per_hour = None
            moisture_rate_label = "Insufficient data (< 15 mins)"
    else:
        moisture_trend = "No valid trend"
        moisture_rate_pct_per_hour = None
        moisture_rate_label = "Insufficient data"

    # 2. TEMPERATURE TREND
    first_temp = first.get("temperature_c")
    last_temp = last.get("temperature_c")

    if first_temp is not None and last_temp is not None:
        delta_t = last_temp - first_temp
        if delta_t > 0.75:
            temperature_trend = "Increasing"
        elif delta_t < -0.75:
            temperature_trend = "Falling"
        else:
            temperature_trend = "Stable"
    else:
        temperature_trend = "No valid trend"

    # 3. PLANT GROWTH TREND & RATE
    first_height = first.get("plant_height_cm")
    last_height = last.get("plant_height_cm")

    if first_height is not None and last_height is not None:
        delta_h = round(last_height - first_height, 2)
        if delta_h > 0.15:
            plant_growth_trend = "Growing"
        elif delta_h < -0.2:
            plant_growth_trend = "No valid trend"
        else:
            plant_growth_trend = "Stable"

        # Biological Rate requirement: At least 24 hours (86,400 seconds) of observation
        # Biological canopy growth cannot be scientifically inferred from short test periods.
        if time_span_seconds >= 86400 and time_span_days > 0:
            rate_h = round(delta_h / time_span_days, 2)
            plant_growth_rate_cm_per_day = rate_h
            growth_rate_label = f"{rate_h:+.2f} cm / day"
        else:
            plant_growth_rate_cm_per_day = None
            growth_rate_label = "Insufficient long-term data (< 24h)"
    else:
        plant_growth_trend = "No valid trend"
        plant_growth_rate_cm_per_day = None
        growth_rate_label = "Insufficient data"

    return {
        "moisture_trend": moisture_trend,
        "temperature_trend": temperature_trend,
        "plant_growth_trend": plant_growth_trend,
        "moisture_rate_pct_per_hour": moisture_rate_pct_per_hour,
        "moisture_rate_label": moisture_rate_label,
        "plant_growth_rate_cm_per_day": plant_growth_rate_cm_per_day,
        "growth_rate_label": growth_rate_label,
        "time_span_seconds": time_span_seconds,
        "time_span_hours": round(time_span_hours, 2)
    }
