#!/usr/bin/env python3
"""
Auswertungs-Queries für die EEG-Abrechnung.
Zeigt typische Abrechnungs-Reports aus der importierten Datenbank.
"""

import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = os.environ.get("EEG_DB_PATH", "eeg_data.db")


def print_table(headers, rows, title=""):
    """Einfache Tabellenausgabe."""
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")

    if not rows:
        print("  (keine Daten)")
        return

    # Spaltenbreiten berechnen
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    # Header
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(f"  {header_line}")
    print(f"  {'-' * len(header_line)}")

    # Daten
    for row in rows:
        line = " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(row))
        print(f"  {line}")


def report_monthly_summary(conn, batch_id=None):
    """Monatliche Zusammenfassung pro Zählpunkt und MeterCode."""
    where = f"WHERE m.batch_id = {batch_id}" if batch_id else ""
    rows = conn.execute(f"""
        SELECT
            b.period_start,
            m.metering_point_id,
            mc.label_de,
            mc.code,
            ROUND(SUM(m.value_kwh), 3) as total_kwh,
            COUNT(*) as intervals,
            ROUND(SUM(CASE WHEN m.quality = 'L1' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as pct_L1
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        {where}
        GROUP BY b.period_start, m.metering_point_id, mc.code
        ORDER BY b.period_start, m.metering_point_id, mc.code
    """).fetchall()

    print_table(
        ["Periode", "Zählpunkt", "Bezeichnung", "OBIS-Code", "Summe kWh", "Intervalle", "% L1"],
        rows,
        "Monatssummen pro Zählpunkt und MeterCode"
    )


def report_billing_base(conn, batch_id=None):
    """Abrechnungsgrundlage: Bezug aus Gemeinschaft pro Verbraucher."""
    where = f"AND m.batch_id = {batch_id}" if batch_id else ""
    rows = conn.execute(f"""
        SELECT
            m.metering_point_id as "Zählpunkt",
            ROUND(SUM(CASE WHEN mc.suffix = 'G.01T' AND mc.direction = 'CONSUMPTION'
                       THEN m.value_kwh ELSE 0 END), 3) as "Verbrauch_TF_kWh",
            ROUND(SUM(CASE WHEN mc.suffix = 'G.02' AND mc.direction = 'CONSUMPTION'
                       THEN m.value_kwh ELSE 0 END), 3) as "Bezug_EG_kWh",
            ROUND(SUM(CASE WHEN mc.suffix = 'G.01' AND mc.direction = 'CONSUMPTION'
                       THEN m.value_kwh ELSE 0 END), 3) as "Gesamtverbrauch_kWh"
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN metering_points mp ON mp.metering_point_id = m.metering_point_id
        WHERE mp.energy_direction = 'CONSUMPTION' {where}
        GROUP BY m.metering_point_id
        HAVING "Bezug_EG_kWh" > 0 OR "Verbrauch_TF_kWh" > 0
        ORDER BY "Bezug_EG_kWh" DESC
    """).fetchall()

    print_table(
        ["Zählpunkt", "Verbrauch (TF) kWh", "Bezug EG kWh", "Gesamtverbrauch kWh"],
        rows,
        "Abrechnungsgrundlage Verbraucher (Bezug aus Gemeinschaft)"
    )


def report_generation_summary(conn, batch_id=None):
    """Erzeugung: Übersicht Erzeuger-Zählpunkte."""
    where = f"AND m.batch_id = {batch_id}" if batch_id else ""
    rows = conn.execute(f"""
        SELECT
            m.metering_point_id as "Zählpunkt",
            ROUND(SUM(CASE WHEN mc.suffix = 'G.01T' AND mc.direction = 'GENERATION'
                       THEN m.value_kwh ELSE 0 END), 3) as "Erzeugung_TF_kWh",
            ROUND(SUM(CASE WHEN mc.suffix = 'P.01T'
                       THEN m.value_kwh ELSE 0 END), 3) as "Restüberschuss_kWh",
            ROUND(SUM(CASE WHEN mc.suffix = 'G.01' AND mc.direction = 'GENERATION'
                       THEN m.value_kwh ELSE 0 END), 3) as "Gesamterzeugung_kWh"
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN metering_points mp ON mp.metering_point_id = m.metering_point_id
        WHERE mp.energy_direction = 'GENERATION' {where}
        GROUP BY m.metering_point_id
        HAVING "Erzeugung_TF_kWh" > 0 OR "Gesamterzeugung_kWh" > 0
        ORDER BY "Gesamterzeugung_kWh" DESC
    """).fetchall()

    print_table(
        ["Zählpunkt", "Erzeugung (TF) kWh", "Restüberschuss kWh", "Gesamterzeugung kWh"],
        rows,
        "Abrechnungsgrundlage Erzeuger"
    )


def report_quality_check(conn, batch_id=None):
    """Datenqualitätsprüfung."""
    where = f"WHERE batch_id = {batch_id}" if batch_id else ""
    rows = conn.execute(f"""
        SELECT
            quality,
            COUNT(*) as anzahl,
            ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM measurements {where}), 1) as prozent
        FROM measurements {where}
        GROUP BY quality
        ORDER BY anzahl DESC
    """).fetchall()

    print_table(
        ["Qualität", "Anzahl", "Prozent"],
        rows,
        "Datenqualität (MeteringMethod)"
    )


def report_completeness(conn, batch_id=None):
    """Prüft ob Viertelstunden-Reihen vollständig sind."""
    where = f"WHERE m.batch_id = {batch_id}" if batch_id else ""
    rows = conn.execute(f"""
        SELECT
            m.metering_point_id,
            mc.label_de,
            COUNT(*) as ist_intervalle,
            b.period_start,
            b.period_end
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        {where}
        GROUP BY m.batch_id, m.metering_point_id, mc.id
        ORDER BY m.metering_point_id, mc.label_de
    """).fetchall()

    print_table(
        ["Zählpunkt", "MeterCode", "Intervalle (ist)", "Von", "Bis"],
        rows,
        "Vollständigkeitsprüfung (Soll: 2688 für 28d, 2976 für 31d)"
    )


def main():
    if not os.path.exists(DB_PATH):
        print(f"Datenbank '{DB_PATH}' nicht gefunden. Zuerst import_eda.py ausführen.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    # Alle Reports
    report_monthly_summary(conn)
    report_billing_base(conn)
    report_generation_summary(conn)
    report_quality_check(conn)
    report_completeness(conn)

    conn.close()


if __name__ == "__main__":
    main()
