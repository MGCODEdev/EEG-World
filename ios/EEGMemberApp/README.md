# EEG Mitglieder-App für iOS

Native SwiftUI-App für Mitglieder der EEG Trabocherstraße. Die App verwendet
die versionierte Flask-API unter `/api/v1`; sämtliche Energie- und
Abrechnungsberechnungen bleiben im Backend.

## Sichere App-Verbindung

Mitglieder können sich per E-Mail-Magic-Link, zehn Minuten gültigem Einmalcode,
Admin-QR-Code oder weiterhin per Passwort verbinden. Einmalcodes und Link-Token
liegen im Backend nur als SHA-256-Hash vor. Ausgestellte Sitzungen sind an eine
zufällige, nur im iOS-Keychain gespeicherte Installations-ID gebunden.

Für Universal Links verwendet das Backend die Apple Developer Team-ID
`LQFUQM34Z5` und die vollständige App-ID
`LQFUQM34Z5.at.eeg.trabocherstrasse.member`. Das Associated-Domains-Entitlement
nutzt `applinks:admin.eeg-trabocherstrasse.at`; der Magic-Link-Pfad lautet
`/mobile-connect`.

## Voraussetzungen

- macOS mit aktuellem Xcode
- iOS 17 oder neuer
- XcodeGen (`brew install xcodegen`)
- öffentlich gültiges HTTPS-Zertifikat für die API-Domain

## Projekt erzeugen

```bash
cd ios/EEGMemberApp
xcodegen generate
open EEGMemberApp.xcodeproj
```

Danach in Xcode unter **Signing & Capabilities** das eigene Development Team
auswählen. Die API-Basisadresse steht als `API_BASE_URL` in `project.yml`.

## Kamera und Dateiauswahl testen

Die Funktion „Kamera“ verwendet ausschließlich die echte iPhone-Kamera und
prüft die iOS-Berechtigung vor dem Öffnen. Der iOS-Simulator besitzt keine
Kamera und zeigt deshalb bewusst eine Hinweismeldung. „Datei“ verwendet einen
`UIDocumentPickerViewController`; „Fotos“ bleibt davon getrennt und verwendet
den Apple-Fotopicker.

Meldet ein Simulator `NSOSStatusErrorDomain Code=-54` oder `process may not map
database`, ist dessen LaunchServices-Datenbank beschädigt oder gesperrt. In
diesem Fall die App löschen, den Simulator neu starten und gegebenenfalls über
**Device → Erase All Content and Settings…** zurücksetzen. Die Kamera muss
abschließend auf einem echten iPhone geprüft werden.

## Kamera und Dateiauswahl testen

Die Funktion „Kamera“ verwendet ausschließlich die echte iPhone-Kamera und
prüft die iOS-Berechtigung vor dem Öffnen. Der iOS-Simulator besitzt keine
Kamera und zeigt deshalb bewusst eine Hinweismeldung. „Datei“ verwendet einen
`UIDocumentPickerViewController`; „Fotos“ bleibt davon getrennt und verwendet
den Apple-Fotopicker.

Meldet ein Simulator `NSOSStatusErrorDomain Code=-54` oder `process may not map
database`, ist dessen LaunchServices-Datenbank beschädigt oder gesperrt. In
diesem Fall die App löschen, den Simulator neu starten und gegebenenfalls über
**Device → Erase All Content and Settings…** zurücksetzen. Die Kamera muss
abschließend auf einem echten iPhone geprüft werden.

## Enthaltene native Funktionen

- Login mit widerrufbaren Access-/Refresh-Tokens
- sichere Token-Speicherung in der iOS-Keychain
- Navigation mit Übersicht, Energie und Mein Konto
- deutlich sichtbarer Datenstand mit letztem Import und Hinweis „Keine Live-Daten“
- geschützter Offline-Cache der zuletzt geladenen Übersicht
- historische Auswahl nach Tag, Woche, Monat und Jahr sowie nach eigenem Zählpunkt
- kompakter Tagesverlauf in Stundenblöcken sowie Wochen-, Monats- und Jahresverläufe
- kompakte Start- und Energieansicht mit vier Kernwerten; Datenstand und Zusatzwerte sind platzsparend aufrufbar
- interaktive D3-Donuts mit räumlicher Tiefe für zwei geschlossene Bilanzen: Verbrauch aus EEG/Netz sowie Einspeisung an EEG/öffentliches Netz
- freie Auswahl von Tag, Monat oder Jahr auf der Startseite und Umschaltung zwischen kWh und geschätzten Eurobeträgen
- interaktive, gestapelte D3-Balken; am Tag stündlich, für Woche/Monat täglich und für das Jahr monatlich
- identische Begriffe, Farben und Berechnungen auf Start- und Energieansicht
- Profilfoto-Auswahl direkt unter „Meine Daten“; das Bild wird serverseitig gespeichert und automatisch im Mitgliedsausweis verwendet
- getrennte Darstellung von EEG-Eigendeckung und verbleibendem Netzbezug
- Face-ID-/Gerätecode-Schutz beim erneuten Öffnen
- geschützte PDF-Vorschau für Abrechnungen und Verträge
- Teilen, Drucken und Speichern von PDFs über das iOS-Teilen-Menü
- Kontoverlauf
- hochwertiger, animierter Mitgliedsausweis mit servergespeichertem Profilfoto, Vorder-/Rückseite, Vereins- und ZVR-Daten, Adresse, Gültigkeit, Rollen, Zählpunkten und Vertragsübersicht
- roter, durchgestrichener Ausweisstatus für inaktive Mitgliederdaten; inaktive Konten bleiben serverseitig vom App-Zugriff ausgeschlossen
- eigener Strompreis-Reiter mit aktuellem EEG-Tarif, früheren Tarifen und interaktivem D3-Preisverlauf für 3, 6, 12 Monate oder den gesamten Datenbestand
- sichere Nachricht an die EEG mit Text, bis zu fünf Fotos/PDFs sowie automatisch beigefügtem aktuellem Standort und serverseitig erfasster Verbindungs-IP; die Standortberechtigung wird erst beim Senden angefragt
- geschützte Admin-Inbox im Webportal und individuell aktivierbare E-Mail-Benachrichtigung für Administratoren
- gemeinsamer Dokumentenbereich für Abrechnungen und Verträge
- Profil und Newsletter-Einstellung
- Apple Push Notifications mit eigenem EEG-Klang, Badge, Kategorien und Deep-Link-Grundlage
- persönliche Einstellungen für Abrechnungs- und Gemeinschaftsmitteilungen

## Push Notifications aktivieren

Für produktive Push-Mitteilungen ist ein kostenpflichtiges Apple Developer
Program erforderlich. Im Apple Developer Portal einen APNs-Schlüssel (`.p8`)
erzeugen und diese Variablen für Webapp und Push-Worker setzen:

```text
EEG_APNS_KEY_PATH=/sicherer/pfad/AuthKey_ABC123.p8
EEG_APNS_KEY_ID=ABC123
EEG_APNS_TEAM_ID=DEINTEAMID # optional, EEG_APPLE_TEAM_ID wird ebenfalls verwendet
EEG_APNS_BUNDLE_ID=at.eeg.trabocherstrasse.member
```

`webapp/push_worker.py` verarbeitet eine Charge aus der dauerhaften Outbox.
Er sollte per systemd-Timer jede Minute ausgeführt werden. Debug-Builds aus
Xcode verwenden APNs Sandbox, TestFlight-/App-Store-Builds Produktion.

Der originale, 1,18 Sekunden lange Klang `eeg-notification.caf` liegt im
App-Bundle und kann im Profil über „EEG-Ton testen“ angehört werden. Er wird
nur abgespielt, sofern der Benutzer Töne erlaubt und kein Fokus-/Lautlosmodus
dies verhindert.

## Lokales D3-Diagramm

Die Bilanz- und Verlaufsdiagramme laden keine Inhalte aus dem Internet. D3 wird
beim Entwickeln gebündelt und als lokale JavaScript-Datei in
die App aufgenommen. Nach Änderungen an den Dateien unter `ChartAssets` werden
die Bundles so neu erzeugt:

```bash
cd ios/EEGMemberApp/ChartAssets
npm install
npm run build
```

Die verwendete D3-Version ist in `ChartAssets/package.json` festgeschrieben.
Der erforderliche ISC-Lizenzhinweis liegt unter
`EEGMemberApp/Resources/ThirdPartyLicenses` im App-Bundle.
