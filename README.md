# EEG Energiedaten Import & Auswertung

Import- und Web-Tool für EDA-Energiedatenreports (Excel) aus dem österreichischen
EDA-Anwenderportal in eine SQLite-Datenbank für Abrechnung, Auswertung und Mitgliederportal.

Dieses Repository enthält nur den Source-Code. Produktivdaten wie SQLite-Datenbank,
Excel-Importe, Rechnungs-PDFs, Verträge, Logs und lokale Secrets sind per `.gitignore`
ausgeschlossen.

## Basis-Standard

- **Prozess:** CR_MSG (03.20) – Versenden der Energiedaten
- **Marktnachricht:** DATEN_CRMSG
- **Schema:** ConsumptionRecord 1.41 (ebUtilities)
- **MeterCodes:** gemäß [13122023_MeterCodes_CR_MSG.pdf](https://www.ebutilities.at/documents/2023/12/13122023_MeterCodes_CR_MSG.pdf)
- **Qualitätskennzeichen:** L1 (Echtwert), L2 (Ersatzwert belastbar), L3 (Ersatzwert nicht belastbar)

## Quickstart

```bash
cd /var/www/eeg
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 1. Excel-Dateien ablegen
cp ~/Downloads/RC107032_*.xlsx data/

# 2. Import starten
python3 import_eda.py

# 3. Auswertung/Reports
python3 reports.py
```

## Webapp wiederherstellen

```bash
git clone https://github.com/MGCODEdev/EEG-World.git
cd EEG-World
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Danach in `.env` mindestens setzen:

- `EEG_SECRET_KEY`
- `EEG_INITIAL_ADMIN_PASSWORD` für die erste Admin-Anlage
- Organisationsdaten (`EEG_ORG_NAME`, `EEG_ORG_EMAIL`, ...)

Produktiv sollte die App hinter einem Reverse Proxy mit HTTPS laufen. Der direkte
Flask-Start bindet standardmäßig nur an `127.0.0.1`.

## Google Drive Backup

Die Backup-Seite kann lokale ZIP-Backups zusätzlich nach Google Drive kopieren.
Dafür wird OAuth verwendet; Google-Passwörter werden nicht in der App gespeichert.

1. In der Google Cloud Console ein OAuth-Client vom Typ Webanwendung erstellen.
2. Als Redirect-URI eintragen: `https://deine-domain.example/admin/backup/google/callback`
3. In der App unter **Backup** die Client-JSON hochladen oder einfügen.
4. Danach unter **Backup** auf **Google verbinden** klicken, damit das OAuth-Token lokal gespeichert wird.

Optional können feste Speicherpfade in `.env` gesetzt werden:

```bash
EEG_GOOGLE_CLIENT_SECRETS=/var/www/eeg/instance/google_client_secret.json
EEG_GOOGLE_TOKEN_FILE=/var/www/eeg/instance/google_drive_token.json
EEG_GOOGLE_OAUTH_REDIRECT_URI=https://deine-domain.example/admin/backup/google/callback
```

`instance/` ist vom Git-Repository ausgeschlossen.
Für dauerhafte automatische Backups sollte der OAuth-Zustimmungsbildschirm in
Google Cloud auf **In production** stehen; im Testmodus können Refresh-Tokens
nach kurzer Zeit ablaufen. Die Backup-Seite enthält einen Button
**Drive-Verbindung prüfen**, der Token-Refresh und Drive-API-Zugriff testet.

## Dateistruktur

```
/var/www/eeg/
├── schema.sql        # DB-Schema (SQLite)
├── import_eda.py     # Importer für EDA-Excel-Reports
├── reports.py        # Abrechnungs- und Auswertungsreports
├── requirements.txt  # Python-Dependencies
├── eeg_data.db       # SQLite-Datenbank (lokal, nicht im Git)
├── data/             # Excel-Dateien lokal hierher kopieren (nicht im Git)
└── README.md
```

## Datenbank-Schema

| Tabelle | Zweck |
|---------|-------|
| `import_batches` | Jeder Import-Lauf mit Datei, Zeitraum, Metadaten |
| `metering_points` | Zählpunkte mit Richtung (CONSUMPTION/GENERATION) |
| `meter_codes` | OBIS/MeterCodes mit deutscher Bezeichnung |
| `measurements` | Viertelstundenwerte (Kern-Tabelle) |
| `overview_totals` | Summen aus Übersichts-Blatt für Plausibilität |

## OBIS-Codes / MeterCodes (EG-relevant)

| Code | Suffix | Bezeichnung | Richtung |
|------|--------|-------------|----------|
| 1-1:1.9.0 G.01 | G.01 | Gesamtverbrauch lt. Messung | CONSUMPTION |
| 1-1:1.9.0 G.01T | G.01T | Verbrauch nach Teilnahmefaktor | CONSUMPTION |
| 1-1:1.9.0 G.02 | G.02 | Bezug aus Gemeinschaft | CONSUMPTION |
| 1-1:2.9.0 G.01 | G.01 | Gesamterzeugung lt. Messung | GENERATION |
| 1-1:2.9.0 G.01T | G.01T | Erzeugung nach Teilnahmefaktor | GENERATION |
| 1-1:2.9.0 G.02 | G.02 | Anteil an der Erzeugung | GENERATION |
| 1-1:2.9.0 G.03 | G.03 | Eigendeckung | GENERATION |
| 1-1:2.9.0 G.03R | G.03R | Eigendeckung erneuerbar | GENERATION |
| 1-1:2.9.0 P.01T | P.01T | Restüberschuss bei EG | GENERATION |

## Abrechnung

Für die innergemeinschaftliche Abrechnung relevant:

- **Verbraucher:** `G.01T` (Verbrauch nach TF) minus `G.02` (Bezug aus EG) = Restnetzbezug
- **Erzeuger:** `G.01T` (Erzeugung nach TF) minus `P.01T` (Restüberschuss) = an EG geliefert

## Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `EEG_DB_PATH` | `eeg_data.db` | Pfad zur SQLite-Datenbank |
| `EEG_DATA_DIR` | `data` | Verzeichnis mit Excel-Dateien |

## Quellen

- [ebUtilities Prozess CR_MSG](https://www.ebutilities.at/prozesse/557)
- [ConsumptionRecord Schema 01.41](https://www.ebutilities.at/schemas/240)
- [XSD-Definition](https://www.ebutilities.at/schemata/customerprocesses/consumptionrecord/01p41/ConsumptionRecord_01p41.xsd)
- [MeterCodes CR_MSG (PDF)](https://www.ebutilities.at/documents/2023/12/13122023_MeterCodes_CR_MSG.pdf)
