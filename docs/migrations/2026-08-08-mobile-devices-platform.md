# Migration `mobile-devices-platform-v1`

- Datum: 8. August 2026
- Produktivdatenbank: `/var/www/eeg/eeg_data.db`
- Betroffene Tabelle: `mobile_devices`
- Backup: `/var/www/eeg/eeg_data.db.bak.pre-mobile-platform-20260808T114941Z`

## Ausgangslage

Der APNs-Worker filtert Geräte mit `d.platform='ios'`. Das deklarative Schema
enthält diese Spalte, das ältere produktive Schema war jedoch ohne
nachvollziehbaren Migrationseintrag aktualisiert worden. Beim Beginn der Prüfung
war die Spalte bereits mit `TEXT NOT NULL DEFAULT 'ios'` vorhanden, während in
`schema_migrations` kein entsprechender Eintrag existierte.

## Umsetzung

`ensure_mobile_device_schema()` prüft das reale Tabellenschema vor jeder Änderung.
Fehlt `platform`, wird ausschließlich folgende additive Migration ausgeführt:

```sql
ALTER TABLE mobile_devices
ADD COLUMN platform TEXT NOT NULL DEFAULT 'ios';
```

Der Default erhält die Semantik aller bestehenden iOS-Geräte. Leere Altwerte
werden als `ios` normalisiert. Danach wird die Version
`mobile-devices-platform-v1` idempotent in `schema_migrations` eingetragen. Die
Migration läuft sowohl beim Initialisieren der Web-App als auch unmittelbar vor
der Verarbeitung des Push-Workers. Es werden keine Tabellen neu erstellt und
keine Nutzdaten gelöscht.

## Verifikation

- Backup mit der SQLite-Backup-Funktion erstellt; `PRAGMA quick_check` ergab `ok`.
- Migration zweimal gegen ein Legacy-Schema ohne `platform` getestet.
- iOS- und Android-Geräteregistrierungstests erfolgreich.
- Produktiver APNs-Auswahl-SQL-Aufruf einschließlich `d.platform='ios'`
  erfolgreich.
- Manueller Lauf von `eeg-push-worker.service`: Exit-Code `0/SUCCESS`.
- Worker-Ergebnis: `selected=0`, `sent=0`, `retry=0`, `failed=0`.
- Service-Journal enthält keinen Fehler `no such column: d.platform`.
