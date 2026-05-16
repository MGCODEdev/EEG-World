# EEG Portal - Programmbeschreibung und Sicherheitspruefung

Stand: 2026-05-16

## 0. Umgesetzte Haertungen

Nach der Sicherheitspruefung wurden folgende Punkte im Code umgesetzt:

- Produktivbetrieb verlangt `EEG_SECRET_KEY`; ohne gesetzten Key wird nur im Nicht-Produktivmodus ein temporaerer Key erzeugt.
- Session-Cookies sind gehaertet: `HttpOnly`, `SameSite=Lax`, und `Secure` im Produktivmodus.
- Der direkte Flask-Start bindet standardmaessig nur noch an `127.0.0.1`; Host/Port sind ueber `EEG_HOST` und `EEG_PORT` steuerbar.
- `debug=True` wurde entfernt; Debug ist nur noch mit `FLASK_DEBUG=1` aktivierbar.
- Neue Admin-Passwoerter werden nicht mehr fest im Code gesetzt. Fuer neue Admins kann `EEG_INITIAL_ADMIN_PASSWORD` genutzt werden; im Produktivmodus ist diese Variable fuer Erstanlage verpflichtend.
- Login-Weiterleitung ueber `next` erlaubt nur noch relative oder gleiche Host-Ziele.
- Newsletter-HTML wird serverseitig ueber eine Allowlist bereinigt.
- ZIP-Restore extrahiert Dateien nur noch nach Pfadnormalisierung in erlaubte Zielverzeichnisse.
- Vertragsupload erlaubt nur noch PDF-Dateien mit PDF-Signatur.
- SMTP-Passwoerter werden im Settings-Formular nicht mehr ausgegeben; leeres Passwortfeld behaelt das gespeicherte Passwort bei.
- Optionaler Laenderblock ist ueber `EEG_ALLOWED_COUNTRIES=AT` aktivierbar, wenn ein Reverse Proxy oder Cloudflare den Header `CF-IPCountry` oder `X-Country-Code` setzt.

## 1. Zweck des Programms

Die Anwendung verwaltet Energiedaten, Mitglieder, Preise, Abrechnungen und Newsletter fuer eine Energiegemeinschaft. Sie importiert EDA-Energiedatenreports als Excel-Dateien, speichert Viertelstundenwerte in SQLite, berechnet Abrechnungen fuer Verbraucher und Erzeuger und stellt ein Webportal fuer Administratoren und Mitglieder bereit.

## 2. Hauptbestandteile

### Webanwendung

Datei: `webapp/app.py`

Die Webanwendung basiert auf Flask und stellt folgende Bereiche bereit:

- Login, Logout, Passwortaenderung und Einladungslinks
- Admin-Dashboard mit Import- und Monatsuebersicht
- Excel-Import fuer EDA-Dateien
- Mitgliederverwaltung inklusive Kontaktdaten, Bankdaten, Zaehlerpunkten und Aktivstatus
- Preisverwaltung fuer Abrechnungsperioden
- Abrechnungserstellung, Neuberechnung, PDF-Erzeugung und E-Mail-Versand
- Zahlungsuebersicht fuer offene und gebuchte Forderungen/Gutschriften
- Benutzerverwaltung mit Admin- und Mitgliederrollen
- Vertragsupload und Vertragsdownload
- Mitgliederportal fuer eigene Daten, eigene Abrechnungen und eigene Vertraege
- Newsletterverwaltung mit Vorschau, Testversand, Versand und Abmeldelink
- Audit-Log fuer Login, Seitenaufrufe und Verwaltungsaktionen
- Backup-Download und Backup-Restore

### Importer

Datei: `import_eda.py`

Der Importer liest EDA-Excel-Reports mit `openpyxl`. Er erkennt Zaehlerpunkte, Energierichtung, MeterCode-Labels, Viertelstundenwerte und Qualitaetskennzeichen. Die Werte werden in die Tabellen `import_batches`, `metering_points`, `meter_codes` und `measurements` geschrieben.

### Konsolenabrechnung

Datei: `abrechnung.py`

Dieses Skript erzeugt textbasierte Abrechnungsuebersichten. Es berechnet Forderungen fuer Verbraucher auf Basis von `G.03` und Gutschriften fuer Erzeuger auf Basis von `G.01T - P.01T`.

### Reports

Datei: `reports.py`

Dieses Skript erzeugt tabellarische Auswertungen fuer Monatssummen, Abrechnungsgrundlagen, Erzeugung, Datenqualitaet und Vollstaendigkeit.

### Datenbank

Dateien: `schema.sql`, `webapp/schema_web.sql`, `eeg_data.db`

Die Anwendung nutzt SQLite. Kernbereiche:

- Importdaten: `import_batches`, `metering_points`, `meter_codes`, `measurements`, `overview_totals`
- Webdaten: `users`, `members`, `prices`, `invoices`, `invoice_items`, `email_log`, `import_log`
- Laufzeit-/Erweiterungstabellen: `settings`, `contracts`, `audit_log`, `newsletters`, `newsletter_log`

## 3. Programmablauf

1. EDA-Excel-Dateien werden im Web hochgeladen oder im `data/`-Verzeichnis abgelegt.
2. Der Importer liest die Dateien und speichert die Messwerte in SQLite.
3. Administratoren pflegen Mitglieder, Zaehlerpunkte und Preise.
4. Fuer einen Zeitraum wird eine Abrechnung erstellt.
5. Die Abrechnung berechnet Verbrauchspositionen und Erzeugungsgutschriften je Mitglied.
6. PDFs werden aus HTML-Templates mit WeasyPrint erzeugt.
7. Rechnungen koennen per SMTP versendet und im E-Mail-Log protokolliert werden.
8. Mitglieder koennen sich einloggen, eigene Stammdaten pflegen, eigene Rechnungen herunterladen und eigene Vertraege ansehen.
9. Admins koennen Newsletter erstellen, testen und an aktive Mitglieder versenden.
10. Das Audit-Log protokolliert relevante Aktionen.

## 4. Rollen und Berechtigungen

Die Anwendung unterscheidet zwischen:

- Admin: Zugriff auf Dashboard, Import, Mitglieder, Preise, Abrechnungen, Zahlungen, Reports, Newsletter, Einstellungen, Benutzerverwaltung, Audit-Log, Backup und alle Vertraege.
- Mitglied: Zugriff auf das eigene Portal, eigene Stammdaten, eigene Abrechnungen und eigene Vertraege.

Die meisten Admin-Routen sind mit `@admin_required` geschuetzt. Mitgliederzugriffe auf PDFs und Vertraege pruefen zusaetzlich, ob die angeforderte Ressource zum eingeloggten Mitglied gehoert.

## 5. Positive Sicherheitsaspekte

- CSRF-Schutz ist global aktiviert (`CSRFProtect`) und die Formulare enthalten ueberwiegend CSRF-Token.
- SQL-Abfragen nutzen in den meisten schreibenden und filternden Stellen Parameterbindung.
- Dynamische Sortierspalten im Web-Dashboard und Importbereich werden per Allowlist eingeschraenkt.
- Passwoerter werden mit `werkzeug.security.generate_password_hash` gespeichert.
- Login-Fehlversuche werden pro IP temporaer begrenzt.
- Sicherheitsheader werden gesetzt: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, Cache-Control.
- Datei-Uploads fuer Excel-Dateien verwenden `secure_filename`.
- Mitglieder duerfen fremde PDFs und Vertraege nicht herunterladen.
- Audit-Logging ist vorhanden und deckt viele sicherheitsrelevante Aktionen ab.

## 6. Urspruengliche Sicherheitsbefunde

Status: Die wichtigsten Befunde aus diesem Abschnitt wurden inzwischen umgesetzt; siehe Abschnitt 0. Einige Empfehlungen bleiben als Betriebsaufgaben bestehen, z. B. Backup-Verschluesselung, Reverse-Proxy-Konfiguration und Dependency-CVE-Pruefung.

### Kritisch: Debug-Modus im Produktivstart aktiv

Fundstelle: `webapp/app.py`, Ende der Datei: `app.run(host='0.0.0.0', port=5000, debug=True)`

Risiko: Der Flask-Debugger darf niemals in Produktion aktiv sein. Bei Fehlkonfiguration kann er sensible Informationen preisgeben oder interaktive Debug-Funktionen erreichbar machen.

Empfehlung: Debug-Modus ueber Umgebungsvariable steuern und standardmaessig deaktivieren, z. B. `debug=os.environ.get("FLASK_DEBUG") == "1"`. Produktivbetrieb ueber Gunicorn/uWSGI hinter Reverse Proxy starten.

### Kritisch: Vordefinierte Admin-Passwoerter

Fundstellen: `webapp/app.py`, `init_db()` und `_create_named_admin()`

Risiko: Neue Admin-Accounts werden mit `changeme2026` angelegt. Wenn das Passwort nicht sofort geaendert wird, ist die Anwendung direkt kompromittierbar.

Empfehlung: Keine festen Passwoerter im Code. Admin-Erstellung nur ueber einmalige Setup-Variable, zufaelliges Initialpasswort oder Einladungslink. Bestehende Accounts sofort pruefen und Passwoerter wechseln.

### Hoch: Offene Weiterleitung nach Login

Fundstelle: `webapp/app.py`, Login-Route, `next_page = request.args.get('next')` und `redirect(next_page)`

Risiko: Angreifer koennen Login-Links mit externen `next`-URLs bauen und Nutzer nach erfolgreichem Login auf fremde Seiten weiterleiten.

Empfehlung: `next` nur erlauben, wenn es relativ ist oder auf denselben Host zeigt. Alternativ immer auf Dashboard/Portal weiterleiten.

### Hoch: Newsletter-HTML wird ungefiltert als sicher gerendert

Fundstellen: `webapp/templates/newsletter_edit.html`, `webapp/templates/newsletter_email.html`, jeweils `body_html|safe`

Risiko: Gespeichertes HTML wird ohne Sanitizing ausgegeben. Da nur Admins Newsletter bearbeiten duerfen, ist das primaer ein Admin-/Supply-Chain-Risiko, kann aber zu gespeicherter XSS im Adminbereich oder in Vorschau/E-Mail fuehren.

Empfehlung: HTML serverseitig sanitizen, z. B. mit `bleach`, und nur erlaubte Tags/Attribute zulassen. Fuer E-Mails insbesondere `script`, Event-Handler, `javascript:`-URLs und unsichere externe Inhalte blockieren.

### Hoch: ZIP-Restore extrahiert Pfade aus Upload

Fundstelle: `webapp/app.py`, `backup_restore()`, `zf.extract(...)`

Risiko: ZIP-Dateien werden teilweise anhand ihrer internen Namen extrahiert. Die aktuelle Pruefung akzeptiert alle Eintraege unter `invoices/`. Ohne explizite Pfadnormalisierung besteht Risiko fuer Path Traversal oder unerwuenschte Dateischreibzugriffe, abhaengig von ZIP-Inhalten und Python-Version.

Empfehlung: ZIP-Eintraege vor dem Extrahieren strikt normalisieren und nur Dateien direkt unter erlaubten Zielpfaden schreiben. Absolute Pfade, `..`, Symlinks und verschachtelte Sonderpfade ablehnen.

### Mittel: Session- und Cookie-Haertung fehlt

Fundstelle: `webapp/app.py`, App-Konfiguration

Risiko: Es sind keine expliziten Cookie-Flags gesetzt. In Produktion sollten Session-Cookies nur ueber HTTPS laufen und gegen clientseitigen Zugriff sowie Cross-Site-Kontexte gehaertet werden.

Empfehlung: Setzen von `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'` oder je nach Bedarf `Strict`.

### Mittel: SECRET_KEY wird bei fehlender Umgebungsvariable pro Prozess neu erzeugt

Fundstelle: `webapp/app.py`, `app.config['SECRET_KEY'] = os.environ.get('EEG_SECRET_KEY', secrets.token_hex(32))`

Risiko: Wenn `EEG_SECRET_KEY` fehlt, werden Sessions und CSRF-Tokens nach jedem Neustart ungueltig. In Mehrprozess-Setups koennen Sessions inkonsistent werden.

Empfehlung: In Produktion Start abbrechen, wenn `EEG_SECRET_KEY` nicht gesetzt ist. Den Key ausserhalb des Codes sicher verwalten.

### Mittel: SMTP-Passwort wird im Klartext in SQLite gespeichert und im Settings-Formular angezeigt

Fundstellen: `settings`-Tabelle und `webapp/templates/settings.html`

Risiko: Wer Zugriff auf DB oder Admin-UI hat, kann SMTP-Zugangsdaten auslesen. Das ist besonders relevant, weil Backups die Datenbank enthalten.

Empfehlung: Secrets aus Umgebungsvariablen oder Secret Manager laden. Falls Speicherung in DB notwendig ist, Zugriff stark beschraenken, Backups verschluesseln und Formularwerte maskiert lassen.

### Mittel: Backup enthaelt personenbezogene Daten und Secrets

Fundstelle: `backup_download()`

Risiko: Das ZIP enthaelt die komplette SQLite-Datenbank inklusive Mitglieder-, Bank-, Vertrags-, SMTP- und Abrechnungsdaten sowie PDFs. Der Download ist Admin-geschuetzt, aber sehr sensibel.

Empfehlung: Backup-ZIP verschluesseln oder serverseitig nur in geschuetzte Ablage schreiben. Download und Restore besonders auditieren. Zugriff auf wenige Admins beschraenken.

### Mittel: Vertragsupload prueft keinen Dateityp

Fundstelle: `admin_contract_upload()`

Risiko: Beliebige Dateien bis 10 MB koennen als Vertrag in die Datenbank geladen und wieder heruntergeladen werden. Das ist weniger kritisch, weil Download als Attachment erfolgt, aber fuer Malware-Ablage und Speicherverbrauch riskant.

Empfehlung: Nur erwartete Typen wie PDF erlauben, MIME-Typ grob pruefen und Dateinamen/Endungen begrenzen.

### Mittel: Import akzeptiert Dateiendung case-sensitiv und prueft keinen Inhalt

Fundstelle: `import_data()`

Risiko: Dateien werden anhand von `.xlsx` akzeptiert und anschliessend von `openpyxl` geparst. Fehler werden abgefangen, aber es gibt keine Inhalts-/MIME-Pruefung.

Empfehlung: Endung case-insensitiv pruefen, MIME/Zip-Struktur validieren und Importfehler ohne Detailleak an Nutzer anzeigen.

### Niedrig: In-Memory-Login-Rate-Limit ist pro Prozess und fluechtig

Fundstelle: `_login_attempts`

Risiko: Bei Neustart oder mehreren Worker-Prozessen greift die Sperre unzuverlaessig.

Empfehlung: Rate-Limits in Redis/DB speichern oder Reverse-Proxy/WAF-Rate-Limits ergaenzen.

### Niedrig: Einige Konsolenskripte nutzen dynamische SQL-Fragmente

Fundstellen: `abrechnung.py`, `reports.py`

Risiko: In den Skripten werden optionale Filter teilweise als f-Strings in SQL eingebettet. Aktuell kommen die Werte hauptsaechlich aus CLI-Argumenten oder internen Parametern, trotzdem ist Parameterbindung robuster.

Empfehlung: Auch in Skripten konsequent SQL-Parameter verwenden.

## 7. Empfohlene Sofortmassnahmen

1. Debug-Modus deaktivieren und produktiven WSGI-Server verwenden.
2. Alle Default-Admin-Passwoerter entfernen und bestehende Admin-Passwoerter sofort aendern.
3. Offene Weiterleitung im Login schliessen.
4. Session-Cookie-Flags setzen und `EEG_SECRET_KEY` verpflichtend machen.
5. ZIP-Restore gegen Path Traversal absichern.
6. Newsletter-HTML sanitizen.
7. SMTP-Passwort aus DB/Formular entfernen oder Backups verschluesseln.

## 8. Prioritaet fuer naechste Code-Aenderungen

Empfohlene Reihenfolge:

1. `debug=True` entfernen.
2. Default-Passwoerter durch Invite-/Setup-Flow ersetzen.
3. Sichere `next`-URL-Pruefung einbauen.
4. Cookie- und Secret-Key-Konfiguration haerten.
5. Safe-ZIP-Extraction-Funktion fuer Restore schreiben.
6. Newsletter-HTML mit Allowlist sanitizen.
7. Upload-Typen fuer Vertrag und Import enger pruefen.

## 9. Einschraenkung der Pruefung

Diese Pruefung ist eine statische Code-Review auf Basis der im Arbeitsverzeichnis vorhandenen Dateien. Es wurden keine externen Penetrationstests, keine Dependency-CVE-Pruefung mit Online-Datenbank und keine Laufzeitpruefung gegen einen produktiven Server durchgefuehrt.
