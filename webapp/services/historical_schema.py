"""Additive, wiederholbare Schemaerweiterung fuer historische Energiedaten."""

import sqlite3


SCHEMA_VERSION = "historical-energy-v2"


IMPORT_BATCH_COLUMNS = {
    "source_sha256": "TEXT",
    "source_format": "TEXT NOT NULL DEFAULT 'xlsx'",
    "source_schema_version": "TEXT",
    "import_status": "TEXT NOT NULL DEFAULT 'committed'",
    "detected_period_start": "TEXT",
    "detected_period_end": "TEXT",
    "data_available_from": "TEXT",
    "data_available_until": "TEXT",
    "metering_point_count": "INTEGER",
    "measurement_count": "INTEGER",
    "missing_interval_count": "INTEGER NOT NULL DEFAULT 0",
    "warning_count": "INTEGER NOT NULL DEFAULT 0",
    "source_timezone": "TEXT NOT NULL DEFAULT 'Europe/Vienna'",
    "committed_at": "TEXT",
    "rolled_back_at": "TEXT",
    "supersedes_import_id": "INTEGER",
}


MEASUREMENT_COLUMNS = {
    "source_row": "INTEGER",
    "raw_timestamp": "TEXT",
    "unit": "TEXT NOT NULL DEFAULT 'kWh'",
    "source_timezone": "TEXT NOT NULL DEFAULT 'Europe/Vienna'",
    "is_corrected": "INTEGER NOT NULL DEFAULT 0",
    "revision": "INTEGER NOT NULL DEFAULT 1",
    "created_at": "TEXT",
}


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _add_columns(db: sqlite3.Connection, table: str, definitions: dict[str, str]) -> None:
    existing = _columns(db, table)
    for name, definition in definitions.items():
        if name not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def ensure_historical_energy_schema(db: sqlite3.Connection) -> None:
    """Installiert ausschliesslich additive Strukturen in einer Transaktion."""
    db.execute("SAVEPOINT historical_energy_schema")
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        _add_columns(db, "import_batches", IMPORT_BATCH_COLUMNS)
        _add_columns(db, "measurements", MEASUREMENT_COLUMNS)

        db.execute("""
            CREATE TABLE IF NOT EXISTS member_metering_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                metering_point_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                role TEXT NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                authorized_from TEXT,
                authorized_to TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                created_by_user_id INTEGER,
                FOREIGN KEY (member_id) REFERENCES members(id),
                FOREIGN KEY (metering_point_id)
                    REFERENCES metering_points(metering_point_id),
                FOREIGN KEY (created_by_user_id) REFERENCES users(id),
                UNIQUE(member_id, metering_point_id, direction, valid_from)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_member_metering_points_member
            ON member_metering_points(member_id, direction, valid_from, valid_to)
        """)
        member_columns = _columns(db, "members")
        if {"bezug_zp", "bezug_ab"} <= member_columns:
            db.execute("""
                INSERT INTO member_metering_points(
                    member_id, metering_point_id, direction, role, valid_from
                )
                SELECT m.id, m.bezug_zp, 'CONSUMPTION', 'consumer', m.bezug_ab
                FROM members m
                JOIN metering_points p ON p.metering_point_id=m.bezug_zp
                WHERE m.bezug_zp IS NOT NULL AND TRIM(m.bezug_zp)!=''
                  AND NOT EXISTS (
                      SELECT 1 FROM member_metering_points x
                      WHERE x.member_id=m.id
                        AND x.metering_point_id=m.bezug_zp
                        AND x.direction='CONSUMPTION'
                  )
            """)
        if {"einspeiser_zp", "einspeiser_ab"} <= member_columns:
            db.execute("""
                INSERT INTO member_metering_points(
                    member_id, metering_point_id, direction, role, valid_from
                )
                SELECT m.id, m.einspeiser_zp, 'GENERATION', 'producer', m.einspeiser_ab
                FROM members m
                JOIN metering_points p ON p.metering_point_id=m.einspeiser_zp
                WHERE m.einspeiser_zp IS NOT NULL AND TRIM(m.einspeiser_zp)!=''
                  AND NOT EXISTS (
                      SELECT 1 FROM member_metering_points x
                      WHERE x.member_id=m.id
                        AND x.metering_point_id=m.einspeiser_zp
                        AND x.direction='GENERATION'
                  )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS import_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id INTEGER,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                uploaded_by_user_id INTEGER,
                FOREIGN KEY (import_batch_id) REFERENCES import_batches(id),
                FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_files_sha256
            ON import_files(sha256, status)
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS import_staging (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                original_filename TEXT NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                data_status TEXT NOT NULL,
                overwrite_existing INTEGER NOT NULL DEFAULT 0,
                preview_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                claimed_at TEXT,
                consumed_at TEXT,
                cancelled_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_staging_expiry
            ON import_staging(expires_at, consumed_at, cancelled_at)
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS import_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                metering_point_id TEXT,
                timestamp_start TEXT,
                source_row INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (import_batch_id) REFERENCES import_batches(id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_warnings_batch
            ON import_warnings(import_batch_id, severity, code)
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS import_data_gaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id INTEGER NOT NULL,
                metering_point_id TEXT NOT NULL,
                meter_code_id INTEGER NOT NULL,
                gap_start TEXT NOT NULL,
                gap_end TEXT NOT NULL,
                missing_intervals INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (import_batch_id) REFERENCES import_batches(id),
                FOREIGN KEY (meter_code_id) REFERENCES meter_codes(id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_data_gaps_batch
            ON import_data_gaps(import_batch_id, metering_point_id, gap_start)
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS measurement_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_measurement_id INTEGER NOT NULL,
                original_batch_id INTEGER NOT NULL,
                replaced_by_batch_id INTEGER NOT NULL,
                metering_point_id TEXT NOT NULL,
                timestamp_start TEXT NOT NULL,
                timestamp_end TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                meter_code_id INTEGER NOT NULL,
                value_kwh REAL NOT NULL,
                quality TEXT NOT NULL,
                is_estimated INTEGER NOT NULL DEFAULT 0,
                archived_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (original_batch_id) REFERENCES import_batches(id),
                FOREIGN KEY (replaced_by_batch_id) REFERENCES import_batches(id),
                FOREIGN KEY (meter_code_id) REFERENCES meter_codes(id)
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_measurement_revisions_identity
            ON measurement_revisions(
                metering_point_id, timestamp_start, meter_code_id, archived_at
            )
        """)
        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_measurements_identity
            ON measurements(metering_point_id, timestamp_start, timestamp_end, meter_code_id)
        """)
        db.execute("""
            INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)
        """, (SCHEMA_VERSION,))
        db.execute("RELEASE SAVEPOINT historical_energy_schema")
    except Exception:
        db.execute("ROLLBACK TO SAVEPOINT historical_energy_schema")
        db.execute("RELEASE SAVEPOINT historical_energy_schema")
        raise
