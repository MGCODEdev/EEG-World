-- EDA Energiedatenreport Import Schema
-- Basierend auf CR_MSG / ConsumptionRecord 1.41 / ebUtilities
-- Optimiert für Energiegemeinschafts-Abrechnung

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    report_code TEXT,              -- z.B. RC107032
    period_start TEXT NOT NULL,    -- ISO datetime
    period_end TEXT NOT NULL,      -- ISO datetime
    energy_community_id TEXT,     -- EC-Nummer / Gemeinschafts-ID
    grid_operator TEXT,           -- Netzbetreiber
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS metering_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metering_point_id TEXT NOT NULL UNIQUE,  -- 33-stellige ZP-Nummer
    name TEXT,
    energy_direction TEXT NOT NULL,          -- CONSUMPTION | GENERATION
    device_type TEXT,                         -- IMS, IME, IMN, LPZ, NSM, DSZ, PAUSCHAL
    first_seen TEXT,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS meter_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,     -- z.B. "1-1:1.9.0 G.01"
    obis_base TEXT,                -- z.B. "1-1:1.9.0"
    suffix TEXT,                   -- z.B. "G.01", "G.01T", "P.01T"
    label_de TEXT,                 -- Sprechende Bezeichnung aus Excel
    direction TEXT,                -- CONSUMPTION | GENERATION
    billing_relevant INTEGER DEFAULT 1,
    description TEXT
);

CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    metering_point_id TEXT NOT NULL,
    timestamp_start TEXT NOT NULL,      -- ISO datetime Beginn Intervall
    timestamp_end TEXT NOT NULL,        -- ISO datetime Ende Intervall
    interval_minutes INTEGER NOT NULL,  -- 15 = QH
    meter_code_id INTEGER NOT NULL,
    value_kwh REAL NOT NULL,
    quality TEXT NOT NULL,              -- L1, L2, L3, 01, 02, 03, 04
    is_estimated INTEGER DEFAULT 0,    -- 1 wenn L2/L3
    FOREIGN KEY (batch_id) REFERENCES import_batches(id),
    FOREIGN KEY (meter_code_id) REFERENCES meter_codes(id)
);

-- Index für schnelle Abrechnung
CREATE INDEX IF NOT EXISTS idx_measurements_period
    ON measurements(metering_point_id, timestamp_start, meter_code_id);

CREATE INDEX IF NOT EXISTS idx_measurements_batch
    ON measurements(batch_id);

-- Übersichtsdaten für Plausibilitätsprüfung
CREATE TABLE IF NOT EXISTS overview_totals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    metering_point_id TEXT NOT NULL,
    meter_code_id INTEGER NOT NULL,
    total_kwh REAL NOT NULL,
    data_completeness REAL,       -- Prozent 0-100
    FOREIGN KEY (batch_id) REFERENCES import_batches(id),
    FOREIGN KEY (meter_code_id) REFERENCES meter_codes(id)
);

-- Vorbelegte MeterCodes für Energiegemeinschaften (CR_MSG)
INSERT OR IGNORE INTO meter_codes (code, obis_base, suffix, label_de, direction, description) VALUES
('1-1:1.9.0 G.01',  '1-1:1.9.0', 'G.01',  'Gesamtverbrauch lt. Messung',                    'CONSUMPTION', 'Verbrauch laut Messung'),
('1-1:1.9.0 G.01T', '1-1:1.9.0', 'G.01T', 'Gesamtverbrauch lt. Messung (Teilnahmefaktor)',  'CONSUMPTION', 'Verbrauch laut Messung entsprechend Teilnahmefaktor'),
('1-1:2.9.0 G.01',  '1-1:2.9.0', 'G.01',  'Gesamterzeugung lt. Messung',                    'GENERATION',  'Erzeugung laut Messung'),
('1-1:2.9.0 G.01T', '1-1:2.9.0', 'G.01T', 'Gesamterzeugung lt. Messung (Teilnahmefaktor)', 'GENERATION',  'Erzeugung laut Messung entsprechend Teilnahmefaktor'),
('1-1:2.9.0 G.02',  '1-1:2.9.0', 'G.02',  'Anteil gemeinschaftliche Erzeugung',             'GENERATION',  'Anteil an der gemeinschaftlichen Erzeugung'),
('1-1:1.9.0 G.02',  '1-1:1.9.0', 'G.02',  'Anteil gemeinschaftlicher Verbrauch',            'CONSUMPTION', 'Anteil am gemeinschaftlichen Verbrauch'),
('1-1:2.9.0 G.03',  '1-1:2.9.0', 'G.03',  'Eigendeckung',                                   'GENERATION',  'Eigendeckung'),
('1-1:2.9.0 G.03R', '1-1:2.9.0', 'G.03R', 'Eigendeckung aus erneuerbarer Energie',          'GENERATION',  'Eigendeckung aus erneuerbarer Energie'),
('1-1:2.9.0 P.01T', '1-1:2.9.0', 'P.01T', 'Restüberschuss bei EG (Teilnahmefaktor)',        'GENERATION',  'Restnetzüberschuss bei Energiegemeinschaft');
