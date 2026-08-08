import sqlite3
import unittest

from services.mobile_schema import SCHEMA_VERSION, ensure_mobile_device_schema


class MobileDeviceSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""
            CREATE TABLE mobile_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                device_token TEXT NOT NULL UNIQUE,
                apns_environment TEXT NOT NULL DEFAULT 'sandbox'
            )
        """)
        self.db.execute("""
            INSERT INTO mobile_devices(user_id, device_token)
            VALUES (7, 'legacy-ios-token')
        """)

    def tearDown(self):
        self.db.close()

    def test_adds_platform_and_preserves_legacy_device(self):
        ensure_mobile_device_schema(self.db)

        row = self.db.execute("""
            SELECT user_id, device_token, platform FROM mobile_devices
        """).fetchone()
        self.assertEqual(row, (7, "legacy-ios-token", "ios"))
        migration = self.db.execute(
            "SELECT version FROM schema_migrations WHERE version=?",
            (SCHEMA_VERSION,),
        ).fetchone()
        self.assertEqual(migration, (SCHEMA_VERSION,))

    def test_is_idempotent(self):
        ensure_mobile_device_schema(self.db)
        ensure_mobile_device_schema(self.db)

        columns = [row[1] for row in self.db.execute("PRAGMA table_info(mobile_devices)")]
        self.assertEqual(columns.count("platform"), 1)
        count = self.db.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=?",
            (SCHEMA_VERSION,),
        ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
