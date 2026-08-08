import sqlite3
import unittest

from services.historical_schema import (
    IMPORT_BATCH_COLUMNS,
    MEASUREMENT_COLUMNS,
    SCHEMA_VERSION,
    ensure_historical_energy_schema,
)


BASE_SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY);
CREATE TABLE members (
    id INTEGER PRIMARY KEY,
    bezug_zp TEXT,
    bezug_ab TEXT,
    einspeiser_zp TEXT,
    einspeiser_ab TEXT
);
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY,
    source_file TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL
);
CREATE TABLE metering_points (
    id INTEGER PRIMARY KEY,
    metering_point_id TEXT NOT NULL UNIQUE,
    energy_direction TEXT NOT NULL
);
CREATE TABLE meter_codes (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE);
CREATE TABLE measurements (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    metering_point_id TEXT NOT NULL,
    timestamp_start TEXT NOT NULL,
    timestamp_end TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    meter_code_id INTEGER NOT NULL,
    value_kwh REAL NOT NULL,
    quality TEXT NOT NULL,
    is_estimated INTEGER DEFAULT 0
);
"""


class HistoricalSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(BASE_SCHEMA)

    def tearDown(self):
        self.db.close()

    @staticmethod
    def columns(db, table):
        return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}

    def test_migration_is_additive_and_idempotent(self):
        ensure_historical_energy_schema(self.db)
        ensure_historical_energy_schema(self.db)

        self.assertTrue(set(IMPORT_BATCH_COLUMNS) <= self.columns(self.db, "import_batches"))
        self.assertTrue(set(MEASUREMENT_COLUMNS) <= self.columns(self.db, "measurements"))
        self.assertIn("token_hash", self.columns(self.db, "import_staging"))
        self.assertIn("expires_at", self.columns(self.db, "import_staging"))
        self.assertIn("token_hash", self.columns(self.db, "import_staging"))
        self.assertIn("expires_at", self.columns(self.db, "import_staging"))
        version = self.db.execute(
            "SELECT version FROM schema_migrations WHERE version=?", (SCHEMA_VERSION,)
        ).fetchone()
        self.assertEqual(version[0], SCHEMA_VERSION)

    def test_unique_measurement_identity_blocks_duplicates(self):
        ensure_historical_energy_schema(self.db)
        values = (1, "AT001", "2026-01-01T00:00:00", "2026-01-01T00:15:00", 15, 1, 1, "L1")
        self.db.execute("""
            INSERT INTO measurements (
                batch_id, metering_point_id, timestamp_start, timestamp_end,
                interval_minutes, meter_code_id, value_kwh, quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, values)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("""
                INSERT INTO measurements (
                    batch_id, metering_point_id, timestamp_start, timestamp_end,
                    interval_minutes, meter_code_id, value_kwh, quality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, values)

    def test_member_can_have_multiple_metering_points(self):
        ensure_historical_energy_schema(self.db)
        self.db.execute("INSERT INTO members(id) VALUES (1)")
        self.db.executemany(
            "INSERT INTO metering_points(id, metering_point_id, energy_direction) VALUES (?, ?, ?)",
            [(1, "AT001", "CONSUMPTION"), (2, "AT002", "GENERATION")],
        )
        self.db.executemany("""
            INSERT INTO member_metering_points(
                member_id, metering_point_id, direction, role, valid_from
            ) VALUES (?, ?, ?, ?, ?)
        """, [
            (1, "AT001", "CONSUMPTION", "consumer", "2026-01-01"),
            (1, "AT002", "GENERATION", "producer", "2026-01-01"),
        ])
        count = self.db.execute(
            "SELECT COUNT(*) FROM member_metering_points WHERE member_id=1"
        ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_existing_member_point_columns_are_backfilled_once(self):
        self.db.execute("""
            INSERT INTO members(
                id, bezug_zp, bezug_ab, einspeiser_zp, einspeiser_ab
            ) VALUES (1, 'AT001', '2026-01-01', 'AT002', '2026-02-01')
        """)
        self.db.executemany(
            "INSERT INTO metering_points(id, metering_point_id, energy_direction) VALUES (?, ?, ?)",
            [(1, "AT001", "CONSUMPTION"), (2, "AT002", "GENERATION")],
        )
        ensure_historical_energy_schema(self.db)
        ensure_historical_energy_schema(self.db)
        rows = self.db.execute("""
            SELECT metering_point_id, direction, role, valid_from
            FROM member_metering_points ORDER BY direction
        """).fetchall()
        self.assertEqual(rows, [
            ("AT001", "CONSUMPTION", "consumer", "2026-01-01"),
            ("AT002", "GENERATION", "producer", "2026-02-01"),
        ])


if __name__ == "__main__":
    unittest.main()
