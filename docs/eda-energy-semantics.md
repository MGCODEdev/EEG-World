# Fachmatrix historische EEG-Energiedaten

Stand: 2026-08-07

Diese Matrix ist die verbindliche technische Grundlage fuer neue historische
Auswertungen. Sie beschreibt ausschliesslich abgeschlossene Energieintervalle.
Keine der Reihen ist ein Live-Wert oder eine momentane Leistung.

## Gelieferte Reihen

| MeterCode | Richtung | Bedeutung | Verwendung |
| --- | --- | --- | --- |
| `1-1:1.9.0 G.01` | Verbrauch | Verbrauch laut Messung | Gemessener Gesamtverbrauch des Intervalls |
| `1-1:1.9.0 G.01T` | Verbrauch | Verbrauch entsprechend Teilnahmefaktor | Nur mit explizit ausgewiesener Teilnahmefaktor-Logik verwenden |
| `1-1:2.9.0 G.03` | Verbrauchszaehlpunkt | Eigendeckung | Innerhalb der EEG gedeckter Anteil des gemessenen Verbrauchs |
| `1-1:2.9.0 G.03R` | Verbrauchszaehlpunkt | Erneuerbare Eigendeckung | Erneuerbarer Anteil der Eigendeckung |
| `1-1:2.9.0 G.01` | Erzeugung | Erzeugung laut Messung | Gemessene Erzeugung des Intervalls |
| `1-1:2.9.0 G.01T` | Erzeugung | Erzeugung entsprechend Teilnahmefaktor | Fuer die EG beruecksichtigte Erzeugung |
| `1-1:2.9.0 P.01T` | Erzeugung | Restnetzauspeisung | Nach der EG-Zuteilung verbleibende Einspeisung |

`G.02` wird importiert, aber bis zur abschliessenden Abstimmung des konkreten
EDA-Reportprofils nicht fuer neue abgeleitete Kennzahlen verwendet. Die in den
vorhandenen Dateien vorkommenden deutschen Bezeichnungen und Richtungen muessen
vor einer Verwendung gegen die jeweilige Prozessversion validiert werden.

## Zulaessige Ableitungen

Alle Operanden muessen denselben Zaehlpunkt, dasselbe Intervall und dieselbe
aktive Importrevision betreffen.

```text
Restnetzbezug = gemessener Verbrauch G.01 - Eigendeckung G.03

Lieferung an die EEG = Erzeugung nach Teilnahmefaktor G.01T
                       - Restnetzauspeisung P.01T

Eigenversorgungsgrad = Eigendeckung G.03 / gemessener Verbrauch G.01 * 100

Durchschnittliche Intervallleistung in kW
    = Energie in kWh / (Intervallminuten / 60)
```

## Verbindliche Darstellung in der Mitglieder-App

Die API und die iOS-App verwenden zwei voneinander getrennte, geschlossene
Bilanzen. Damit sind Summen, Prozentwerte und Farben in jeder Ansicht gleich:

```text
Verbrauch gesamt = EEG-Eigendeckung + verbleibender Netzbezug

Beruecksichtigte Erzeugung = Lieferung an die EEG + Restnetzeinspeisung
```

Der EEG-Anteil wird immer auf die jeweilige Bilanz bezogen. Ein direkter
PV-Fluss vom eigenen Dach in den Haushalt wird nicht dargestellt, weil er aus
den hier verfügbaren EDA-Reihen nicht verlaesslich ableitbar ist. Die
Tagesansicht summiert Viertelstundenwerte in Stundenbloecke; sie zeigt Energie
in kWh und keine vermeintliche Live-Leistung.

Eine Differenz darf nicht still auf null gekappt werden. Wenn ein Teilwert
groesser als sein Gesamtwert ist, ist das Ergebnis fachlich ungueltig und muss
als Datenqualitaetsfehler ausgewiesen werden.

## Nicht zulaessig

- `G.01 + G.03` als Gesamtverbrauch
- Bezeichnungen wie "Live", "Echtzeit" oder "momentane Leistung"
- Addition von Werten verschiedener Importrevisionen
- Ersetzen fehlender Intervalle durch erfundene Nullwerte
- Verwendung von `G.02` ohne freigegebene Semantik des konkreten Reportprofils
- pauschale Annahme von 96 Intervallen pro Kalendertag

## Qualitaet

- `L1`: Echtwert
- `L2`: belastbarer Ersatzwert
- `L3`: nicht belastbarer Ersatzwert

L2 und L3 bleiben in Summen enthalten, werden aber in API und Oberflaeche
sichtbar als Ersatzwerte ausgewiesen. Fehlende Werte werden nicht interpoliert,
sofern eine Auswertung nicht ausdruecklich und sichtbar als Schaetzung
gekennzeichnet wird.
