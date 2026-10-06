"""
tests/test_backend.py
=====================
Automated unit & integration test suite for the IoT Plant Growth Monitor.
Tests cover:
  1. Capacitive moisture calibration math & clamping
  2. Sensor input validation (ADC range, DS18B20 -127°C, negative distance)
  3. Temperature-aware drying risk decision rules
  4. Explainable Plant Condition Score calculation
  5. Device heartbeat liveness states
  6. Calibration settings validation & dynamic configuration (Phase 6)
  7. Trends and rates calculations (Phase 5)
  8. Database operations and record preservation
  9. REST API endpoints:
     - POST /api/sensor-data
     - GET /api/latest
     - GET /api/history (with search, device, and date filters)
     - GET /api/history/export (CSV output)
     - GET /api/status
     - GET /api/config
     - GET /api/settings and POST /api/settings
     - GET /api/analytics (summary, trends, rates)
"""

import unittest
import sqlite3
import os
import json
from datetime import datetime, timedelta

from calculations import (
    DRY_RAW,
    WET_RAW,
    calculate_moisture_percent,
    classify_moisture,
    validate_moisture_raw,
    validate_temperature_c,
    validate_distance_cm,
    validate_plant_height_cm,
    calculate_drying_risk,
    calculate_plant_condition_score,
    evaluate_device_liveness,
    HEARTBEAT_TIMEOUTS,
    validate_calibration_settings,
    calculate_trends_and_rates,
    get_calibration,
    set_calibration
)
import app as flask_module


class TestMoistureAndValidation(unittest.TestCase):
    """Test core math, calibration boundaries, and sensor input validation."""

    def test_moisture_dry_calibration_point(self):
        """Dry baseline raw (3326) must yield 0.0% relative moisture."""
        pct = calculate_moisture_percent(DRY_RAW)
        self.assertEqual(pct, 0.0)

    def test_moisture_wet_calibration_point(self):
        """Wet baseline raw (1520) must yield 100.0% relative moisture."""
        pct = calculate_moisture_percent(WET_RAW)
        self.assertEqual(pct, 100.0)

    def test_moisture_midpoint(self):
        """Midpoint ((3326 + 1520) / 2 = 2423) must yield 50.0%."""
        pct = calculate_moisture_percent(2423.0)
        self.assertEqual(pct, 50.0)

    def test_moisture_clamping_above_dry(self):
        """Raw value higher than dry point (e.g. 3500) must clamp to 0.0%, never negative."""
        pct = calculate_moisture_percent(3500.0)
        self.assertEqual(pct, 0.0)

    def test_moisture_clamping_below_wet(self):
        """Raw value lower than wet point (e.g. 1000) must clamp to 100.0%, never > 100%."""
        pct = calculate_moisture_percent(1000.0)
        self.assertEqual(pct, 100.0)

    def test_moisture_null_and_invalid(self):
        """Null or unparseable raw values must return None."""
        self.assertIsNone(calculate_moisture_percent(None))
        self.assertIsNone(calculate_moisture_percent("invalid"))
        self.assertIsNone(calculate_moisture_percent(-10))
        self.assertIsNone(calculate_moisture_percent(5000))

    def test_temperature_validation_disconnect_code(self):
        """DS18B20 disconnected sensor returns -127.0°C; must be filtered out."""
        self.assertIsNone(validate_temperature_c(-127.0))
        self.assertIsNone(validate_temperature_c(-127))

    def test_temperature_validation_poweron_register(self):
        """DS18B20 unconverted register returns 85.0°C; must be filtered out."""
        self.assertIsNone(validate_temperature_c(85.0))

    def test_temperature_validation_valid(self):
        """Normal ambient temperature must pass through."""
        self.assertEqual(validate_temperature_c(27.75), 27.75)
        self.assertEqual(validate_temperature_c("28.5"), 28.5)

    def test_distance_validation_rejects_negative(self):
        """HC-SR04 distance must never be negative."""
        self.assertIsNone(validate_distance_cm(-5.0))
        self.assertEqual(validate_distance_cm(7.8), 7.8)

    def test_plant_height_validation(self):
        """Plant height calculation and non-negative constraint."""
        # 30.0 - 7.8 = 22.2 cm
        self.assertEqual(validate_plant_height_cm(None, distance_cm=7.8), 22.2)
        # Never negative
        self.assertEqual(validate_plant_height_cm(-2.0), 0.0)


class TestDryingRiskAndConditionScore(unittest.TestCase):
    """Test rule-based drying risk engine and explainable condition score."""

    def test_high_drying_risk_hot_and_dry(self):
        """Low moisture (15%) + high temperature (32°C) = High drying risk."""
        risk = calculate_drying_risk(15.0, 32.0)
        self.assertEqual(risk["risk_level"], "High")
        self.assertEqual(risk["badge_class"], "danger")

    def test_moderate_drying_risk_dry_and_cool(self):
        """Low moisture (15%) + cool temperature (18°C) = Moderate drying risk."""
        risk = calculate_drying_risk(15.0, 18.0)
        self.assertEqual(risk["risk_level"], "Moderate")

    def test_low_drying_risk_good_moisture(self):
        """Good moisture (65%) + normal temperature (26°C) = Low drying risk."""
        risk = calculate_drying_risk(65.0, 26.0)
        self.assertEqual(risk["risk_level"], "Low")

    def test_plant_condition_score_explainability(self):
        """Condition score must return itemized reasons and breakdown."""
        score_data = calculate_plant_condition_score(
            moisture_percent=65.0,
            temperature_c=25.0,
            drying_risk_level="Low",
            sensor_status="OK"
        )
        self.assertGreaterEqual(score_data["score"], 90)
        self.assertEqual(score_data["status"], "Optimal")
        self.assertIn("Optimal", score_data["breakdown"]["moisture"])
        self.assertTrue(len(score_data["reasons"]) > 0)


class TestHeartbeatLiveness(unittest.TestCase):
    """Test device status liveness calculation based on time elapsed."""

    def test_liveness_online(self):
        now = datetime.now()
        reading_time = (now - timedelta(seconds=10)).isoformat()
        status = evaluate_device_liveness(reading_time, current_time=now)
        self.assertTrue(status["online"])
        self.assertEqual(status["state"], "ONLINE")

    def test_liveness_recent(self):
        now = datetime.now()
        reading_time = (now - timedelta(seconds=45)).isoformat()
        status = evaluate_device_liveness(reading_time, current_time=now)
        self.assertTrue(status["online"])
        self.assertEqual(status["state"], "RECENT")

    def test_liveness_stale(self):
        now = datetime.now()
        reading_time = (now - timedelta(seconds=150)).isoformat()
        status = evaluate_device_liveness(reading_time, current_time=now)
        self.assertFalse(status["online"])
        self.assertEqual(status["state"], "STALE")

    def test_liveness_offline(self):
        now = datetime.now()
        reading_time = (now - timedelta(seconds=600)).isoformat()
        status = evaluate_device_liveness(reading_time, current_time=now)
        self.assertFalse(status["online"])
        self.assertEqual(status["state"], "OFFLINE")


class TestCalibrationSettingsValidation(unittest.TestCase):
    """Phase 6: Test calibration settings validation and constraints."""

    def test_valid_calibration_settings(self):
        is_valid, msg, val = validate_calibration_settings(dry_raw=3300, wet_raw=1500)
        self.assertTrue(is_valid)
        self.assertEqual(val["dry_raw"], 3300.0)
        self.assertEqual(val["wet_raw"], 1500.0)

    def test_reject_dry_less_than_wet(self):
        """Dry reference must be strictly greater than wet reference."""
        is_valid, msg, val = validate_calibration_settings(dry_raw=1500, wet_raw=3300)
        self.assertFalse(is_valid)
        self.assertIn("strictly greater", msg)

    def test_reject_out_of_bounds_adc(self):
        """ADC reference points must be in 0 to 4095 range."""
        is_valid, msg, val = validate_calibration_settings(dry_raw=5000, wet_raw=1500)
        self.assertFalse(is_valid)
        self.assertIn("0 to 4095", msg)

    def test_reject_narrow_span(self):
        """Difference between dry and wet must be >= 100."""
        is_valid, msg, val = validate_calibration_settings(dry_raw=1550, wet_raw=1500)
        self.assertFalse(is_valid)
        self.assertIn("too narrow", msg)


class TestTrendsAndRatesCalculation(unittest.TestCase):
    """Phase 5: Test trend evaluation and honest rate calculations."""

    def test_insufficient_data_under_two_records(self):
        """Fewer than 2 records must return 'Insufficient data'."""
        res = calculate_trends_and_rates([])
        self.assertEqual(res["moisture_rate_label"], "Insufficient data")
        self.assertEqual(res["growth_rate_label"], "Insufficient data")

        single = [{"created_at": "2026-10-05T18:00:00", "moisture_percent": 50.0, "plant_height_cm": 20.0}]
        res_single = calculate_trends_and_rates(single)
        self.assertEqual(res_single["moisture_rate_label"], "Insufficient data")

    def test_insufficient_time_span_under_15_minutes(self):
        """Readings spaced only 30 seconds apart cannot compute a reliable hourly rate."""
        r1 = {"created_at": "2026-10-05T18:00:00", "moisture_percent": 50.0, "plant_height_cm": 20.0}
        r2 = {"created_at": "2026-10-05T18:00:30", "moisture_percent": 49.8, "plant_height_cm": 20.0}
        res = calculate_trends_and_rates([r1, r2])
        self.assertIn("Insufficient data (< 15 mins)", res["moisture_rate_label"])

    def test_valid_rate_across_multi_hour_readings(self):
        """Readings spaced 2 hours apart with moisture drop calculate valid %/hour rate."""
        r1 = {"created_at": "2026-10-05T18:00:00", "moisture_percent": 60.0, "temperature_c": 26.0, "plant_height_cm": 20.0}
        r2 = {"created_at": "2026-10-05T20:00:00", "moisture_percent": 52.0, "temperature_c": 27.5, "plant_height_cm": 20.2}
        res = calculate_trends_and_rates([r1, r2])
        # Moisture delta: -8.0% over 2 hours = -4.0 % / hour
        self.assertEqual(res["moisture_trend"], "Falling")
        self.assertEqual(res["moisture_rate_pct_per_hour"], -4.0)
        self.assertIn("-4.0", res["moisture_rate_label"])
        self.assertEqual(res["plant_growth_trend"], "Growing")
        # Under 24 hours, plant growth rate must NOT extrapolate to daily rate
        self.assertIn("Insufficient long-term data (< 24h)", res["growth_rate_label"])
        self.assertIsNone(res["plant_growth_rate_cm_per_day"])

    def test_valid_growth_rate_across_multi_day_observation(self):
        """Readings spaced 48 hours apart calculate valid biological cm/day growth rate."""
        r1 = {"created_at": "2026-10-01T10:00:00", "moisture_percent": 50.0, "temperature_c": 25.0, "plant_height_cm": 15.0}
        r2 = {"created_at": "2026-10-03T10:00:00", "moisture_percent": 45.0, "temperature_c": 26.0, "plant_height_cm": 16.2}
        res = calculate_trends_and_rates([r1, r2])
        # Delta H = +1.2 cm over 2 days = +0.60 cm / day
        self.assertEqual(res["plant_growth_trend"], "Growing")
        self.assertEqual(res["plant_growth_rate_cm_per_day"], 0.60)
        self.assertIn("+0.60 cm / day", res["growth_rate_label"])


class TestFlaskEndpoints(unittest.TestCase):
    """Integration test suite for Flask REST API endpoints."""

    @classmethod
    def setUpClass(cls):
        import shutil
        cls.test_db_path = "database/test_plant_monitor.db"
        if os.path.exists("database/plant_monitor.db"):
            shutil.copyfile("database/plant_monitor.db", cls.test_db_path)
        flask_module.app.config["DATABASE"] = cls.test_db_path
        flask_module.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        flask_module.app.config.pop("DATABASE", None)
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def setUp(self):
        self.app = flask_module.app
        self.client = self.app.test_client()

    def test_get_status_endpoint(self):
        """GET /api/status returns valid JSON structure with liveness info."""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertIn("state", data)
        self.assertIn("online", data)
        self.assertIn("timeouts", data)

    def test_get_latest_endpoint(self):
        """GET /api/latest returns valid sensor record."""
        response = self.client.get("/api/latest")
        self.assertIn(response.status_code, [200, 404])
        if response.status_code == 200:
            data = response.get_json()
            self.assertTrue(data["success"])
            self.assertIn("moisture_raw", data["data"])
            self.assertIn("temperature_c", data["data"])
            self.assertIn("device_liveness", data["data"])

    def test_get_history_endpoint_with_filters(self):
        """Phase 5: GET /api/history returns array and respects search and device filters."""
        # 1. Standard history
        response = self.client.get("/api/history?limit=10")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["data"], list)

        # 2. Filter by device_id
        res_dev = self.client.get("/api/history?device_id=ESP32_003&limit=5")
        self.assertEqual(res_dev.status_code, 200)
        data_dev = res_dev.get_json()
        self.assertTrue(data_dev["success"])
        for record in data_dev["data"]:
            self.assertEqual(record["device_id"], "ESP32_003")

    def test_export_history_csv(self):
        """Phase 5: GET /api/history/export returns CSV file attachment."""
        response = self.client.get("/api/history/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["Content-Type"])
        self.assertIn("attachment", response.headers["Content-Disposition"])
        content = response.data.decode("utf-8")
        self.assertIn("Record_ID,Timestamp_ISO,Device_ID", content)

    def test_get_and_post_settings(self):
        """Phase 6: GET and POST /api/settings allows viewing and updating calibration."""
        # 1. GET settings
        get_res = self.client.get("/api/settings")
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.get_json()
        self.assertTrue(get_data["success"])
        self.assertIn("dry_raw", get_data["settings"])
        self.assertIn("wet_raw", get_data["settings"])

        # 2. POST invalid settings (dry < wet) -> 400
        bad_post = self.client.post("/api/settings", json={"dry_raw": 1200, "wet_raw": 3000})
        self.assertEqual(bad_post.status_code, 400)

        # 3. POST valid settings -> 200
        good_post = self.client.post("/api/settings", json={
            "dry_raw": 3326.0,
            "wet_raw": 1520.0,
            "sensor_mount_height_cm": 30.0,
            "drying_risk_temp_threshold": 30.0,
            "low_moisture_threshold": 25.0
        })
        self.assertEqual(good_post.status_code, 200)
        self.assertTrue(good_post.get_json()["success"])

    def test_get_analytics_endpoint(self):
        """Phase 5: GET /api/analytics returns trends, summary stats, and rates."""
        response = self.client.get("/api/analytics")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertIn("sample_count", data)
        self.assertIn("moisture", data)
        self.assertIn("temperature", data)
        self.assertIn("growth", data)
        self.assertIn("rate_label", data["moisture"])
        self.assertIn("rate_label", data["growth"])

    def test_post_sensor_data_validation(self):
        """POST /api/sensor-data accepts valid payload and rejects empty."""
        # 1. Test empty payload
        res_empty = self.client.post("/api/sensor-data", json={})
        self.assertEqual(res_empty.status_code, 400)

        # 2. Test valid ESP32 payload
        payload = {
            "device_id": "ESP32_003",
            "moisture_raw": 3326.0,
            "moisture_percent": None,
            "temperature_c": 27.5,
            "distance_cm": 7.8,
            "plant_height_cm": 22.2,
            "status": "OK"
        }
        res_post = self.client.post("/api/sensor-data", json=payload)
        self.assertEqual(res_post.status_code, 201)
        data = res_post.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["moisture_percent"], 0.0)
        self.assertEqual(data["moisture_raw"], 3326.0)
        self.assertIn("reading_id", data)

    def test_get_health_endpoint(self):
        """Phase 7.12: GET /health returns 200 with service and database status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "plant_growth_monitor")
        self.assertEqual(data["database"], "connected")
        self.assertIn("engine", data)

    def test_database_record_count_preservation(self):
        """Verify the database has at least the original 85 records."""
        conn = sqlite3.connect("database/plant_monitor.db")
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sensor_readings")
        count = c.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 85)


class TestDatabaseAbstraction(unittest.TestCase):
    """Phase 7.3: Unit tests for database abstraction and dialect adaptation."""

    def test_url_normalization(self):
        import db as db_module
        # Fix Render postgres:// to postgresql://
        self.assertEqual(
            db_module.normalize_database_url("postgres://user:pass@host/db"),
            "postgresql://user:pass@host/db"
        )
        self.assertEqual(
            db_module.normalize_database_url("postgresql://user:pass@host/db"),
            "postgresql://user:pass@host/db"
        )

    def test_sql_dialect_adaptation(self):
        import db as db_module
        # SQLite connection preserves '?'
        sqlite_conn = db_module.DatabaseConnection(raw_conn=None, is_postgres=False)
        self.assertEqual(
            sqlite_conn.adapt_sql("SELECT * FROM t WHERE a = ? AND b = ?"),
            "SELECT * FROM t WHERE a = ? AND b = ?"
        )
        # Postgres connection adapts '?' to '%s'
        pg_conn = db_module.DatabaseConnection(raw_conn=None, is_postgres=True)
        self.assertEqual(
            pg_conn.adapt_sql("SELECT * FROM t WHERE a = ? AND b = ?"),
            "SELECT * FROM t WHERE a = %s AND b = %s"
        )


class TestMigrationScript(unittest.TestCase):
    """Phase 7.4: Unit tests for SQLite to PostgreSQL migration script."""

    def test_migration_dry_run_validation(self):
        """Verifies migration utility correctly reads and verifies SQLite source in dry-run mode."""
        from scripts.migrate_sqlite_to_postgres import migrate
        res = migrate(sqlite_path="database/plant_monitor.db", pg_url="", dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertGreaterEqual(res["sensor_count"], 89)
        self.assertEqual(res["settings_count"], 6)

    def test_migration_missing_sqlite_file_error(self):
        """Verifies migration utility raises FileNotFoundError if source DB is missing."""
        from scripts.migrate_sqlite_to_postgres import migrate
        with self.assertRaises(FileNotFoundError):
            migrate(sqlite_path="database/non_existent.db", pg_url="", dry_run=True)


class TestSupabaseReadiness(unittest.TestCase):
    """Phase 7B: Verification of Supabase PostgreSQL URI compatibility."""

    def test_supabase_pooler_url_detection(self):
        import db as db_module
        pooler_url = "postgresql://postgres.myproject:secretpassword@aws-0-us-west-1.pooler.supabase.com:6543/postgres?sslmode=require"
        self.assertTrue(db_module.is_postgres_url(pooler_url))
        self.assertEqual(db_module.normalize_database_url(pooler_url), pooler_url)

    def test_supabase_postgres_scheme_rewrite(self):
        import db as db_module
        # If copied with postgres:// scheme
        raw_url = "postgres://postgres.myproject:secretpassword@aws-0-us-west-1.pooler.supabase.com:5432/postgres?sslmode=require"
        normalized = db_module.normalize_database_url(raw_url)
        self.assertTrue(normalized.startswith("postgresql://"))
        self.assertIn("sslmode=require", normalized)

    def test_biological_growth_rate_24h_requirement(self):
        """Verifies analytics strictly enforce 24-hour observation period for biological growth rates."""
        from calculations import calculate_trends_and_rates
        from datetime import datetime, timedelta
        now = datetime.now()
        # 1. Test short-term readings (only 1 hour span)
        short_records = [
            {"created_at": (now - timedelta(hours=1)).isoformat(), "moisture_percent": 60.0, "temperature_c": 25.0, "plant_height_cm": 15.0},
            {"created_at": now.isoformat(), "moisture_percent": 59.0, "temperature_c": 25.5, "plant_height_cm": 15.2}
        ]
        res_short = calculate_trends_and_rates(short_records)
        self.assertIsNone(res_short["plant_growth_rate_cm_per_day"])
        self.assertIn("Insufficient long-term data (< 24h)", res_short["growth_rate_label"])

        # 2. Test valid multi-day readings (48 hours span)
        long_records = [
            {"created_at": (now - timedelta(hours=48)).isoformat(), "moisture_percent": 60.0, "temperature_c": 25.0, "plant_height_cm": 15.0},
            {"created_at": now.isoformat(), "moisture_percent": 58.0, "temperature_c": 26.0, "plant_height_cm": 15.4}
        ]
        res_long = calculate_trends_and_rates(long_records)
        self.assertIsNotNone(res_long["plant_growth_rate_cm_per_day"])
        self.assertEqual(res_long["plant_growth_rate_cm_per_day"], 0.2)
        self.assertEqual(res_long["growth_rate_label"], "+0.20 cm / day")

    def test_timezone_normalization_liveness(self):
        """Phase 7B Fix: Verifies evaluate_device_liveness handles both offset-aware and offset-naive timestamps without TypeError."""
        from calculations import evaluate_device_liveness, parse_iso_timestamp
        from datetime import datetime, timezone, timedelta

        now_utc = datetime.now(timezone.utc)
        recent_aware = (now_utc - timedelta(seconds=15)).isoformat()
        recent_naive = (datetime.now() - timedelta(seconds=15)).strftime("%Y-%m-%d %H:%M:%S")
        old_aware = "2026-10-05T17:32:46+00:00"
        old_naive = "2026-10-05 17:32:46"
        old_z = "2026-10-05T17:32:46Z"

        # 1. Aware timestamp within 15 seconds -> ONLINE
        res1 = evaluate_device_liveness(recent_aware)
        self.assertTrue(res1["online"])
        self.assertEqual(res1["state"], "ONLINE")

        # 2. Naive timestamp within 15 seconds -> ONLINE
        res2 = evaluate_device_liveness(recent_naive)
        self.assertTrue(res2["online"])
        self.assertEqual(res2["state"], "ONLINE")

        # 3. PostgreSQL aware historical timestamp -> OFFLINE (No TypeError)
        res3 = evaluate_device_liveness(old_aware)
        self.assertFalse(res3["online"])
        self.assertEqual(res3["state"], "OFFLINE")

        # 4. SQLite naive historical timestamp -> OFFLINE (No TypeError)
        res4 = evaluate_device_liveness(old_naive)
        self.assertFalse(res4["online"])
        self.assertEqual(res4["state"], "OFFLINE")

        # 5. UTC Z timestamp -> OFFLINE (No TypeError)
        res5 = evaluate_device_liveness(old_z)
        self.assertFalse(res5["online"])
        self.assertEqual(res5["state"], "OFFLINE")

        # 6. Explicit current_time passed as naive while reading is aware
        res6 = evaluate_device_liveness(old_aware, current_time=datetime.now())
        self.assertFalse(res6["online"])
        self.assertEqual(res6["state"], "OFFLINE")


if __name__ == "__main__":
    unittest.main()
