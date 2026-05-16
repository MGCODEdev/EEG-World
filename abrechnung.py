#!/usr/bin/env python3
"""
EEG-Abrechnung: Monatliche Rechnungen und Gutschriften.

Preismodell:
  - Verbraucher zahlen: 10 ct/kWh (Eigendeckung G.03 = tatsächlich aus EEG bezogen)
  - Erzeuger erhalten:   8 ct/kWh (an Gemeinschaft geliefert = G.01T - P.01T)
  - EEG-Marge:           2 ct/kWh

Wichtig: Abgerechnet wird NUR die tatsächlich in der EEG gehandelte Energie!
  - G.03 (Eigendeckung) = was der Verbraucher tatsächlich aus der Gemeinschaft erhalten hat
  - G.01T - P.01T       = was der Erzeuger tatsächlich an die Gemeinschaft geliefert hat
  - Balance:  Summe(G.03) == Summe(G.01T - P.01T)  (muss aufgehen!)

  NICHT verwendet: G.02 (= Zuteilung/Anteil, nicht der reale Handel)
"""

import sqlite3
import sys
import os
from datetime import datetime

DB_PATH = os.environ.get("EEG_DB_PATH", "eeg_data.db")

# Preise in ct/kWh
PREIS_VERBRAUCH = 10.0   # Verbraucher zahlt an EEG
PREIS_ERZEUGUNG = 8.0    # EEG zahlt an Erzeuger
MARGE_EEG = PREIS_VERBRAUCH - PREIS_ERZEUGUNG  # 2 ct/kWh


def load_member_names(conn):
    """Lädt Mitglieder-Namen aus der DB. Gibt dict {zp: name} zurück."""
    names = {}
    try:
        for row in conn.execute('SELECT name, bezug_zp, einspeiser_zp FROM members'):
            name, bzp, ezp = row
            if bzp:
                names[bzp] = name
            if ezp:
                names[ezp] = name
    except Exception:
        pass  # Tabelle existiert noch nicht
    return names


def abrechnung_verbraucher(conn, monat=None):
    """Rechnung pro Verbraucher: Eigendeckung (G.03) × 10 ct/kWh.

    G.03 = tatsächlich aus der EEG bezogene Energie (Eigendeckung).
    """
    names = load_member_names(conn)
    where = f"AND b.period_start = '{monat}'" if monat else ""
    rows = conn.execute(f"""
        SELECT
            b.period_start,
            m.metering_point_id,
            ROUND(SUM(m.value_kwh), 3) as eigendeckung_kwh
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE mc.code = '1-1:2.9.0 G.03'
        {where}
        GROUP BY b.period_start, m.metering_point_id
        ORDER BY b.period_start, m.metering_point_id
    """).fetchall()

    print(f"\n{'='*96}")
    print(f"  RECHNUNG VERBRAUCHER (Eigendeckung aus EEG @ {PREIS_VERBRAUCH:.0f} ct/kWh)")
    print(f"{'='*96}")
    print(f"  {'Monat':<10} {'Name':<30} {'Zählpunkt':<38} {'kWh':>10} {'Betrag €':>10}")
    print(f"  {'-'*100}")

    total_kwh = 0
    total_eur = 0
    monat_summen = {}

    for periode, zp, kwh in rows:
        betrag = kwh * PREIS_VERBRAUCH / 100.0
        total_kwh += kwh
        total_eur += betrag
        m_key = periode[:7]
        if m_key not in monat_summen:
            monat_summen[m_key] = {"kwh": 0, "eur": 0}
        monat_summen[m_key]["kwh"] += kwh
        monat_summen[m_key]["eur"] += betrag
        name = names.get(zp, '?')
        print(f"  {periode[:7]:<10} {name:<30} {zp:<38} {kwh:>10.3f} {betrag:>10.2f}")

    print(f"  {'-'*100}")
    for m_key in sorted(monat_summen):
        s = monat_summen[m_key]
        print(f"  {'Summe ' + m_key:<80} {s['kwh']:>10.3f} {s['eur']:>10.2f}")
    print(f"  {'='*100}")
    print(f"  {'GESAMT':<80} {total_kwh:>10.3f} {total_eur:>10.2f}")

    return total_kwh, total_eur


def abrechnung_erzeuger(conn, monat=None):
    """Gutschrift pro Erzeuger: Lieferung an Gemeinschaft × 8 ct/kWh.

    Lieferung = G.01T (Erzeugung mit TF) - P.01T (Restüberschuss)
    = Energie die tatsächlich von Mitgliedern verbraucht wurde.
    """
    names = load_member_names(conn)
    where = f"AND b.period_start = '{monat}'" if monat else ""
    rows = conn.execute(f"""
        SELECT
            b.period_start,
            m.metering_point_id,
            ROUND(SUM(CASE WHEN mc.code = '1-1:2.9.0 G.01T'
                       THEN m.value_kwh ELSE 0 END), 3) as erzeugung_tf,
            ROUND(SUM(CASE WHEN mc.code = '1-1:2.9.0 P.01T'
                       THEN m.value_kwh ELSE 0 END), 3) as ueberschuss
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN metering_points mp ON mp.metering_point_id = m.metering_point_id
        WHERE mp.energy_direction = 'GENERATION'
          AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
        {where}
        GROUP BY b.period_start, m.metering_point_id
        ORDER BY b.period_start, m.metering_point_id
    """).fetchall()

    print(f"\n{'='*120}")
    print(f"  GUTSCHRIFT ERZEUGER (Lieferung an Gemeinschaft @ {PREIS_ERZEUGUNG:.0f} ct/kWh)")
    print(f"{'='*120}")
    print(f"  {'Monat':<10} {'Name':<30} {'Zählpunkt':<38} {'Erzeugt':>9} {'Übersch.':>9} {'Geliefert':>10} {'Gutschr. €':>11}")
    print(f"  {'-'*120}")

    total_geliefert = 0
    total_eur = 0
    monat_summen = {}

    for periode, zp, erzeugung_tf, ueberschuss in rows:
        geliefert = erzeugung_tf - ueberschuss
        if geliefert < 0:
            geliefert = 0
        betrag = geliefert * PREIS_ERZEUGUNG / 100.0
        total_geliefert += geliefert
        total_eur += betrag
        m_key = periode[:7]
        if m_key not in monat_summen:
            monat_summen[m_key] = {"kwh": 0, "eur": 0}
        monat_summen[m_key]["kwh"] += geliefert
        monat_summen[m_key]["eur"] += betrag
        name = names.get(zp, '?')
        print(f"  {periode[:7]:<10} {name:<30} {zp:<38} {erzeugung_tf:>9.3f} {ueberschuss:>9.3f} {geliefert:>10.3f} {betrag:>11.2f}")

    print(f"  {'-'*120}")
    for m_key in sorted(monat_summen):
        s = monat_summen[m_key]
        print(f"  {'Summe ' + m_key:<90} {s['kwh']:>10.3f} {s['eur']:>11.2f}")
    print(f"  {'='*120}")
    print(f"  {'GESAMT':<90} {total_geliefert:>10.3f} {total_eur:>11.2f}")

    return total_geliefert, total_eur


def eeg_bilanz(conn, monat=None):
    """EEG-Bilanz: Einnahmen - Ausgaben = Marge."""
    where = f"AND b.period_start = '{monat}'" if monat else ""

    # Einnahmen: Verbraucher zahlen für G.03 (Eigendeckung = tatsächlich bezogen)
    einnahmen_row = conn.execute(f"""
        SELECT COALESCE(ROUND(SUM(m.value_kwh), 3), 0)
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE mc.code = '1-1:2.9.0 G.03'
        {where}
    """).fetchone()
    verbrauch_kwh = einnahmen_row[0] or 0

    # Ausgaben: Erzeuger bekommen Gutschrift für (G.01T - P.01T)
    ausgaben_row = conn.execute(f"""
        SELECT
            COALESCE(ROUND(SUM(CASE WHEN mc.code = '1-1:2.9.0 G.01T'
                       THEN m.value_kwh ELSE 0 END), 3), 0),
            COALESCE(ROUND(SUM(CASE WHEN mc.code = '1-1:2.9.0 P.01T'
                       THEN m.value_kwh ELSE 0 END), 3), 0)
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN metering_points mp ON mp.metering_point_id = m.metering_point_id
        WHERE mp.energy_direction = 'GENERATION'
          AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
        {where}
    """).fetchone()
    erzeugung_tf = ausgaben_row[0] or 0
    ueberschuss = ausgaben_row[1] or 0
    geliefert_kwh = erzeugung_tf - ueberschuss

    einnahmen_eur = verbrauch_kwh * PREIS_VERBRAUCH / 100.0
    ausgaben_eur = geliefert_kwh * PREIS_ERZEUGUNG / 100.0
    marge_eur = einnahmen_eur - ausgaben_eur

    # Balance-Check
    diff = abs(verbrauch_kwh - geliefert_kwh)
    balance_ok = diff < 0.01

    print(f"\n{'='*60}")
    print(f"  EEG-BILANZ (nur tatsächlich gehandelte Energie)")
    print(f"{'='*60}")
    print(f"  Eigendeckung (G.03) gesamt:  {verbrauch_kwh:>12.3f} kWh")
    print(f"  Lieferung (G.01T-P.01T):     {geliefert_kwh:>12.3f} kWh")
    print(f"  Balance-Check:               {'✓ OK' if balance_ok else f'✗ Differenz {diff:.3f} kWh!'}")
    print(f"")
    print(f"  Einnahmen (Verbraucher, {PREIS_VERBRAUCH:.0f} ct): {einnahmen_eur:>10.2f} €")
    print(f"  Ausgaben  (Erzeuger, {PREIS_ERZEUGUNG:.0f} ct):    {ausgaben_eur:>10.2f} €")
    print(f"  {'─'*40}")
    print(f"  EEG-Marge ({MARGE_EEG:.0f} ct/kWh):          {marge_eur:>10.2f} €")

    return einnahmen_eur, ausgaben_eur, marge_eur


def abrechnung_monatlich(conn):
    """Aufschlüsselung pro Monat."""
    monate = conn.execute("""
        SELECT DISTINCT period_start FROM import_batches ORDER BY period_start
    """).fetchall()

    print(f"\n{'='*60}")
    print(f"  MONATSÜBERSICHT EEG (gehandelte Energie)")
    print(f"{'='*60}")
    print(f"  {'Monat':<10} {'kWh gehandelt':>14} {'Einnahmen €':>12} {'Ausgaben €':>12} {'Marge €':>10}")
    print(f"  {'-'*62}")

    gesamt_kwh = 0
    gesamt_ein = 0
    gesamt_aus = 0

    for (monat,) in monate:
        # Gehandelte Energie = G.03 (Eigendeckung)
        r = conn.execute("""
            SELECT COALESCE(ROUND(SUM(m.value_kwh), 3), 0)
            FROM measurements m
            JOIN import_batches b ON b.id = m.batch_id
            JOIN meter_codes mc ON mc.id = m.meter_code_id
            WHERE mc.code = '1-1:2.9.0 G.03' AND b.period_start = ?
        """, (monat,)).fetchone()
        kwh = r[0] or 0
        einnahmen = kwh * PREIS_VERBRAUCH / 100.0
        ausgaben = kwh * PREIS_ERZEUGUNG / 100.0
        marge = kwh * MARGE_EEG / 100.0

        gesamt_kwh += kwh
        gesamt_ein += einnahmen
        gesamt_aus += ausgaben

        print(f"  {monat[:7]:<10} {kwh:>14.3f} {einnahmen:>12.2f} {ausgaben:>12.2f} {marge:>10.2f}")

    print(f"  {'-'*62}")
    print(f"  {'GESAMT':<10} {gesamt_kwh:>14.3f} {gesamt_ein:>12.2f} {gesamt_aus:>12.2f} {gesamt_ein - gesamt_aus:>10.2f}")


def abrechnung_mitglied(conn, monat=None):
    """Einzelabrechnung pro Mitglied (Verbraucher UND Erzeuger)."""
    where_ts = f"AND b.period_start = '{monat}'" if monat else ""

    # Alle Mitglieder (Metering Points)
    mitglieder = conn.execute("""
        SELECT metering_point_id, energy_direction
        FROM metering_points
        ORDER BY energy_direction, metering_point_id
    """).fetchall()

    print(f"\n{'='*78}")
    print(f"  EINZELABRECHNUNG PRO MITGLIED")
    if monat:
        print(f"  Zeitraum: {monat[:7]}")
    else:
        print(f"  Zeitraum: Alle importierten Monate")
    print(f"{'='*78}")

    names = load_member_names(conn)
    gesamt_forderung = 0
    gesamt_gutschrift = 0

    # --- VERBRAUCHER ---
    print(f"\n  {'─'*74}")
    print(f"  VERBRAUCHER (zahlen {PREIS_VERBRAUCH:.0f} ct/kWh für Eigendeckung aus EEG)")
    print(f"  {'─'*74}")

    verbraucher_rows = conn.execute(f"""
        SELECT
            m.metering_point_id,
            b.period_start,
            ROUND(SUM(CASE WHEN mc.code = '1-1:1.9.0 G.01T'
                       THEN m.value_kwh ELSE 0 END), 3) as verbrauch_gesamt,
            ROUND(SUM(CASE WHEN mc.code = '1-1:2.9.0 G.03'
                       THEN m.value_kwh ELSE 0 END), 3) as eigendeckung,
            ROUND(SUM(CASE WHEN mc.code = '1-1:1.9.0 G.02'
                       THEN m.value_kwh ELSE 0 END), 3) as zuteilung
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN metering_points mp ON mp.metering_point_id = m.metering_point_id
        WHERE mp.energy_direction = 'CONSUMPTION'
        {where_ts}
        GROUP BY m.metering_point_id, b.period_start
        ORDER BY m.metering_point_id, b.period_start
    """).fetchall()

    current_zp = None
    zp_total_kwh = 0
    zp_total_eur = 0

    for zp, periode, verbrauch, eigendeckung, zuteilung in verbraucher_rows:
        if zp != current_zp:
            if current_zp is not None:
                print(f"    {'SUMME':<12} {'':<44} {zp_total_kwh:>8.3f} {zp_total_eur:>9.2f}")
                print()
                gesamt_forderung += zp_total_eur
            current_zp = zp
            zp_total_kwh = 0
            zp_total_eur = 0
            name = names.get(zp, '?')
            print(f"  {name} ({zp})")
            print(f"    {'Monat':<12} {'Verbrauch kWh':>14} {'Zuteilung kWh':>14} {'Eigendeckung':>13} {'Betrag €':>9}")
            print(f"    {'-'*66}")

        betrag = eigendeckung * PREIS_VERBRAUCH / 100.0
        zp_total_kwh += eigendeckung
        zp_total_eur += betrag
        deckungsgrad = (eigendeckung / verbrauch * 100) if verbrauch > 0 else 0
        print(f"    {periode[:7]:<12} {verbrauch:>14.3f} {zuteilung:>14.3f} {eigendeckung:>13.3f} {betrag:>9.2f}")

    if current_zp is not None:
        print(f"    {'SUMME':<12} {'':<44} {zp_total_kwh:>8.3f} {zp_total_eur:>9.2f}")
        gesamt_forderung += zp_total_eur

    # --- ERZEUGER ---
    print(f"\n  {'─'*74}")
    print(f"  ERZEUGER (erhalten {PREIS_ERZEUGUNG:.0f} ct/kWh für Lieferung an EEG)")
    print(f"  {'─'*74}")

    erzeuger_rows = conn.execute(f"""
        SELECT
            m.metering_point_id,
            b.period_start,
            ROUND(SUM(CASE WHEN mc.code = '1-1:2.9.0 G.01T'
                       THEN m.value_kwh ELSE 0 END), 3) as erzeugung_tf,
            ROUND(SUM(CASE WHEN mc.code = '1-1:2.9.0 P.01T'
                       THEN m.value_kwh ELSE 0 END), 3) as ueberschuss
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN metering_points mp ON mp.metering_point_id = m.metering_point_id
        WHERE mp.energy_direction = 'GENERATION'
          AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
        {where_ts}
        GROUP BY m.metering_point_id, b.period_start
        ORDER BY m.metering_point_id, b.period_start
    """).fetchall()

    current_zp = None
    zp_total_kwh = 0
    zp_total_eur = 0

    for zp, periode, erzeugung_tf, ueberschuss in erzeuger_rows:
        if zp != current_zp:
            if current_zp is not None:
                print(f"    {'SUMME':<12} {'':<30} {zp_total_kwh:>10.3f} {zp_total_eur:>11.2f}")
                print()
                gesamt_gutschrift += zp_total_eur
            current_zp = zp
            zp_total_kwh = 0
            zp_total_eur = 0
            name = names.get(zp, '?')
            print(f"  {name} ({zp})")
            print(f"    {'Monat':<12} {'Erzeugt kWh':>12} {'Überschuss':>11} {'Geliefert':>10} {'Gutschrift €':>11}")
            print(f"    {'-'*60}")

        geliefert = max(0, erzeugung_tf - ueberschuss)
        betrag = geliefert * PREIS_ERZEUGUNG / 100.0
        zp_total_kwh += geliefert
        zp_total_eur += betrag
        print(f"    {periode[:7]:<12} {erzeugung_tf:>12.3f} {ueberschuss:>11.3f} {geliefert:>10.3f} {betrag:>11.2f}")

    if current_zp is not None:
        print(f"    {'SUMME':<12} {'':<30} {zp_total_kwh:>10.3f} {zp_total_eur:>11.2f}")
        gesamt_gutschrift += zp_total_eur

    # Zusammenfassung
    print(f"\n  {'='*74}")
    print(f"  ZUSAMMENFASSUNG")
    print(f"  {'='*74}")
    print(f"  Forderungen an Verbraucher:   {gesamt_forderung:>10.2f} €")
    print(f"  Gutschriften an Erzeuger:     {gesamt_gutschrift:>10.2f} €")
    print(f"  {'─'*40}")
    print(f"  EEG-Ertrag (Differenz):       {gesamt_forderung - gesamt_gutschrift:>10.2f} €")


def main():
    if not os.path.exists(DB_PATH):
        print(f"Datenbank '{DB_PATH}' nicht gefunden.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    monat = None
    if len(sys.argv) > 1:
        monat = sys.argv[1]  # z.B. "2026-01" oder "2026-01-01"
        if len(monat) == 7:
            monat = monat + "-01T00:00:00"
        elif len(monat) == 10:
            monat = monat + "T00:00:00"
        print(f"  Filter: Monat {monat[:7]}")

    abrechnung_monatlich(conn)
    abrechnung_mitglied(conn, monat)
    eeg_bilanz(conn, monat)

    conn.close()


if __name__ == "__main__":
    main()
