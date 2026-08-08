-- Erweitertes Schema für die Web-Oberfläche

-- Benutzer für Login
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email TEXT,
    is_admin INTEGER DEFAULT 0,
    admin_feedback_email INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS member_profile_photos (
    member_id INTEGER PRIMARY KEY,
    mime_type TEXT NOT NULL,
    photo_data BLOB NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
);

-- Nachrichten von Mitgliedern inklusive Standort, Verbindungs-IP und Anlagen.
CREATE TABLE IF NOT EXISTS member_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    message TEXT,
    latitude REAL,
    longitude REAL,
    location_accuracy_m REAL,
    source_ip TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_member_feedback_status
    ON member_feedback(status, created_at DESC);

CREATE TABLE IF NOT EXISTS member_feedback_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_data BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (feedback_id) REFERENCES member_feedback(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_member_feedback_attachments_feedback
    ON member_feedback_attachments(feedback_id, id);

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
    data_status TEXT NOT NULL DEFAULT 'final',
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
    paid INTEGER DEFAULT 0,
    paid_at TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (member_id) REFERENCES members(id)
);

-- Buchungsjournal fuer Zahlungsbestaetigungen und Gutschriften
CREATE TABLE IF NOT EXISTS payment_bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    amount_eur REAL NOT NULL,
    direction TEXT NOT NULL,        -- member_to_eeg oder eeg_to_member
    booking_date TEXT NOT NULL,     -- Datum am Bankkonto
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    recorded_by_user_id INTEGER,
    recorded_by_username TEXT,
    note TEXT,
    reversed_at TEXT,
    reversed_by_user_id INTEGER,
    reversed_by_username TEXT,
    reverse_note TEXT,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (member_id) REFERENCES members(id),
    FOREIGN KEY (recorded_by_user_id) REFERENCES users(id),
    FOREIGN KEY (reversed_by_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_payment_bookings_member ON payment_bookings(member_id, booking_date);
CREATE INDEX IF NOT EXISTS idx_payment_bookings_invoice_member ON payment_bookings(invoice_id, member_id);

-- Finanzvortraege aus frueheren Abrechnungen
CREATE TABLE IF NOT EXISTS invoice_carryovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,        -- neue Abrechnung, in der der Vortrag erscheint
    member_id INTEGER NOT NULL,
    source_invoice_id INTEGER NOT NULL, -- alte offene Abrechnung
    amount_eur REAL NOT NULL,           -- positiv = Mitglied schuldet EEG, negativ = Guthaben
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    FOREIGN KEY (member_id) REFERENCES members(id),
    FOREIGN KEY (source_invoice_id) REFERENCES invoices(id),
    UNIQUE(invoice_id, member_id, source_invoice_id)
);
CREATE INDEX IF NOT EXISTS idx_invoice_carryovers_invoice_member ON invoice_carryovers(invoice_id, member_id);
CREATE INDEX IF NOT EXISTS idx_invoice_carryovers_source ON invoice_carryovers(source_invoice_id, member_id);

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
    data_status TEXT NOT NULL DEFAULT 'final',
    error_message TEXT,
    imported_by TEXT,
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Widerrufbare, nur gehasht gespeicherte Tokens für native Apps.
CREATE TABLE IF NOT EXISTS mobile_api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    access_token_hash TEXT NOT NULL UNIQUE,
    refresh_token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    access_expires_at TEXT NOT NULL,
    refresh_expires_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_mobile_api_tokens_user
    ON mobile_api_tokens(user_id, revoked_at);
CREATE INDEX IF NOT EXISTS idx_mobile_api_tokens_refresh
    ON mobile_api_tokens(refresh_token_hash, revoked_at);

-- Kurzlebige Einmalcodes zur Verbindung der nativen App. Klartextcodes und
-- Magic-Link-Token werden nie gespeichert.
CREATE TABLE IF NOT EXISTS mobile_connection_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,
    link_token_hash TEXT NOT NULL UNIQUE,
    delivery TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_by_user_id INTEGER,
    used_at TEXT,
    used_device_hash TEXT,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_mobile_connection_links_user
    ON mobile_connection_links(user_id, expires_at, used_at, revoked_at);
CREATE TABLE IF NOT EXISTS mobile_connection_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    requested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mobile_connection_requests_time
    ON mobile_connection_requests(requested_at, email_hash, ip_hash);

-- Nachrichten, die in der Mitglieder-App als Hinweis angezeigt werden.
CREATE TABLE IF NOT EXISTS mobile_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    member_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    starts_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES members(id)
);
CREATE INDEX IF NOT EXISTS idx_mobile_messages_active
    ON mobile_messages(active, member_id, starts_at, expires_at);

CREATE TABLE IF NOT EXISTS mobile_message_reads (
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    read_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (message_id, user_id),
    FOREIGN KEY (message_id) REFERENCES mobile_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Registrierte iOS- und Android-Geräte. Das Push-Token ist kein Anmelde-Token, wird aber
-- trotzdem nur serverseitig gespeichert und beim Abmelden deaktiviert.
CREATE TABLE IF NOT EXISTS mobile_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    device_token TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL DEFAULT 'ios',
    apns_environment TEXT NOT NULL DEFAULT 'sandbox',
    app_version TEXT,
    notifications_enabled INTEGER NOT NULL DEFAULT 1,
    sound_enabled INTEGER NOT NULL DEFAULT 1,
    invoice_notifications INTEGER NOT NULL DEFAULT 1,
    community_notifications INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    disabled_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_mobile_devices_user
    ON mobile_devices(user_id, disabled_at);

-- Dauerhafte Push-Warteschlange. Ein separater Worker versendet und wiederholt
-- vorübergehende Fehler, ohne den Admin-Request zu blockieren.
CREATE TABLE IF NOT EXISTS mobile_push_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_error TEXT,
    sent_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(message_id, device_id),
    FOREIGN KEY (message_id) REFERENCES mobile_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (device_id) REFERENCES mobile_devices(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_mobile_push_outbox_pending
    ON mobile_push_outbox(status, next_attempt_at);
