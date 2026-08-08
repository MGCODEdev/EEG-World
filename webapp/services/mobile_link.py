"""One-time, short-lived links for securely connecting a mobile app."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone


LINK_LIFETIME_MINUTES = 10
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{16,128}$")


class MobileLinkError(ValueError):
    pass


def _timestamp(value=None):
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def secret_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_code(value):
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def device_identifier_hash(value):
    value = str(value or "").strip()
    if not _DEVICE_ID_RE.fullmatch(value):
        raise MobileLinkError("Ungültige Gerätekennung.")
    return secret_hash(value)


def ensure_mobile_link_schema(db):
    token_columns = {row[1] for row in db.execute("PRAGMA table_info(mobile_api_tokens)")}
    for name, definition in {
        "device_identifier_hash": "TEXT",
        "device_name": "TEXT",
        "last_used_at": "TEXT",
    }.items():
        if name not in token_columns:
            db.execute(f"ALTER TABLE mobile_api_tokens ADD COLUMN {name} {definition}")
    device_columns = {row[1] for row in db.execute("PRAGMA table_info(mobile_devices)")}
    if "install_identifier_hash" not in device_columns:
        db.execute("ALTER TABLE mobile_devices ADD COLUMN install_identifier_hash TEXT")
    db.executescript("""
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
    """)


def register_mobile_link_request(db, email, ip):
    """Rate-limit without retaining the member email or client IP."""
    now = datetime.now(timezone.utc)
    window = _timestamp(now - timedelta(minutes=15))
    retention = _timestamp(now - timedelta(hours=24))
    email_hash = secret_hash(str(email or "").strip().lower())
    ip_hash = secret_hash(str(ip or "unknown"))
    db.execute("DELETE FROM mobile_connection_requests WHERE requested_at<?", (retention,))
    email_count = db.execute("""
        SELECT COUNT(*) FROM mobile_connection_requests
        WHERE email_hash=? AND requested_at>=?
    """, (email_hash, window)).fetchone()[0]
    ip_count = db.execute("""
        SELECT COUNT(*) FROM mobile_connection_requests
        WHERE ip_hash=? AND requested_at>=?
    """, (ip_hash, window)).fetchone()[0]
    db.execute("""
        INSERT INTO mobile_connection_requests(email_hash, ip_hash, requested_at)
        VALUES (?, ?, ?)
    """, (email_hash, ip_hash, _timestamp(now)))
    db.commit()
    return email_count < 3 and ip_count < 10


def create_mobile_link(db, user_id, created_by_user_id=None, delivery="admin"):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=LINK_LIFETIME_MINUTES)
    code_plain = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
    code = f"{code_plain[:5]}-{code_plain[5:]}"
    link_token = secrets.token_urlsafe(32)
    db.execute("""
        UPDATE mobile_connection_links SET revoked_at=?
        WHERE user_id=? AND used_at IS NULL AND revoked_at IS NULL AND expires_at>?
    """, (_timestamp(now), int(user_id), _timestamp(now)))
    db.execute("""
        INSERT INTO mobile_connection_links (
            user_id, code_hash, link_token_hash, delivery,
            created_at, expires_at, created_by_user_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        int(user_id), secret_hash(normalize_code(code)), secret_hash(link_token),
        delivery, _timestamp(now), _timestamp(expires), created_by_user_id,
    ))
    db.commit()
    return {
        "code": code,
        "link_token": link_token,
        "expires_at": _timestamp(expires),
        "expires_in": LINK_LIFETIME_MINUTES * 60,
    }


def begin_redeem_mobile_link(db, *, code=None, link_token=None, device_id=None):
    """Claim a link atomically and leave the transaction open for token issuance."""
    if bool(code) == bool(link_token):
        raise MobileLinkError("Verbindungscode oder Magic-Link-Token erforderlich.")
    install_hash = device_identifier_hash(device_id)
    column = "code_hash" if code else "link_token_hash"
    value = secret_hash(normalize_code(code)) if code else secret_hash(str(link_token))
    now = _timestamp()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(f"""
        SELECT l.id, l.user_id, u.username, u.member_id, u.password_change_required,
               m.name AS member_name, m.active AS member_active
        FROM mobile_connection_links l
        JOIN users u ON u.id=l.user_id
        JOIN members m ON m.id=u.member_id
        WHERE l.{column}=? AND l.used_at IS NULL AND l.revoked_at IS NULL
          AND l.expires_at>?
    """, (value, now)).fetchone()
    if not row:
        db.rollback()
        raise MobileLinkError("Verbindungscode ist ungültig, abgelaufen oder bereits verwendet.")
    if row["password_change_required"]:
        db.rollback()
        raise MobileLinkError("Bitte den Webportal-Zugang zuerst vollständig aktivieren.")
    if not row["member_active"]:
        db.rollback()
        raise MobileLinkError("Mitglied ist nicht aktiv.")
    updated = db.execute("""
        UPDATE mobile_connection_links
        SET used_at=?, used_device_hash=?
        WHERE id=? AND used_at IS NULL AND revoked_at IS NULL AND expires_at>?
    """, (now, install_hash, row["id"], now)).rowcount
    if updated != 1:
        db.rollback()
        raise MobileLinkError("Verbindungscode wurde bereits verwendet.")
    return dict(row), install_hash
