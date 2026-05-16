-- Erweitertes Schema für die Web-Oberfläche

-- Benutzer für Login
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Mitglieder erweitert (Adresse, Email)
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    address_street TEXT,
    address_zip TEXT,
    address_city TEXT,
    einspeiser_zp TEXT,
    einspeiser_ab TEXT,
    bezug_zp TEXT,
    bezug_ab TEXT,
    teilnahme REAL DEFAULT 1.0,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

-- Preise pro Quartal
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    valid_from TEXT NOT NULL,       -- ISO date (Quartalsstart)
    valid_to TEXT NOT NULL,         -- ISO date (Quartalsende)
    price_consumption REAL NOT NULL, -- ct/kWh Verbrauch
    price_generation REAL NOT NULL,  -- ct/kWh Erzeugung
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Abrechnungen
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_from TEXT NOT NULL,      -- ISO date
    period_to TEXT NOT NULL,        -- ISO date
    status TEXT NOT NULL DEFAULT 'draft',  -- draft, finalized, sent
    total_kwh_traded REAL,
    total_income REAL,
    total_expense REAL,
    total_margin REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finalized_at TEXT
);

-- Einzelpositionen pro Abrechnung
CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    type TEXT NOT NULL,             -- 'consumption' oder 'generation'
    kwh REAL NOT NULL,
    price_per_kwh REAL NOT NULL,   -- ct/kWh zum Zeitpunkt der Abrechnung
    amount_eur REAL NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (member_id) REFERENCES members(id)
);

-- E-Mail Versand-Protokoll
CREATE TABLE IF NOT EXISTS email_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER,
    member_id INTEGER,
    recipient_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL,           -- 'sent', 'failed', 'pending'
    error_message TEXT,
    sent_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (member_id) REFERENCES members(id)
);

-- Import-Log für Web-Uploads
CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    records_imported INTEGER,
    records_overwritten INTEGER DEFAULT 0,
    status TEXT NOT NULL,           -- 'success', 'error', 'partial'
    error_message TEXT,
    imported_by TEXT,
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);
