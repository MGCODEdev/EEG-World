"""Additive, wiederholbare Schemaerweiterungen fuer mobile Endgeraete."""

import sqlite3


SCHEMA_VERSION = "mobile-devices-platform-v1"


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def ensure_mobile_device_schema(db: sqlite3.Connection) -> None:
    """Migriert ``mobile_devices`` ohne vorhandene Geraetedaten zu veraendern.

    Alte Installationen enthielten keine Plattformspalte und sind ausschliesslich
    iOS-Installationen. Der Default ``ios`` erhaelt deshalb die bisherige Semantik,
    waehrend neue Android-Geraete explizit als ``android`` gespeichert werden.
    """
    db.execute("SAVEPOINT mobile_device_schema")
    try:
        table_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mobile_devices'"
        ).fetchone()
        if not table_exists:
            raise sqlite3.OperationalError("Tabelle mobile_devices fehlt")

        db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        if "platform" not in _columns(db, "mobile_devices"):
            db.execute(
                "ALTER TABLE mobile_devices "
                "ADD COLUMN platform TEXT NOT NULL DEFAULT 'ios'"
            )

        # Leere Werte koennen nur aus manuell angelegten Zwischenstaenden stammen.
        # Sie entsprechen wie alle Altgeraete der bisherigen iOS-only-Semantik.
        db.execute("""
            UPDATE mobile_devices
            SET platform='ios'
            WHERE platform IS NULL OR TRIM(platform)=''
        """)
        db.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        db.execute("RELEASE SAVEPOINT mobile_device_schema")
    except Exception:
        db.execute("ROLLBACK TO SAVEPOINT mobile_device_schema")
        db.execute("RELEASE SAVEPOINT mobile_device_schema")
        raise
