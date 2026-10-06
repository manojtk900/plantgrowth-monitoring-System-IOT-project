"""
app.py
======
IoT-Based Plant Growth & Environmental Monitoring System
Backend REST API & Gateway built with Python Flask & SQLite.
Preserves existing ESP32 API contracts while delivering robust validation,
accurate heartbeat evaluation, persistent calibration settings,
advanced history filtering, and real trend/rate analytics.
"""

from flask import Flask, render_template, request, jsonify, Response
import sqlite3
import os
import io
import csv
from datetime import datetime

from calculations import (
    DRY_RAW,
    WET_RAW,
    SENSOR_MOUNT_HEIGHT_CM,
    DRYING_RISK_TEMP_THRESHOLD,
    LOW_MOISTURE_THRESHOLD,
    HEARTBEAT_TIMEOUTS,
    MOISTURE_CLASSIFICATIONS,
    TEMP_RANGES,
    get_calibration,
    set_calibration,
    validate_calibration_settings,
    validate_moisture_raw,
    validate_temperature_c,
    validate_distance_cm,
    validate_plant_height_cm,
    calculate_moisture_percent,
    classify_moisture,
    calculate_drying_risk,
    calculate_plant_condition_score,
    evaluate_device_liveness,
    calculate_trends_and_rates
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "plant-monitor-dev-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2MB maximum payload limit

import db as db_layer

# =====================================================================
# DATABASE CONFIGURATION & ABSTRACTION
# =====================================================================

DATABASE_FOLDER = "database"
DATABASE_PATH = os.path.join(DATABASE_FOLDER, "plant_monitor.db")


def get_db():
    """
    Get unified database connection wrapper (SQLite or PostgreSQL).
    Respects app.config['DATABASE_URL'], app.config['DATABASE'], or DATABASE_PATH.
    """
    target = app.config.get("DATABASE_URL") or app.config.get("DATABASE") or DATABASE_PATH
    return db_layer.get_db(target)


def initialize_database():
    """
    Initialize database schema, indexes, and default calibration settings.
    Non-destructive: preserves all existing historical records.
    """
    target = app.config.get("DATABASE_URL") or app.config.get("DATABASE") or DATABASE_PATH
    db_layer.init_db(target)
    load_settings_from_db()




def load_settings_from_db():
    """Reads persistent settings from SQLite into calculations module."""
    try:
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute("SELECT key, value FROM system_settings")
        rows = cursor.fetchall()
        connection.close()

        settings_dict = {row["key"]: row["value"] for row in rows}
        if "dry_raw" in settings_dict and "wet_raw" in settings_dict:
            set_calibration(
                dry_raw=float(settings_dict["dry_raw"]),
                wet_raw=float(settings_dict["wet_raw"]),
                mount_height_cm=float(settings_dict.get("sensor_mount_height_cm", 30.0)),
                drying_risk_temp_threshold=float(settings_dict.get("drying_risk_temp_threshold", 30.0)),
                low_moisture_threshold=float(settings_dict.get("low_moisture_threshold", 25.0))
            )
    except Exception as e:
        print("Notice: using default calibration settings:", e)


# =====================================================================
# WEB DASHBOARD ROUTE
# =====================================================================

@app.route("/")
def dashboard():
    return render_template("index.html")


# =====================================================================
# API — SYSTEM CONFIGURATION & CALIBRATION (PHASE 6)
# =====================================================================

@app.route("/api/config", methods=["GET"])
def get_system_config():
    """
    Returns centralized configuration parameters so the frontend does
    not hardcode calibration constants, classification bands, or timeouts.
    """
    cal = get_calibration()
    return jsonify({
        "success": True,
        "calibration": cal,
        "moisture_classifications": MOISTURE_CLASSIFICATIONS,
        "heartbeat_timeouts": HEARTBEAT_TIMEOUTS,
        "temp_ranges": TEMP_RANGES,
        "humidity_sensor_present": False,
        "humidity_disclaimer": "No physical atmospheric humidity sensor installed."
    })


@app.route("/api/settings", methods=["GET", "POST"])
def manage_settings():
    """
    GET: Returns current active and persisted calibration settings with metadata.
    POST: Validates and updates calibration constants safely in SQLite and memory.
    """
    if request.method == "GET":
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute("SELECT key, value, updated_at FROM system_settings")
        rows = cursor.fetchall()
        connection.close()

        settings_dict = {row["key"]: row["value"] for row in rows}
        latest_update = max((row["updated_at"] for row in rows), default=None)

        cal = get_calibration()
        return jsonify({
            "success": True,
            "settings": {
                "dry_raw": cal["dry_raw"],
                "wet_raw": cal["wet_raw"],
                "sensor_mount_height_cm": cal["sensor_mount_height_cm"],
                "drying_risk_temp_threshold": cal["drying_risk_temp_threshold"],
                "low_moisture_threshold": cal["low_moisture_threshold"],
                "device_id": settings_dict.get("device_id", "ESP32_003"),
                "last_updated": latest_update
            },
            "explanation": "Relative Soil Moisture Index (RSMI) calibration maps raw capacitive ADC output between dry soil and water-saturated baselines. Managed entirely on backend."
        })

    # POST: Update settings
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "Invalid JSON payload"
        }), 400

    current_cal = get_calibration()
    dry_raw = data.get("dry_raw", current_cal["dry_raw"])
    wet_raw = data.get("wet_raw", current_cal["wet_raw"])
    mount_height = data.get("sensor_mount_height_cm", current_cal["sensor_mount_height_cm"])
    temp_thresh = data.get("drying_risk_temp_threshold", current_cal["drying_risk_temp_threshold"])
    moist_thresh = data.get("low_moisture_threshold", current_cal["low_moisture_threshold"])

    is_valid, err_msg, sanitized = validate_calibration_settings(
        dry_raw=dry_raw,
        wet_raw=wet_raw,
        mount_height_cm=mount_height,
        drying_risk_temp_threshold=temp_thresh,
        low_moisture_threshold=moist_thresh
    )

    if not is_valid:
        return jsonify({
            "success": False,
            "message": err_msg
        }), 400

    now_iso = datetime.now().isoformat(timespec="seconds")
    connection = get_db()
    cursor = connection.cursor()

    for key, val in sanitized.items():
        cursor.execute("""
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, str(val), now_iso))

    connection.commit()
    connection.close()

    # Update runtime memory constants
    set_calibration(**sanitized)

    return jsonify({
        "success": True,
        "message": "Calibration settings updated successfully",
        "settings": {
            **sanitized,
            "last_updated": now_iso
        }
    })


# =====================================================================
# API — INGEST SENSOR READING (ESP32 COMPATIBLE)
# =====================================================================

@app.route("/api/sensor-data", methods=["POST"])
def add_sensor_data():
    """
    Ingests telemetry from ESP32 DevKit V1.
    Preserves exact contract: returns HTTP 201 with reading_id,
    created_at, moisture_raw, and moisture_percent.
    """
    data = request.get_json(silent=True)

    if not data or not isinstance(data, dict):
        return jsonify({
            "success": False,
            "message": "No JSON data received or invalid payload"
        }), 400

    # 1. Device Identification
    device_id = str(data.get("device_id", "ESP32_003")).strip()
    if not device_id:
        device_id = "ESP32_003"

    # 2. Soil Moisture Validation & Backend RSMI Calculation
    raw_in = data.get("moisture_raw")
    moisture_raw = validate_moisture_raw(raw_in)
    moisture_percent = calculate_moisture_percent(moisture_raw)

    # 3. Temperature Validation (Filters out -127°C, 85°C hardware faults)
    temp_in = data.get("temperature_c")
    temperature_c = validate_temperature_c(temp_in)

    # 4. Ultrasonic Distance & Plant Height Validation
    dist_in = data.get("distance_cm")
    distance_cm = validate_distance_cm(dist_in)

    height_in = data.get("plant_height_cm")
    plant_height_cm = validate_plant_height_cm(height_in, distance_cm=distance_cm)

    # 5. Hardware Status Flag
    status = str(data.get("status", "OK")).strip()
    if not status:
        status = "OK"

    # 6. Server Timestamp (ISO format with seconds precision)
    created_at = datetime.now().isoformat(timespec="seconds")

    # 7. Persist to Database
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO sensor_readings (
            device_id,
            moisture_raw,
            moisture_percent,
            temperature_c,
            distance_cm,
            plant_height_cm,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        device_id,
        moisture_raw,
        moisture_percent,
        temperature_c,
        distance_cm,
        plant_height_cm,
        status,
        created_at
    ))

    connection.commit()
    reading_id = cursor.lastrowid
    connection.close()

    # Derived context for response
    moisture_info = classify_moisture(moisture_percent)
    drying_risk = calculate_drying_risk(moisture_percent, temperature_c)
    condition = calculate_plant_condition_score(
        moisture_percent,
        temperature_c,
        drying_risk["risk_level"],
        status
    )

    # Return HTTP 201 preserving full backwards-compatibility with ESP32
    return jsonify({
        "success": True,
        "message": "Sensor reading saved successfully",
        "reading_id": reading_id,
        "created_at": created_at,
        "moisture_raw": moisture_raw,
        "moisture_percent": moisture_percent,
        "temperature_c": temperature_c,
        "distance_cm": distance_cm,
        "plant_height_cm": plant_height_cm,
        "device_id": device_id,
        "moisture_status": moisture_info["label"],
        "drying_risk": drying_risk["risk_level"],
        "condition_score": condition["score"]
    }), 201


# =====================================================================
# API — GET LATEST SENSOR READING
# =====================================================================

@app.route("/api/latest", methods=["GET"])
def get_latest():
    """
    Returns the most recent reading from the database, enriched with
    moisture classification, drying risk, plant condition score, and liveness.
    """
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM sensor_readings
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    connection.close()

    if row is None:
        return jsonify({
            "success": False,
            "message": "No sensor data available"
        }), 404

    data = dict(row)

    # Enrich with transparent decision engines
    moisture_info = classify_moisture(data["moisture_percent"])
    drying_risk = calculate_drying_risk(data["moisture_percent"], data["temperature_c"])
    condition = calculate_plant_condition_score(
        data["moisture_percent"],
        data["temperature_c"],
        drying_risk["risk_level"],
        data["status"]
    )
    liveness = evaluate_device_liveness(data["created_at"])

    data["moisture_status"] = moisture_info["label"]
    data["moisture_color"] = moisture_info["color"]
    data["drying_risk"] = drying_risk
    data["plant_condition"] = condition
    data["device_liveness"] = liveness

    return jsonify({
        "success": True,
        "data": data
    })


# =====================================================================
# API — SENSOR HISTORY (SEARCH, FILTERING, PAGINATION)
# =====================================================================

@app.route("/api/history", methods=["GET"])
def get_history():
    """
    Returns historical readings in reverse chronological order.
    Supports search, date range, moisture range, temperature range,
    device filtering, and pagination.
    """
    limit = request.args.get("limit", default=30, type=int)
    offset = request.args.get("offset", default=0, type=int)
    search = request.args.get("search", default="", type=str).strip()
    device_id = request.args.get("device_id", default="", type=str).strip()
    date_from = request.args.get("date_from", default="", type=str).strip()
    date_to = request.args.get("date_to", default="", type=str).strip()
    min_moisture = request.args.get("min_moisture", default=None, type=float)
    max_moisture = request.args.get("max_moisture", default=None, type=float)
    min_temp = request.args.get("min_temp", default=None, type=float)
    max_temp = request.args.get("max_temp", default=None, type=float)

    limit = max(1, min(500, limit))
    offset = max(0, offset)

    conditions = []
    params = []

    if search:
        conditions.append("(device_id LIKE ? OR status LIKE ? OR created_at LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    if device_id:
        conditions.append("device_id = ?")
        params.append(device_id)

    if date_from:
        conditions.append("created_at >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("created_at <= ?")
        params.append(date_to)

    if min_moisture is not None:
        conditions.append("moisture_percent >= ?")
        params.append(min_moisture)

    if max_moisture is not None:
        conditions.append("moisture_percent <= ?")
        params.append(max_moisture)

    if min_temp is not None:
        conditions.append("temperature_c >= ?")
        params.append(min_temp)

    if max_temp is not None:
        conditions.append("temperature_c <= ?")
        params.append(max_temp)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    connection = get_db()
    cursor = connection.cursor()

    # Total matching records count
    count_sql = f"SELECT COUNT(*) AS total FROM sensor_readings {where_clause}"
    cursor.execute(count_sql, params)
    total_count = cursor.fetchone()["total"]

    # Paginated data query
    data_sql = f"""
        SELECT *
        FROM sensor_readings
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(data_sql, params + [limit, offset])
    rows = cursor.fetchall()

    # List of available devices for filter dropdowns
    cursor.execute("SELECT DISTINCT device_id FROM sensor_readings ORDER BY device_id")
    device_rows = cursor.fetchall()
    available_devices = [r["device_id"] for r in device_rows]

    connection.close()

    return jsonify({
        "success": True,
        "count": len(rows),
        "total": total_count,
        "offset": offset,
        "limit": limit,
        "available_devices": available_devices,
        "data": [dict(r) for r in rows]
    })


# =====================================================================
# API — EXPORT SENSOR HISTORY AS CSV (PHASE 5)
# =====================================================================

@app.route("/api/history/export", methods=["GET"])
def export_history_csv():
    """
    Exports sensor history as a clean, standardized CSV file compatible
    with Excel and data analysis packages. Respects active filters.
    """
    search = request.args.get("search", default="", type=str).strip()
    device_id = request.args.get("device_id", default="", type=str).strip()
    date_from = request.args.get("date_from", default="", type=str).strip()
    date_to = request.args.get("date_to", default="", type=str).strip()

    conditions = []
    params = []

    if search:
        conditions.append("(device_id LIKE ? OR status LIKE ? OR created_at LIKE ?)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    if device_id:
        conditions.append("device_id = ?")
        params.append(device_id)

    if date_from:
        conditions.append("created_at >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("created_at <= ?")
        params.append(date_to)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    connection = get_db()
    cursor = connection.cursor()

    export_sql = f"""
        SELECT id, created_at, device_id, moisture_raw, moisture_percent,
               temperature_c, distance_cm, plant_height_cm, status
        FROM sensor_readings
        {where_clause}
        ORDER BY id ASC
    """
    cursor.execute(export_sql, params)
    rows = cursor.fetchall()
    connection.close()

    # Generate CSV with UTF-8 BOM so Excel opens it with proper encoding
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM for Microsoft Excel
    writer = csv.writer(output)

    writer.writerow([
        "Record_ID",
        "Timestamp_ISO",
        "Device_ID",
        "Moisture_Raw_ADC",
        "Moisture_Percent_RSMI",
        "Temperature_Celsius",
        "Distance_CM",
        "Plant_Height_CM",
        "Status"
    ])

    for r in rows:
        writer.writerow([
            r["id"],
            r["created_at"],
            r["device_id"],
            r["moisture_raw"] if r["moisture_raw"] is not None else "",
            r["moisture_percent"] if r["moisture_percent"] is not None else "",
            r["temperature_c"] if r["temperature_c"] is not None else "",
            r["distance_cm"] if r["distance_cm"] is not None else "",
            r["plant_height_cm"] if r["plant_height_cm"] is not None else "",
            r["status"] if r["status"] is not None else ""
        ])

    csv_data = output.getvalue()
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"plant_monitor_history_{timestamp_str}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


# =====================================================================
# API — DEVICE STATUS (ACCURATE HEARTBEAT)
# =====================================================================

@app.route("/api/status", methods=["GET"])
def device_status():
    """
    Evaluates hardware liveness from the timestamp of the latest valid ESP32 reading.
    Does NOT claim ONLINE merely because a database row exists.
    States:
      ONLINE:  < 30s
      RECENT:  30s - 90s
      STALE:   90s - 300s
      OFFLINE: > 300s
    """
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT created_at, device_id
        FROM sensor_readings
        ORDER BY id DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    connection.close()

    if row is None:
        return jsonify({
            "success": True,
            "online": False,
            "state": "OFFLINE",
            "message": "No data received yet",
            "last_update": None,
            "device_id": None,
            "seconds_since_last_seen": None,
            "timeouts": HEARTBEAT_TIMEOUTS
        })

    liveness = evaluate_device_liveness(row["created_at"])

    return jsonify({
        "success": True,
        "online": liveness["online"],
        "state": liveness["state"],
        "label": liveness["label"],
        "badge_class": liveness["badge_class"],
        "seconds_since_last_seen": liveness["seconds_since_last_seen"],
        "last_update": row["created_at"],
        "device_id": row["device_id"],
        "timeouts": HEARTBEAT_TIMEOUTS
    })


# =====================================================================
# API — ADVANCED ANALYTICS & TREND RATES (PHASE 5)
# =====================================================================

@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """
    Calculates summary aggregates, trends, and change rates from real historical
    database records. Only calculates rates when sufficient timestamped data exists.
    Never fabricates trends or statistics.
    """
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) AS total_samples,
            MIN(moisture_percent) AS min_moisture,
            MAX(moisture_percent) AS max_moisture,
            AVG(moisture_percent) AS avg_moisture,
            MIN(temperature_c) AS min_temp,
            MAX(temperature_c) AS max_temp,
            AVG(temperature_c) AS avg_temp,
            MIN(plant_height_cm) AS min_height,
            MAX(plant_height_cm) AS max_height,
            MIN(created_at) AS first_reading_time,
            MAX(created_at) AS latest_reading_time
        FROM sensor_readings
        WHERE moisture_percent IS NOT NULL
          AND temperature_c IS NOT NULL
    """)

    summary = dict(cursor.fetchone())

    # Get chronological records for trend and rate calculation
    cursor.execute("""
        SELECT created_at, moisture_percent, temperature_c, plant_height_cm
        FROM sensor_readings
        WHERE moisture_percent IS NOT NULL
          AND plant_height_cm IS NOT NULL
        ORDER BY id ASC
    """)
    chronological_rows = cursor.fetchall()
    connection.close()

    readings_list = [dict(r) for r in chronological_rows]

    # Calculate trends and rates using mathematical engine
    trends_and_rates = calculate_trends_and_rates(readings_list)

    # First and latest height for net growth calculation
    baseline_height = readings_list[0]["plant_height_cm"] if readings_list else None
    current_height = readings_list[-1]["plant_height_cm"] if readings_list else None
    total_growth = round(current_height - baseline_height, 2) if (current_height and baseline_height) else 0.0

    cal = get_calibration()

    return jsonify({
        "success": True,
        "sample_count": summary["total_samples"],
        "time_span": {
            "from": summary["first_reading_time"],
            "to": summary["latest_reading_time"],
            "hours": trends_and_rates["time_span_hours"]
        },
        "moisture": {
            "avg": round(summary["avg_moisture"], 1) if summary["avg_moisture"] is not None else None,
            "min": summary["min_moisture"],
            "max": summary["max_moisture"],
            "trend": trends_and_rates["moisture_trend"],
            "rate_pct_per_hour": trends_and_rates["moisture_rate_pct_per_hour"],
            "rate_label": trends_and_rates["moisture_rate_label"],
            "calibration_dry_raw": cal["dry_raw"],
            "calibration_wet_raw": cal["wet_raw"]
        },
        "temperature": {
            "avg": round(summary["avg_temp"], 1) if summary["avg_temp"] is not None else None,
            "min": summary["min_temp"],
            "max": summary["max_temp"],
            "trend": trends_and_rates["temperature_trend"],
            "unit": "°C"
        },
        "growth": {
            "baseline_height_cm": baseline_height,
            "current_height_cm": current_height,
            "min_height_cm": summary["min_height"],
            "max_height_cm": summary["max_height"],
            "total_growth_cm": total_growth,
            "trend": trends_and_rates["plant_growth_trend"],
            "rate_cm_per_day": trends_and_rates["plant_growth_rate_cm_per_day"],
            "rate_label": trends_and_rates["growth_rate_label"],
            "sensor_mount_height_cm": cal["sensor_mount_height_cm"]
        }
    })


# =====================================================================
# API — PRODUCTION HEALTH CHECK (PHASE 7.12)
# =====================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """
    Lightweight health check endpoint for cloud orchestrators (Render) and monitors.
    Returns HTTP 200 when application and database are responsive.
    Returns HTTP 503 if database connection fails.
    Never exposes internal credentials, connection strings, or system paths.
    """
    try:
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        connection.close()

        db_state = "connected" if row else "unresponsive"
        return jsonify({
            "status": "ok",
            "service": "plant_growth_monitor",
            "database": db_state
        }), 200
    except Exception:
        return jsonify({
            "status": "degraded",
            "service": "plant_growth_monitor",
            "database": "unavailable"
        }), 503


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "success": False,
        "error": "Payload too large",
        "message": "Incoming request exceeds 2MB maximum payload threshold"
    }), 413


@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({
        "success": False,
        "error": "Internal Server Error",
        "message": "An unexpected error occurred. Internal diagnostics are not exposed."
    }), 500


# =====================================================================
# START APPLICATION
# =====================================================================

initialize_database()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true") or os.environ.get("FLASK_ENV") == "development"
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug_mode
    )