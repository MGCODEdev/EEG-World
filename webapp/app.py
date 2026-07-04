#!/usr/bin/env python3
"""EEG Web-Oberfläche - Hauptanwendung."""

import os
import sys
import sqlite3
import secrets
import re
import json
import threading
import time
import base64
import hashlib
import ipaddress
import io
from datetime import datetime, date, timezone, timedelta
from functools import wraps
from email.header import Header
from email.utils import formataddr
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
from zoneinfo import ZoneInfo

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, send_file, jsonify, g, abort)
from flask import has_request_context
from flask import session
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass

# App-Pfad setzen
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, '..', 'eeg_data.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, '..', 'data')
INVOICE_FOLDER = os.path.join(BASE_DIR, 'invoices')
BACKUP_FOLDER = os.path.join(BASE_DIR, '..', 'backups')
INSTANCE_DIR = os.path.join(BASE_DIR, '..', 'instance')
APP_TIMEZONE = ZoneInfo(os.environ.get('EEG_TIMEZONE', 'Europe/Vienna'))

app = Flask(__name__)
_IS_PRODUCTION = os.environ.get('EEG_ENV', '').lower() == 'production' or os.environ.get('FLASK_ENV') == 'production'
_SECRET_KEY = os.environ.get('EEG_SECRET_KEY')
if _IS_PRODUCTION and not _SECRET_KEY:
    raise RuntimeError('EEG_SECRET_KEY muss im Produktivbetrieb gesetzt sein.')
app.config['SECRET_KEY'] = _SECRET_KEY or secrets.token_hex(32)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
app.config['WTF_CSRF_ENABLED'] = True
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SERVER_NAME_PUBLIC'] = os.environ.get('EEG_SERVER_NAME_PUBLIC', 'localhost')
app.config['PUBLIC_BASE_URL'] = os.environ.get('EEG_PUBLIC_BASE_URL', '').strip().rstrip('/')
app.config['SESSION_COOKIE_SECURE'] = _IS_PRODUCTION
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_PATH'] = '/'
if os.environ.get('EEG_SESSION_COOKIE_DOMAIN'):
    app.config['SESSION_COOKIE_DOMAIN'] = os.environ['EEG_SESSION_COOKIE_DOMAIN']

DEFAULT_ORG_NAME = os.environ.get('EEG_ORG_NAME', 'EEG Portal')
DEFAULT_ORG_EMAIL = os.environ.get('EEG_ORG_EMAIL', 'office@example.org')
DEFAULT_ORG_WEBSITE = os.environ.get('EEG_ORG_WEBSITE', 'https://example.org/')
DEFAULT_ORG_ADDRESS = os.environ.get('EEG_ORG_ADDRESS', 'Adresse bitte konfigurieren')
DEFAULT_ORG_LEGAL = os.environ.get('EEG_ORG_LEGAL', 'Vereinsdaten bitte konfigurieren')

# Proxy-Fix: Hinter HAProxy/Nginx die echte Client-IP lesen
# x_for=1: Ein Proxy-Level (HAProxy/Nginx) leitet X-Forwarded-For weiter
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

csrf = CSRFProtect(app)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INVOICE_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)
os.makedirs(INSTANCE_DIR, exist_ok=True)

GOOGLE_DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file']
GOOGLE_CLIENT_SECRETS_FILE = os.environ.get(
    'EEG_GOOGLE_CLIENT_SECRETS',
    os.path.join(INSTANCE_DIR, 'google_client_secret.json')
)
GOOGLE_TOKEN_FILE = os.environ.get(
    'EEG_GOOGLE_TOKEN_FILE',
    os.path.join(INSTANCE_DIR, 'google_drive_token.json')
)
GOOGLE_OAUTH_REDIRECT_URI = os.environ.get('EEG_GOOGLE_OAUTH_REDIRECT_URI', '')
RESTORE_MAX_FILES = int(os.environ.get('EEG_RESTORE_MAX_FILES', '1000'))
RESTORE_MAX_UNCOMPRESSED_BYTES = int(os.environ.get('EEG_RESTORE_MAX_UNCOMPRESSED_MB', '512')) * 1024 * 1024

BACKUP_SETTING_DEFAULTS = {
    'backup_auto_enabled': 'true',
    'backup_auto_time': '02:30',
    'backup_retention_daily': '3',
    'backup_retention_weekly': '4',
    'backup_retention_monthly': '6',
    'backup_retention_yearly': '3',
    'backup_email_enabled': 'false',
    'backup_email_weekday': '6',
    'backup_email_time': '03:00',
    'backup_email_to': '',
    'backup_email_max_mb': '20',
    'backup_drive_enabled': 'false',
    'backup_drive_folder_id': '',
    'backup_drive_last_upload': '',
    'backup_drive_last_check': '',
    'backup_drive_last_error': '',
    'backup_auto_last_run_date': '',
    'backup_email_last_attempt_week': '',
    'backup_email_last_sent_week': '',
}
BACKUP_JOB_LOCK = threading.Lock()
BACKUP_SCHEDULER_LOCK = threading.Lock()
BACKUP_SCHEDULER_STARTED = False


def local_now():
    return datetime.now(APP_TIMEZONE)


def utc_now_string():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def form_switch_enabled(name):
    return '1' in request.form.getlist(name)


def to_local_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text.replace(' ', 'T'))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(APP_TIMEZONE)


def local_day_bounds_as_utc_strings(day_text=None):
    """Lokale Tagesgrenzen fuer SQLite-UTC-Zeitstempel."""
    if day_text:
        day = datetime.strptime(day_text, '%Y-%m-%d').date()
    else:
        day = local_now().date()
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=APP_TIMEZONE)
    end_local = datetime.combine(day, datetime.max.time().replace(microsecond=0), tzinfo=APP_TIMEZONE)
    start_utc = start_local.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    end_utc = end_local.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    return start_utc, end_utc


@app.template_filter('localdatetime')
def format_local_datetime(value, fmt='%d.%m.%Y %H:%M'):
    dt = to_local_datetime(value)
    return dt.strftime(fmt) if dt else '—'


@app.template_filter('localdate')
def format_local_date(value, fmt='%d.%m.%Y'):
    dt = to_local_datetime(value)
    return dt.strftime(fmt) if dt else '—'


@app.context_processor
def inject_template_globals():
    public_cfg = {
        'org_name': DEFAULT_ORG_NAME,
        'org_email': DEFAULT_ORG_EMAIL,
        'org_website': DEFAULT_ORG_WEBSITE,
        'org_address': DEFAULT_ORG_ADDRESS,
        'org_legal': DEFAULT_ORG_LEGAL,
        'payment_bic': '',
        'payment_iban': '',
        'payment_recipient': DEFAULT_ORG_NAME,
    }
    try:
        public_cfg.update(get_public_config(get_db()))
    except Exception:
        pass
    return {
        'now': local_now(),
        'public_cfg': public_cfg,
        'org_name': public_cfg['org_name'],
        'org_email': public_cfg['org_email'],
        'org_website': public_cfg['org_website'],
        'org_address': public_cfg['org_address'],
        'org_legal': public_cfg['org_legal'],
        'timezone_name': getattr(APP_TIMEZONE, 'key', 'Europe/Vienna'),
    }


class _NewsletterHTMLSanitizer(HTMLParser):
    """Kleine Allowlist fuer Newsletter-HTML ohne externe Abhaengigkeit."""

    ALLOWED_TAGS = {
        'a', 'b', 'br', 'blockquote', 'div', 'em', 'h2', 'h3', 'h4', 'hr',
        'i', 'img', 'li', 'ol', 'p', 'span', 'strong', 'table', 'tbody',
        'td', 'th', 'thead', 'tr', 'u', 'ul'
    }
    ALLOWED_ATTRS = {
        'a': {'href', 'title'},
        'img': {'src', 'alt', 'width', 'height'},
        'table': {'width'},
        'td': {'colspan', 'rowspan'},
        'th': {'colspan', 'rowspan'},
    }
    SAFE_URL_SCHEMES = {'http', 'https', 'mailto'}
    VOID_TAGS = {'br', 'hr', 'img'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def _safe_attrs(self, tag, attrs):
        allowed = self.ALLOWED_ATTRS.get(tag, set())
        safe_attrs = []
        for key, value in attrs:
            key = (key or '').lower()
            value = value or ''
            if key not in allowed:
                continue
            if key in {'href', 'src'}:
                parsed = urlparse(value.strip())
                if parsed.scheme.lower() not in self.SAFE_URL_SCHEMES:
                    continue
            safe_attrs.append(f'{key}="{escape(value, quote=True)}"')
        return (' ' + ' '.join(safe_attrs)) if safe_attrs else ''

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.ALLOWED_TAGS:
            self.parts.append(f'<{tag}{self._safe_attrs(tag, attrs)}>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.ALLOWED_TAGS and tag not in self.VOID_TAGS:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        self.parts.append(escape(data))

    def handle_entityref(self, name):
        self.parts.append(f'&{name};')

    def handle_charref(self, name):
        self.parts.append(f'&#{name};')


def sanitize_newsletter_html(html):
    sanitizer = _NewsletterHTMLSanitizer()
    sanitizer.feed(html or '')
    sanitizer.close()
    return ''.join(sanitizer.parts)


def is_safe_redirect_url(target):
    """Erlaubt nur relative oder gleiche Host-Weiterleitungen."""
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in {'http', 'https'} and ref.netloc == test.netloc


def public_base_url():
    """Liefert die oeffentliche Basis-URL fuer Links in E-Mails."""
    configured = (app.config.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if configured:
        parsed = urlparse(configured)
        if parsed.scheme in {'http', 'https'} and parsed.netloc:
            return configured
        app.logger.warning('Ignoring invalid EEG_PUBLIC_BASE_URL: %s', configured)

    public_host = (app.config.get('SERVER_NAME_PUBLIC') or '').strip().rstrip('/')
    if public_host and public_host != 'localhost':
        if '://' in public_host:
            parsed = urlparse(public_host)
            if parsed.scheme in {'http', 'https'} and parsed.netloc:
                return public_host.rstrip('/')
        return f'https://{public_host}'

    if has_request_context():
        return request.url_root.rstrip('/')
    return 'http://localhost'


def public_url_for(endpoint, **values):
    """Erzeugt absolute URLs mit der oeffentlichen Basisadresse."""
    return urljoin(public_base_url() + '/', url_for(endpoint, **values).lstrip('/'))


def _hostname_without_port(host):
    text = (host or '').strip().lower()
    if not text:
        return ''
    if text.startswith('[') and ']' in text:
        return text[1:text.index(']')]
    return text.rsplit(':', 1)[0] if ':' in text else text


def _is_internal_hostname(hostname):
    if hostname in {'localhost', '127.0.0.1', '::1'}:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def initial_password_hash():
    """Erzeugt sichere Initial-Passwoerter ohne fest codierten Default."""
    password = os.environ.get('EEG_INITIAL_ADMIN_PASSWORD')
    if password:
        return generate_password_hash(password)
    if _IS_PRODUCTION:
        raise RuntimeError('EEG_INITIAL_ADMIN_PASSWORD muss fuer neue Admins im Produktivbetrieb gesetzt sein.')
    app.logger.warning('Kein EEG_INITIAL_ADMIN_PASSWORD gesetzt; neuer Admin erhaelt ein zufaelliges Passwort.')
    return generate_password_hash(secrets.token_urlsafe(32))


def safe_extract_zip_member(zf, member_name, destination):
    """Extrahiert nur Dateien, die im erwarteten Zielverzeichnis bleiben."""
    normalized = os.path.normpath(member_name).replace('\\', '/')
    if normalized.startswith('../') or normalized.startswith('/') or '/..' in normalized:
        raise ValueError(f'Ungueltiger ZIP-Pfad: {member_name}')
    target_path = os.path.abspath(os.path.join(destination, normalized))
    destination_abs = os.path.abspath(destination)
    if not target_path.startswith(destination_abs + os.sep) and target_path != destination_abs:
        raise ValueError(f'Ungueltiger ZIP-Zielpfad: {member_name}')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with zf.open(member_name) as source, open(target_path, 'wb') as target:
        target.write(source.read())
    return target_path


def validate_backup_zip(zf):
    """Prueft Backup-ZIPs vor dem Entpacken gegen unerwartete Dateien und ZIP-Bomben."""
    infos = [info for info in zf.infolist() if not info.is_dir()]
    if len(infos) > RESTORE_MAX_FILES:
        raise ValueError(f'Backup enthaelt zu viele Dateien ({len(infos)} > {RESTORE_MAX_FILES}).')

    total_size = sum(info.file_size for info in infos)
    if total_size > RESTORE_MAX_UNCOMPRESSED_BYTES:
        max_mb = RESTORE_MAX_UNCOMPRESSED_BYTES / 1024 / 1024
        raise ValueError(f'Backup ist entpackt zu gross ({total_size / 1024 / 1024:.1f} MB > {max_mb:.0f} MB).')

    names = []
    for info in infos:
        name = info.filename
        normalized = os.path.normpath(name).replace('\\', '/')
        if normalized.startswith('../') or normalized.startswith('/') or '/..' in normalized:
            raise ValueError(f'Ungueltiger ZIP-Pfad: {name}')
        if normalized not in {'eeg_data.db', 'backup_manifest.txt'} and not normalized.startswith('invoices/'):
            raise ValueError(f'Unerwartete Datei im Backup: {name}')
        names.append(normalized)

    if 'eeg_data.db' not in names:
        raise ValueError('Ungueltiges Backup: eeg_data.db nicht gefunden.')
    return names


@app.before_request
def enforce_allowed_country():
    """Optionaler Laenderblock, gedacht fuer Cloudflare/Reverse-Proxy-Header."""
    allowed = {
        c.strip().upper()
        for c in os.environ.get('EEG_ALLOWED_COUNTRIES', '').split(',')
        if c.strip()
    }
    if not allowed:
        return None
    country = (request.headers.get('CF-IPCountry')
               or request.headers.get('X-Country-Code')
               or '').upper()
    if country not in allowed:
        abort(403)
    return None


@app.before_request
def redirect_internal_host_to_public_url():
    """Verhindert Browser-Sessions ueber interne HTTP-Adressen im Produktivbetrieb."""
    if not _IS_PRODUCTION:
        return None
    redirect_enabled = os.environ.get('EEG_REDIRECT_INTERNAL_HTTP', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    if not redirect_enabled:
        return None
    base_url = public_base_url()
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc or parsed.hostname in {None, 'localhost'}:
        return None
    current_hostname = _hostname_without_port(request.host)
    public_hostname = (parsed.hostname or '').lower()
    if current_hostname == public_hostname:
        return None
    if request.is_secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https':
        return None
    if not _is_internal_hostname(current_hostname):
        return None
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        return redirect(urljoin(base_url + '/', 'login?csrf=1'), code=303)
    target = urljoin(base_url + '/', request.full_path.lstrip('/'))
    if target.endswith('?'):
        target = target[:-1]
    return redirect(target, code=302)


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    app.logger.warning(
        'CSRF validation failed | reason=%s | host=%s | path=%s | secure=%s',
        getattr(error, 'description', str(error)),
        request.host,
        request.path,
        request.is_secure,
    )
    if current_user and current_user.is_authenticated:
        flash('Die Sicherheitsprüfung ist abgelaufen. Bitte Aktion erneut ausführen.', 'warning')
        return redirect(url_for('dashboard' if current_user.is_admin else 'portal_dashboard'))
    return redirect(public_url_for('login', csrf='1'), code=303)


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.highcharts.com; "
        "connect-src 'self'; "
        "object-src 'none'"
    )
    if _IS_PRODUCTION and (request.is_secure or request.headers.get('X-Forwarded-Proto', '').lower() == 'https'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Bitte einloggen.'


# === Database ===

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def ensure_import_schema(db):
    """Stellt sicher, dass die EDA-Importtabellen vorhanden sind."""
    import_schema_path = os.path.join(BASE_DIR, '..', 'schema.sql')
    if os.path.exists(import_schema_path):
        with open(import_schema_path) as f:
            db.executescript(f.read())
    for col, coldef in [
        ('data_status', "TEXT NOT NULL DEFAULT 'final'"),
        ('replaced_by_batch_id', 'INTEGER'),
        ('replaced_at', 'TEXT'),
    ]:
        try:
            db.execute(f"ALTER TABLE import_batches ADD COLUMN {col} {coldef}")
        except sqlite3.OperationalError:
            pass
    db.execute("UPDATE import_batches SET data_status='final' WHERE data_status IS NULL OR data_status=''")


def init_db():
    """Schema initialisieren und Admin-User anlegen."""
    db = sqlite3.connect(DB_PATH)
    schema_path = os.path.join(BASE_DIR, 'schema_web.sql')
    with open(schema_path) as f:
        db.executescript(f.read())
    ensure_import_schema(db)
    # Users: member_id, role, invite_token, invite_expires vor Admin-Anlage migrieren
    for col, coldef in [('member_id', 'INTEGER'), ('role', "TEXT DEFAULT 'member'"),
                        ('invite_token', 'TEXT'), ('invite_expires', 'TEXT')]:
        try:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {coldef}")
        except sqlite3.OperationalError:
            pass
    # Admin-User anlegen falls nicht vorhanden
    existing = db.execute("SELECT id FROM users WHERE username='SuperAdmin'").fetchone()
    if not existing:
        # Auch alten 'admin' User prüfen
        old_admin = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not old_admin:
            pw_hash = initial_password_hash()
            db.execute("INSERT INTO users (username, password_hash, is_admin, role) VALUES (?, ?, 1, 'admin')",
                       ('SuperAdmin', pw_hash))
        db.commit()
    # Bank-Felder zu members hinzufügen (Migration)
    try:
        db.execute("ALTER TABLE members ADD COLUMN iban TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE members ADD COLUMN bic TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE members ADD COLUMN account_holder TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE members ADD COLUMN phone TEXT")
    except sqlite3.OperationalError:
        pass
    # Users: member_id, role, invite_token, invite_expires
    for col, coldef in [('member_id', 'INTEGER'), ('role', "TEXT DEFAULT 'member'"),
                        ('invite_token', 'TEXT'), ('invite_expires', 'TEXT')]:
        try:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {coldef}")
        except sqlite3.OperationalError:
            pass
    # Bestehende admins markieren
    db.execute("UPDATE users SET role='admin' WHERE is_admin=1 AND (role IS NULL OR role='')")
    db.execute("UPDATE users SET role='member' WHERE is_admin=0 AND (role IS NULL OR role='')")
    # Contracts-Tabelle
    db.execute("""CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        filename TEXT NOT NULL,
        file_data BLOB NOT NULL,
        uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
        uploaded_by TEXT,
        FOREIGN KEY (member_id) REFERENCES members(id)
    )""")
    # Audit-Log-Tabelle
    db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        user_id INTEGER,
        username TEXT,
        action TEXT NOT NULL,
        detail TEXT,
        ip TEXT,
        url TEXT,
        method TEXT
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    # Settings-Tabelle für SMTP etc.
    db.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    # Defaults setzen falls leer
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_host', 'mail.your-server.de')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_port', '587')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_user', '')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_pass', '')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_from', '')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('smtp_tls', 'true')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mail_from_address', '')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mail_from_name', ?)", (DEFAULT_ORG_NAME,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mail_reply_to', '')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mail_reply_to_name', ?)", (DEFAULT_ORG_NAME,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('org_name', ?)", (DEFAULT_ORG_NAME,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('org_email', ?)", (DEFAULT_ORG_EMAIL,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('org_website', ?)", (DEFAULT_ORG_WEBSITE,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('org_address', ?)", (DEFAULT_ORG_ADDRESS,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('org_legal', ?)", (DEFAULT_ORG_LEGAL,))
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_bic', '')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_iban', '')")
    db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('payment_recipient', ?)", (DEFAULT_ORG_NAME,))
    for key, value in BACKUP_SETTING_DEFAULTS.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.execute("""CREATE TABLE IF NOT EXISTS oauth_pkce_sessions (
        id TEXT PRIMARY KEY,
        user_id INTEGER,
        state TEXT NOT NULL,
        code_verifier TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""")
    # Zahlungsstatus und Buchungsjournal
    for col, coldef in [('paid', 'INTEGER DEFAULT 0'), ('paid_at', 'TEXT')]:
        try:
            db.execute(f"ALTER TABLE invoice_items ADD COLUMN {col} {coldef}")
        except sqlite3.OperationalError:
            pass
    for table, col, coldef in [
        ('invoices', 'data_status', "TEXT NOT NULL DEFAULT 'final'"),
        ('import_log', 'data_status', "TEXT NOT NULL DEFAULT 'final'"),
    ]:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
        except sqlite3.OperationalError:
            pass
    db.execute("UPDATE invoices SET data_status='final' WHERE data_status IS NULL OR data_status=''")
    db.execute("UPDATE import_log SET data_status='final' WHERE data_status IS NULL OR data_status=''")
    db.execute("""CREATE TABLE IF NOT EXISTS payment_bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        amount_eur REAL NOT NULL,
        direction TEXT NOT NULL,
        booking_date TEXT NOT NULL,
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
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_payment_bookings_member ON payment_bookings(member_id, booking_date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_payment_bookings_invoice_member ON payment_bookings(invoice_id, member_id)")
    db.execute("""CREATE TABLE IF NOT EXISTS invoice_carryovers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        source_invoice_id INTEGER NOT NULL,
        amount_eur REAL NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (invoice_id) REFERENCES invoices(id),
        FOREIGN KEY (member_id) REFERENCES members(id),
        FOREIGN KEY (source_invoice_id) REFERENCES invoices(id),
        UNIQUE(invoice_id, member_id, source_invoice_id)
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_invoice_carryovers_invoice_member ON invoice_carryovers(invoice_id, member_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_invoice_carryovers_source ON invoice_carryovers(source_invoice_id, member_id)")
    # Newsletter-Tabellen
    db.execute("""CREATE TABLE IF NOT EXISTS newsletters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        body_html TEXT NOT NULL,
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        sent_at TEXT,
        recipients_count INTEGER DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS newsletter_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        newsletter_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        sent_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (newsletter_id) REFERENCES newsletters(id),
        FOREIGN KEY (member_id) REFERENCES members(id)
    )""")
    # Newsletter-Opt-out Spalte in members
    try:
        db.execute("ALTER TABLE members ADD COLUMN newsletter_optout INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # Unsubscribe-Token in members
    try:
        db.execute("ALTER TABLE members ADD COLUMN unsubscribe_token TEXT")
    except sqlite3.OperationalError:
        pass
    db.commit()
    db.close()


def _create_named_admin(db, username, member_id, email):
    """Erstellt einen Admin-User falls noch nicht vorhanden."""
    existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not existing:
        pw_hash = initial_password_hash()
        db.execute("""INSERT INTO users (username, password_hash, email, is_admin, role, member_id)
                      VALUES (?, ?, ?, 1, 'admin', ?)""",
                   (username, pw_hash, email, member_id))


def _is_valid_email(address):
    """Einfache E-Mail-Validierung für Header/SMTP-Konfiguration."""
    if not address:
        return False
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', address.strip()))


def _mail_header(name, address):
    """Erzeugt RFC-konformen Address-Header mit UTF-8 Anzeigename."""
    return formataddr((str(Header(name or '', 'utf-8')), address))


def _load_mail_config(db):
    """Lädt SMTP- und Mail-Absenderkonfiguration aus settings."""
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    cfg = {r['key']: r['value'] for r in rows}

    smtp_user = (cfg.get('smtp_user') or '').strip()
    from_address = (cfg.get('mail_from_address') or cfg.get('smtp_from') or smtp_user).strip()
    from_name = (cfg.get('mail_from_name') or DEFAULT_ORG_NAME).strip()
    reply_to_address = (cfg.get('mail_reply_to') or from_address).strip()
    reply_to_name = (cfg.get('mail_reply_to_name') or DEFAULT_ORG_NAME).strip()
    smtp_tls = (cfg.get('smtp_tls') or 'true').strip().lower() in ('1', 'true', 'yes', 'on')

    return {
        'smtp_host': (cfg.get('smtp_host') or '').strip(),
        'smtp_port': int((cfg.get('smtp_port') or '587').strip() or '587'),
        'smtp_user': smtp_user,
        'smtp_pass': cfg.get('smtp_pass') or '',
        'smtp_tls': smtp_tls,
        'from_address': from_address,
        'from_name': from_name,
        'reply_to_address': reply_to_address,
        'reply_to_name': reply_to_name,
        'from_header': _mail_header(from_name, from_address) if from_address else '',
        'reply_to_header': _mail_header(reply_to_name, reply_to_address) if reply_to_address else '',
    }


def _validate_mail_config(mail_cfg):
    """Validiert Mail-Konfiguration gemäß RFC/Anwendungsanforderungen."""
    if not mail_cfg.get('smtp_user'):
        return False, 'SMTP-Benutzername fehlt.'
    if not mail_cfg.get('smtp_host'):
        return False, 'SMTP-Server fehlt.'
    if not mail_cfg.get('smtp_pass'):
        return False, 'SMTP-Passwort fehlt.'
    if not mail_cfg.get('from_address'):
        return False, 'Absenderadresse für E-Mails fehlt.'
    if not _is_valid_email(mail_cfg.get('from_address')):
        return False, 'Absenderadresse für E-Mails ist ungültig.'
    if not _is_valid_email(mail_cfg.get('reply_to_address')):
        return False, 'Antwortadresse ist ungültig.'

    smtp_user = mail_cfg.get('smtp_user').lower()
    from_addr = mail_cfg.get('from_address').lower()
    if from_addr != smtp_user:
        smtp_domain = smtp_user.split('@')[-1] if '@' in smtp_user else ''
        from_domain = from_addr.split('@')[-1] if '@' in from_addr else ''
        if not smtp_domain or smtp_domain != from_domain:
            return False, 'Absenderadresse muss dem SMTP-Benutzernamen oder einer Alias-Adresse derselben Domain entsprechen.'

    return True, ''


def _get_valid_mail_config(db):
    """Lädt und validiert Mail-Konfiguration; wirft RuntimeError bei Fehlern."""
    mail_cfg = _load_mail_config(db)
    ok, error = _validate_mail_config(mail_cfg)
    if not ok:
        raise RuntimeError(error)
    return mail_cfg


def get_public_config(db):
    rows = db.execute("""SELECT key, value FROM settings WHERE key IN (
        'org_name', 'org_email', 'org_website', 'org_address', 'org_legal',
        'payment_bic', 'payment_iban', 'payment_recipient'
    )""").fetchall()
    cfg = {r['key']: r['value'] for r in rows}
    return {
        'org_name': cfg.get('org_name') or DEFAULT_ORG_NAME,
        'org_email': cfg.get('org_email') or DEFAULT_ORG_EMAIL,
        'org_website': cfg.get('org_website') or DEFAULT_ORG_WEBSITE,
        'org_address': cfg.get('org_address') or DEFAULT_ORG_ADDRESS,
        'org_legal': cfg.get('org_legal') or DEFAULT_ORG_LEGAL,
        'payment_bic': cfg.get('payment_bic') or '',
        'payment_iban': cfg.get('payment_iban') or '',
        'payment_recipient': cfg.get('payment_recipient') or cfg.get('org_name') or DEFAULT_ORG_NAME,
    }


def _log_mail_send(mail_cfg, recipient, subject):
    """Loggt Versandparameter ohne sensitive Daten (kein Passwort)."""
    app.logger.info(
        'Sending mail | SMTP host: %s | SMTP user: %s | From: %s | Reply-To: %s | To: %s | Subject: %s',
        mail_cfg.get('smtp_host'),
        mail_cfg.get('smtp_user'),
        mail_cfg.get('from_header'),
        mail_cfg.get('reply_to_header'),
        recipient,
        subject,
    )


def _format_invite_expires(invite_expires):
    """Formatiert das Ablaufdatum für Einladungs-Mails."""
    if not invite_expires:
        return 'in 14 Tagen'
    try:
        return datetime.fromisoformat(str(invite_expires)).strftime('%d.%m.%Y um %H:%M Uhr')
    except ValueError:
        return str(invite_expires)


def _build_invitation_email(member_name, username, role, invite_url, invite_expires, public_cfg, logo_src=None):
    """Erzeugt Betreff, Text- und HTML-Teil für Portal-Einladungen."""
    display_name = (member_name or username or 'Mitglied').strip()
    role_label = 'Administrator' if role == 'admin' else 'Teilnehmer'
    expires_text = _format_invite_expires(invite_expires)
    org_name = public_cfg.get('org_name') or DEFAULT_ORG_NAME
    org_email = public_cfg.get('org_email') or DEFAULT_ORG_EMAIL
    org_address = public_cfg.get('org_address') or ''
    org_website = public_cfg.get('org_website') or ''

    subject = f'Einladung zum {org_name}'
    body_text = f"""Hallo {display_name},

Christian und Markus von der EEG haben für Sie einen Zugang zum {org_name} eingerichtet.

So starten Sie:
1. Öffnen Sie den folgenden Einladungslink:
{invite_url}
2. Legen Sie Ihr eigenes Passwort fest.
3. Melden Sie sich danach mit Ihrem Benutzernamen an: {username}

Der Link ist bis {expires_text} gültig. Falls der Link abgelaufen ist, antworten Sie bitte auf diese E-Mail oder wenden Sie sich an {org_email}.

Ihre Rolle im Portal: {role_label}

Viele Grüße
Christian und Markus
von der EEG
"""

    safe_name = escape(display_name)
    safe_username = escape(username or '')
    safe_role = escape(role_label)
    safe_url = escape(invite_url)
    safe_expires = escape(expires_text)
    safe_org_name = escape(org_name)
    safe_org_email = escape(org_email)
    safe_org_address = escape(org_address)
    safe_org_website = escape(org_website)
    safe_logo_src = escape(logo_src) if logo_src else ''

    html_footer_website = (
        f'<br><a href="{safe_org_website}" style="color:#2b5e3a;text-decoration:none;">{safe_org_website}</a>'
        if org_website else ''
    )
    logo_html = (
        f'<img src="{safe_logo_src}" width="58" height="58" alt="{safe_org_name}" '
        'style="display:block;border-radius:8px;margin:0 0 12px 0;background:#ffffff;">'
        if logo_src else ''
    )
    body_html = f"""<!doctype html>
<html lang="de">
<body style="margin:0;padding:0;background:#f5f7f4;font-family:Arial,Helvetica,sans-serif;color:#1f2a24;">
  <div style="display:none;max-height:0;overflow:hidden;color:transparent;">
    Christian und Markus von der EEG laden Sie zum Portal ein.
  </div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f7f4;padding:28px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #dfe7df;">
          <tr>
            <td style="background:#2b5e3a;padding:24px 28px;color:#ffffff;">
              {logo_html}
              <div style="font-size:13px;letter-spacing:.04em;text-transform:uppercase;opacity:.85;">Einladung zum Portal</div>
              <h1 style="margin:8px 0 0 0;font-size:24px;line-height:1.25;font-weight:700;">{safe_org_name}</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:28px;">
              <p style="margin:0 0 16px 0;font-size:16px;line-height:1.6;">Hallo {safe_name},</p>
              <p style="margin:0 0 16px 0;font-size:16px;line-height:1.6;">
                Christian und Markus von der EEG haben für Sie einen Zugang zum <strong>{safe_org_name}</strong> eingerichtet.
              </p>
              <div style="background:#eef6ef;border-left:4px solid #2b5e3a;padding:16px 18px;margin:22px 0;border-radius:6px;">
                <p style="margin:0 0 8px 0;font-size:15px;line-height:1.5;"><strong>Ihre Zugangsdaten</strong></p>
                <p style="margin:0;font-size:15px;line-height:1.6;">Benutzername: <strong>{safe_username}</strong><br>Rolle: <strong>{safe_role}</strong></p>
              </div>
              <p style="margin:0 0 12px 0;font-size:16px;line-height:1.6;"><strong>So starten Sie:</strong></p>
              <ol style="margin:0 0 22px 20px;padding:0;font-size:16px;line-height:1.7;">
                <li>Einladungslink öffnen.</li>
                <li>Eigenes Passwort festlegen.</li>
                <li>Danach mit Ihrem Benutzernamen anmelden.</li>
              </ol>
              <p style="margin:0 0 24px 0;text-align:center;">
                <a href="{safe_url}" style="display:inline-block;background:#2b5e3a;color:#ffffff;text-decoration:none;font-weight:700;padding:13px 22px;border-radius:6px;font-size:16px;">Einladung annehmen</a>
              </p>
              <p style="margin:0 0 16px 0;font-size:14px;line-height:1.6;color:#58665e;">
                Der Link ist bis <strong>{safe_expires}</strong> gültig. Falls der Button nicht funktioniert, kopieren Sie diesen Link in Ihren Browser:
              </p>
              <p style="margin:0 0 22px 0;word-break:break-all;font-size:13px;line-height:1.5;color:#2b5e3a;">
                <a href="{safe_url}" style="color:#2b5e3a;">{safe_url}</a>
              </p>
              <p style="margin:0;font-size:16px;line-height:1.6;">
                Viele Grüße<br>
                <strong>Christian und Markus</strong><br>
                von der EEG
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 28px;background:#f0f4ef;border-top:1px solid #dfe7df;color:#6a766e;font-size:12px;line-height:1.5;text-align:center;">
              <strong>{safe_org_name}</strong><br>
              {safe_org_address}<br>
              <a href="mailto:{safe_org_email}" style="color:#2b5e3a;text-decoration:none;">{safe_org_email}</a>{html_footer_website}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return subject, body_text, body_html


def send_invitation_email(db, user_row, invite_url, invite_expires):
    """Sendet eine Portal-Einladung als HTML-Mail mit Plaintext-Fallback."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage

    recipient = (user_row['email'] or '').strip()
    if not _is_valid_email(recipient):
        raise RuntimeError('Keine gültige E-Mail-Adresse für diesen Benutzer hinterlegt.')

    mail_cfg = _get_valid_mail_config(db)
    public_cfg = get_public_config(db)
    member_name = user_row['member_name'] if 'member_name' in user_row.keys() else ''
    logo_cid = 'eeg-logo'
    subject, body_text, body_html = _build_invitation_email(
        member_name,
        user_row['username'],
        user_row['role'],
        invite_url,
        invite_expires,
        public_cfg,
        logo_src=f'cid:{logo_cid}',
    )

    msg = MIMEMultipart('related')
    msg['From'] = mail_cfg['from_header']
    msg['Reply-To'] = mail_cfg['reply_to_header']
    msg['To'] = recipient
    msg['Subject'] = subject

    msg_alt = MIMEMultipart('alternative')
    msg_alt.attach(MIMEText(body_text, 'plain', 'utf-8'))
    msg_alt.attach(MIMEText(body_html, 'html', 'utf-8'))
    msg.attach(msg_alt)

    logo_path = os.path.join(BASE_DIR, 'static', 'logo_small.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            logo = MIMEImage(f.read(), _subtype='png')
        logo.add_header('Content-ID', f'<{logo_cid}>')
        logo.add_header('Content-Disposition', 'inline', filename='eeg-logo.png')
        msg.attach(logo)

    _log_mail_send(mail_cfg, recipient, subject)
    with smtplib.SMTP(mail_cfg['smtp_host'], mail_cfg['smtp_port']) as server:
        if mail_cfg['smtp_tls']:
            server.starttls()
        server.login(mail_cfg['smtp_user'], mail_cfg['smtp_pass'])
        server.send_message(msg, from_addr=mail_cfg['from_address'], to_addrs=[recipient])


def _startup_mail_config_check():
    """Prüft Mail-Konfiguration beim Start und loggt das Ergebnis."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        cfg = _load_mail_config(db)
        ok, error = _validate_mail_config(cfg)
        if ok:
            app.logger.info('Mail config check passed on startup. SMTP user=%s, From=%s',
                            cfg.get('smtp_user'), cfg.get('from_header'))
        else:
            app.logger.error('Mail config invalid on startup: %s', error)
    finally:
        db.close()


# === User Model ===

class User(UserMixin):
    def __init__(self, id, username, is_admin=False, member_id=None, role='member'):
        self.id = id
        self.username = username
        self.is_admin = is_admin
        self.member_id = member_id
        self.role = role or ('admin' if is_admin else 'member')


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    row = db.execute("SELECT id, username, is_admin, member_id, role FROM users WHERE id=?",
                     (user_id,)).fetchone()
    if row:
        return User(row['id'], row['username'], row['is_admin'],
                    row['member_id'], row['role'])
    return None


def admin_required(f):
    """Decorator: Route nur für Admins zugänglich."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash('Zugriff nur für Administratoren.', 'danger')
            return redirect(url_for('portal_dashboard'))
        return f(*args, **kwargs)
    return decorated


# === Audit Logging ===

# Seitenaufrufe, die automatisch geloggt werden (GET-Requests)
_AUDIT_PAGE_ENDPOINTS = {
    'dashboard': 'Dashboard',
    'import_data': 'Import',
    'members_list': 'Mitglieder',
    'member_new': 'Neues Mitglied',
    'member_edit': 'Mitglied bearbeiten',
    'prices': 'Preise',
    'invoices_list': 'Abrechnungen',
    'invoice_new': 'Neue Abrechnung',
    'invoice_detail': 'Abrechnungsdetail',
    'reports': 'Reports',
    'settings': 'Einstellungen',
    'admin_backup': 'Backup',
    'admin_database': 'Datenbank-Wartung',
    'admin_users': 'Benutzerverwaltung',
    'payments': 'Überweisungen',
    'portal_dashboard': 'Portal: Übersicht',
    'portal_data': 'Portal: Meine Daten',
    'portal_invoices': 'Portal: Abrechnungen',
    'portal_contracts': 'Portal: Verträge',
}


def get_real_ip():
    """Echte Client-IP ermitteln (hinter Reverse-Proxy)."""
    # ProxyFix setzt remote_addr bereits korrekt, aber als Fallback:
    return request.remote_addr


def audit_log(action, detail=None, user_id=None, username=None):
    """Schreibt einen Eintrag ins Audit-Log."""
    try:
        db = get_db()
        uid = user_id
        uname = username
        if uid is None and has_request_context() and current_user and current_user.is_authenticated:
            uid = current_user.id
            uname = current_user.username
        db.execute(
            """INSERT INTO audit_log
               (timestamp, user_id, username, action, detail, ip, url, method)
               VALUES (?,?,?,?,?,?,?,?)""",
            (utc_now_string(), uid, uname, action, detail,
             get_real_ip() if has_request_context() else None,
             request.url if has_request_context() else None,
             request.method if has_request_context() else None))
        db.commit()
    except Exception:
        pass  # Audit-Log darf nie die App blockieren


@app.after_request
def audit_page_views(response):
    """Loggt Seitenaufrufe automatisch für authentifizierte User."""
    try:
        if (request.method == 'GET'
                and response.status_code == 200
                and current_user
                and current_user.is_authenticated
                and request.endpoint in _AUDIT_PAGE_ENDPOINTS):
            label = _AUDIT_PAGE_ENDPOINTS[request.endpoint]
            audit_log('page_view', label)
    except Exception:
        pass
    return response


# === Login Security ===
_login_attempts = {}  # {ip: {'count': int, 'last': float, 'locked_until': float}}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 Minuten


def _check_login_rate(ip):
    """Prüft ob eine IP gesperrt ist. Gibt verbleibende Sekunden zurück, oder 0."""
    import time
    info = _login_attempts.get(ip, {})
    locked_until = info.get('locked_until', 0)
    if locked_until > time.time():
        return int(locked_until - time.time())
    return 0


def _record_failed_login(ip):
    """Zählt fehlgeschlagene Login-Versuche und sperrt ggf."""
    import time
    now = time.time()
    info = _login_attempts.get(ip, {'count': 0, 'last': 0, 'locked_until': 0})
    # Reset nach 15 Minuten ohne Versuch
    if now - info.get('last', 0) > 900:
        info = {'count': 0, 'last': now, 'locked_until': 0}
    info['count'] = info.get('count', 0) + 1
    info['last'] = now
    if info['count'] >= MAX_LOGIN_ATTEMPTS:
        info['locked_until'] = now + LOCKOUT_SECONDS
    _login_attempts[ip] = info


def _reset_login_attempts(ip):
    _login_attempts.pop(ip, None)


# === Auth Routes ===

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('dashboard'))
        return redirect(url_for('portal_dashboard'))

    if request.method == 'GET' and request.args.get('csrf'):
        flash('Die Sitzung war nicht mehr gültig. Bitte erneut anmelden.', 'warning')

    ip = get_real_ip()
    locked_secs = _check_login_rate(ip)

    if request.method == 'POST':
        if locked_secs > 0:
            flash(f'Zu viele Fehlversuche. Bitte warten Sie {locked_secs} Sekunden.', 'danger')
            return render_template('login.html', locked_until=locked_secs)

        login_identifier = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        db = get_db()
        candidates = db.execute("""
            SELECT id, username, password_hash, is_admin, member_id, role
            FROM users
            WHERE LOWER(username)=? OR LOWER(email)=?
            ORDER BY
                CASE
                    WHEN invite_token IS NULL THEN 0
                    WHEN LOWER(username)=? THEN 1
                    ELSE 2
                END,
                id
        """, (login_identifier, login_identifier, login_identifier)).fetchall()
        row = None
        for candidate in candidates:
            if check_password_hash(candidate['password_hash'], password):
                row = candidate
                break
        if row:
            _reset_login_attempts(ip)
            user = User(row['id'], row['username'], row['is_admin'],
                        row['member_id'], row['role'])
            login_user(user)
            audit_log('login', f'Anmeldung erfolgreich (Rolle: {user.role})')
            next_page = request.args.get('next')
            if next_page and is_safe_redirect_url(next_page):
                return redirect(next_page)
            if user.is_admin:
                return redirect(url_for('dashboard'))
            return redirect(url_for('portal_dashboard'))
        _record_failed_login(ip)
        audit_log('login_failed', f'Fehlgeschlagener Login für "{login_identifier}"', user_id=0, username=login_identifier)
        remaining = MAX_LOGIN_ATTEMPTS - _login_attempts.get(ip, {}).get('count', 0)
        if remaining > 0:
            flash(f'Ungültiger Benutzername oder Passwort. Noch {remaining} Versuche.', 'danger')
        else:
            flash(f'Konto gesperrt für {LOCKOUT_SECONDS // 60} Minuten.', 'danger')
        locked_secs = _check_login_rate(ip)

    return render_template('login.html', locked_until=locked_secs if locked_secs > 0 else None)


@app.route('/logout')
@login_required
def logout():
    audit_log('logout', 'Abmeldung')
    logout_user()
    return redirect(url_for('login'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_pw = request.form.get('old_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        db = get_db()
        row = db.execute("SELECT password_hash FROM users WHERE id=?",
                         (current_user.id,)).fetchone()
        if not check_password_hash(row['password_hash'], old_pw):
            flash('Altes Passwort falsch.', 'danger')
        elif new_pw != confirm:
            flash('Neue Passwörter stimmen nicht überein.', 'danger')
        elif len(new_pw) < 6:
            flash('Passwort muss mindestens 6 Zeichen haben.', 'danger')
        else:
            db.execute("UPDATE users SET password_hash=? WHERE id=?",
                       (generate_password_hash(new_pw), current_user.id))
            db.commit()
            audit_log('password_change', 'Passwort geändert')
            flash('Passwort geändert.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')


# === Dashboard ===

@app.route('/')
@admin_required
def dashboard():
    db = get_db()
    stats = {}
    stats['members'] = db.execute("SELECT COUNT(*) FROM members WHERE active=1").fetchone()[0]
    stats['measurements'] = db.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    stats['batches'] = db.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
    stats['invoices'] = db.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]

    # Sortierung Dashboard
    imp_sort = request.args.get('imp_sort', 'imported_at')
    imp_dir = request.args.get('imp_dir', 'desc').lower()
    mon_sort = request.args.get('mon_sort', 'period_start')
    mon_dir = request.args.get('mon_dir', 'desc').lower()

    allowed_imp_sort = {'imported_at', 'source_file', 'period_start'}
    allowed_mon_sort = {'period_start', 'kwh'}
    if imp_sort not in allowed_imp_sort:
        imp_sort = 'imported_at'
    if mon_sort not in allowed_mon_sort:
        mon_sort = 'period_start'
    if imp_dir not in {'asc', 'desc'}:
        imp_dir = 'desc'
    if mon_dir not in {'asc', 'desc'}:
        mon_dir = 'asc'

    # Importe
    stats['last_imports'] = db.execute(f"""
        SELECT source_file, period_start, period_end, imported_at
        FROM import_batches ORDER BY {imp_sort} {imp_dir.upper()}
    """).fetchall()

    # Monatssummen
    order_col = 'kwh' if mon_sort == 'kwh' else 'b.period_start'
    stats['monthly'] = db.execute(f"""
        SELECT b.period_start, ROUND(SUM(m.value_kwh), 1) as kwh, COUNT(*) as cnt
        FROM measurements m
        JOIN import_batches b ON b.id = m.batch_id
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE mc.code = '1-1:2.9.0 G.03'
        GROUP BY b.period_start
        ORDER BY {order_col} {mon_dir.upper()}
    """).fetchall()

    return render_template('dashboard.html', stats=stats,
                           imp_sort=imp_sort, imp_dir=imp_dir,
                           mon_sort=mon_sort, mon_dir=mon_dir)


# === Import ===

@app.route('/import', methods=['GET', 'POST'])
@admin_required
def import_data():
    files_sort = request.args.get('files_sort', 'imported_at')
    files_dir = request.args.get('files_dir', 'asc').lower()
    values_sort = request.args.get('values_sort', 'imported_at')
    values_dir = request.args.get('values_dir', 'asc').lower()

    allowed_files_sort = {'period_start', 'source_file', 'imported_at'}
    allowed_values_sort = {'imported_at', 'filename', 'records_imported', 'status'}
    if files_sort not in allowed_files_sort:
        files_sort = 'imported_at'
    if values_sort not in allowed_values_sort:
        values_sort = 'imported_at'
    if files_dir not in {'asc', 'desc'}:
        files_dir = 'asc'
    if values_dir not in {'asc', 'desc'}:
        values_dir = 'asc'

    if request.method == 'POST':
        files = request.files.getlist('files')
        overwrite = request.form.get('overwrite') == '1'
        data_status = _valid_import_data_status(request.form.get('data_status'))
        results = []
        for f in files:
            if f and f.filename.lower().endswith('.xlsx'):
                filename = secure_filename(f.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                try:
                    f.save(filepath)
                    result = run_import(filepath, overwrite, data_status)
                except Exception as e:
                    app.logger.exception('Import upload handling failed for %s', filename)
                    result = {
                        'filename': filename,
                        'status': 'error',
                        'data_status': data_status,
                        'records': 0,
                        'overwritten': 0,
                        'error': str(e),
                        'imported_at': None,
                    }
                results.append(result)
                audit_log('import', f'Datei importiert: {filename} ({result["records"]} Datensätze, Status: {result["status"]})')
        db = get_db()
        imports = db.execute(f"""
            SELECT id, source_file, period_start, period_end, data_status, replaced_by_batch_id, replaced_at, imported_at
            FROM import_batches ORDER BY {files_sort} {files_dir.upper()}
        """).fetchall()
        import_values = db.execute(f"""
            SELECT id, filename, records_imported, records_overwritten, status, data_status, error_message, imported_by, imported_at
            FROM import_log ORDER BY {values_sort} {values_dir.upper()}
        """).fetchall()
        return render_template('import.html', results=results, imports=imports,
                               import_values=import_values,
                               files_sort=files_sort, files_dir=files_dir,
                               values_sort=values_sort, values_dir=values_dir)

    # Vorhandene Importe zeigen
    db = get_db()
    imports = db.execute(f"""
        SELECT id, source_file, period_start, period_end, data_status, replaced_by_batch_id, replaced_at, imported_at
        FROM import_batches ORDER BY {files_sort} {files_dir.upper()}
    """).fetchall()
    import_values = db.execute(f"""
        SELECT id, filename, records_imported, records_overwritten, status, data_status, error_message, imported_by, imported_at
        FROM import_log ORDER BY {values_sort} {values_dir.upper()}
    """).fetchall()
    return render_template('import.html', imports=imports, import_values=import_values,
                           files_sort=files_sort, files_dir=files_dir,
                           values_sort=values_sort, values_dir=values_dir)


def _valid_import_data_status(value):
    return 'final' if value == 'final' else 'provisional'


def _format_import_status_label(data_status):
    return 'Endgültig' if data_status == 'final' else 'Vorläufig'


def safe_invoice_pdf_filename(invoice_id, member_id, member_name):
    """Erzeugt einen Download-Dateinamen ohne daraus einen Serverpfad zu bauen."""
    safe_name = secure_filename(str(member_name or '').replace(' ', '_')) or f'mitglied_{member_id}'
    safe_name = safe_name[:80]
    return f'abrechnung_{int(invoice_id)}_{int(member_id)}_{safe_name}.pdf'


def _active_batches_for_period(db, period_start, period_end, data_status=None):
    params = [period_start, period_end]
    status_filter = ''
    if data_status:
        status_filter = ' AND data_status=?'
        params.append(data_status)
    return db.execute(f"""
        SELECT *
        FROM import_batches
        WHERE replaced_at IS NULL
          AND period_start = ?
          AND period_end = ?
          {status_filter}
        ORDER BY id
    """, params).fetchall()


def _delete_batch_measurements(db, batch_id):
    count = db.execute("SELECT COUNT(*) FROM measurements WHERE batch_id=?", (batch_id,)).fetchone()[0]
    db.execute("DELETE FROM measurements WHERE batch_id=?", (batch_id,))
    return count


def _mark_batches_replaced(db, batches, replacement_batch_id):
    for batch in batches:
        _delete_batch_measurements(db, batch['id'])
        db.execute("""
            UPDATE import_batches
            SET replaced_by_batch_id=?, replaced_at=datetime('now')
            WHERE id=?
        """, (replacement_batch_id, batch['id']))


def run_import(filepath, overwrite=False, data_status='final'):
    """Importiert eine Excel-Datei. Bei overwrite=True werden bestehende Daten überschrieben."""
    sys.path.insert(0, os.path.join(BASE_DIR, '..'))
    from import_eda import import_file, parse_filename

    data_status = _valid_import_data_status(data_status)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    ensure_import_schema(db)

    filename = os.path.basename(filepath)
    records_overwritten = 0
    new_batch_id = None
    replacement_candidates = []

    try:
        info = parse_filename(filename)
        period_start = info.get('period_start')
        period_end = info.get('period_end')
        if not period_start or not period_end:
            raise ValueError('Der Zeitraum konnte aus dem Dateinamen nicht erkannt werden.')

        active_final = _active_batches_for_period(db, period_start, period_end, 'final')
        active_provisional = _active_batches_for_period(db, period_start, period_end, 'provisional')

        if data_status == 'provisional' and active_final and not overwrite:
            raise ValueError('Für diesen Zeitraum sind bereits endgültige Daten vorhanden. Vorläufige Daten werden nicht darüber importiert.')
        if data_status == 'final' and active_final and not overwrite:
            raise ValueError('Für diesen Zeitraum sind bereits endgültige Daten vorhanden. Zum Ersetzen bitte Überschreiben aktivieren.')

        if data_status == 'final':
            replacement_candidates = list(active_provisional)
            if overwrite:
                replacement_candidates.extend(active_final)
        elif overwrite:
            replacement_candidates = list(active_provisional)

        count = import_file(filepath, db, allow_duplicate=bool(replacement_candidates or overwrite))
        new_batch = db.execute("""
            SELECT id
            FROM import_batches
            WHERE source_file=? AND period_start=? AND period_end=? AND replaced_at IS NULL
            ORDER BY id DESC
            LIMIT 1
        """, (filename, period_start, period_end)).fetchone()
        if new_batch:
            new_batch_id = new_batch['id']
            db.execute("UPDATE import_batches SET data_status=? WHERE id=?", (data_status, new_batch_id))

        if new_batch_id and replacement_candidates:
            records_overwritten = sum(_delete_batch_measurements(db, batch['id']) for batch in replacement_candidates)
            for batch in replacement_candidates:
                db.execute("""
                    UPDATE import_batches
                    SET replaced_by_batch_id=?, replaced_at=datetime('now')
                    WHERE id=?
                """, (new_batch_id, batch['id']))

        db.commit()
        status = 'success'
        error = None
    except Exception as e:
        status = 'error'
        count = 0
        error = str(e)
        app.logger.exception('Import failed for %s', filename)
    finally:
        # Log
        cur = db.execute("""INSERT INTO import_log (filename, records_imported, records_overwritten, status, data_status, error_message, imported_by)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (filename, count, records_overwritten, status, data_status, error,
                          current_user.username if has_request_context() and current_user and current_user.is_authenticated else 'system'))
        log_row = db.execute("SELECT imported_at FROM import_log WHERE id=?", (cur.lastrowid,)).fetchone()
        db.commit()
        db.close()

    return {'filename': filename, 'status': status, 'records': count,
            'data_status': data_status,
            'overwritten': records_overwritten, 'error': error,
            'imported_at': (log_row['imported_at'] if log_row else None)}


# === Mitglieder ===

@app.route('/members')
@admin_required
def members_list():
    db = get_db()
    members = db.execute("""
        SELECT * FROM members ORDER BY name
    """).fetchall()
    return render_template('members.html', members=members)


@app.route('/members/new', methods=['GET', 'POST'])
@admin_required
def member_new():
    if request.method == 'POST':
        db = get_db()
        newsletter_optout = 0 if form_switch_enabled('newsletter_enabled') else 1
        db.execute("""INSERT INTO members (name, email, phone, address_street, address_zip, address_city,
                      einspeiser_zp, einspeiser_ab, bezug_zp, bezug_ab, teilnahme,
                      iban, bic, account_holder, newsletter_optout, updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                   (request.form['name'], request.form.get('email'),
                    request.form.get('phone'),
                    request.form.get('address_street'), request.form.get('address_zip'),
                    request.form.get('address_city'),
                    request.form.get('einspeiser_zp') or None,
                    request.form.get('einspeiser_ab') or None,
                    request.form.get('bezug_zp') or None,
                    request.form.get('bezug_ab') or None,
                    float(request.form.get('teilnahme', 1.0)),
                    request.form.get('iban') or None,
                    request.form.get('bic') or None,
                    request.form.get('account_holder') or None,
                    newsletter_optout))
        db.commit()
        audit_log('member_create', f'Mitglied angelegt: {request.form["name"]}')
        flash('Mitglied angelegt.', 'success')
        return redirect(url_for('members_list'))
    return render_template('member_edit.html', member=None)


@app.route('/members/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def member_edit(id):
    db = get_db()
    if request.method == 'POST':
        newsletter_optout = 0 if form_switch_enabled('newsletter_enabled') else 1
        db.execute("""UPDATE members SET name=?, email=?, phone=?, address_street=?, address_zip=?,
                      address_city=?, einspeiser_zp=?, einspeiser_ab=?, bezug_zp=?,
                      bezug_ab=?, teilnahme=?, active=?, iban=?, bic=?, account_holder=?,
                      newsletter_optout=?,
                      updated_at=datetime('now')
                      WHERE id=?""",
                   (request.form['name'], request.form.get('email'),
                    request.form.get('phone'),
                    request.form.get('address_street'), request.form.get('address_zip'),
                    request.form.get('address_city'),
                    request.form.get('einspeiser_zp') or None,
                    request.form.get('einspeiser_ab') or None,
                    request.form.get('bezug_zp') or None,
                    request.form.get('bezug_ab') or None,
                    float(request.form.get('teilnahme', 1.0)),
                    1 if request.form.get('active') else 0,
                    request.form.get('iban') or None,
                    request.form.get('bic') or None,
                    request.form.get('account_holder') or None,
                    newsletter_optout,
                    id))
        db.commit()
        audit_log('member_edit', f'Mitglied bearbeitet: {request.form["name"]} (ID {id})')
        flash('Mitglied aktualisiert.', 'success')
        return redirect(url_for('members_list'))
    member = db.execute("SELECT * FROM members WHERE id=?", (id,)).fetchone()
    return render_template('member_edit.html', member=member)


@app.route('/members/<int:id>/delete', methods=['POST'])
@admin_required
def member_delete(id):
    db = get_db()
    member = db.execute("SELECT name FROM members WHERE id=?", (id,)).fetchone()
    db.execute("UPDATE members SET active=0, updated_at=datetime('now') WHERE id=?", (id,))
    db.commit()
    audit_log('member_delete', f'Mitglied deaktiviert: {member["name"]} (ID {id})')
    flash('Mitglied deaktiviert.', 'success')
    return redirect(url_for('members_list'))


# === Preise ===

@app.route('/prices', methods=['GET', 'POST'])
@admin_required
def prices():
    db = get_db()
    if request.method == 'POST':
        db.execute("""INSERT INTO prices (valid_from, valid_to, price_consumption, price_generation, description)
                      VALUES (?, ?, ?, ?, ?)""",
                   (request.form['valid_from'], request.form['valid_to'],
                    float(request.form['price_consumption']),
                    float(request.form['price_generation']),
                    request.form.get('description', '')))
        db.commit()
        audit_log('price_create', f'Preis angelegt: {request.form["valid_from"]} - {request.form["valid_to"]}')
        flash('Preis angelegt.', 'success')
        return redirect(url_for('prices'))
    all_prices = db.execute("SELECT * FROM prices ORDER BY valid_from DESC").fetchall()
    # Prüfe ob es Abrechnungen für die Preis-Zeiträume gibt
    invoices_for_prices = {}
    for p in all_prices:
        inv = db.execute("""SELECT id, period_from, period_to FROM invoices
                           WHERE period_from <= ? AND period_to >= ?""",
                        (p['valid_to'], p['valid_from'])).fetchone()
        if inv:
            invoices_for_prices[p['id']] = inv
    return render_template('prices.html', prices=all_prices, invoices_for_prices=invoices_for_prices)


@app.route('/prices/<int:id>/edit', methods=['POST'])
@admin_required
def price_edit(id):
    db = get_db()
    price = db.execute("SELECT * FROM prices WHERE id=?", (id,)).fetchone()
    if not price:
        flash('Preis nicht gefunden.', 'danger')
        return redirect(url_for('prices'))
    db.execute("""UPDATE prices SET valid_from=?, valid_to=?, price_consumption=?,
                  price_generation=?, description=? WHERE id=?""",
               (request.form['valid_from'], request.form['valid_to'],
                float(request.form['price_consumption']),
                float(request.form['price_generation']),
                request.form.get('description', ''), id))
    db.commit()
    audit_log('price_edit', f'Preis bearbeitet: {request.form["valid_from"]} - {request.form["valid_to"]} (ID {id})')
    # Warnung wenn Abrechnung existiert
    inv = db.execute("""SELECT id FROM invoices
                       WHERE period_from <= ? AND period_to >= ?""",
                    (request.form['valid_to'], request.form['valid_from'])).fetchone()
    if inv:
        flash(f'Achtung: Für diesen Zeitraum existiert bereits Abrechnung #{inv["id"]}. '
              f'Es muss eine neue Abrechnung erstellt werden, damit die Preisänderung wirksam wird!', 'warning')
    else:
        flash('Preis aktualisiert.', 'success')
    return redirect(url_for('prices'))


@app.route('/prices/<int:id>/duplicate', methods=['POST'])
@admin_required
def price_duplicate(id):
    """Preis in die nächste Periode (Quartal) duplizieren."""
    from datetime import timedelta
    db = get_db()
    price = db.execute("SELECT * FROM prices WHERE id=?", (id,)).fetchone()
    if not price:
        flash('Preis nicht gefunden.', 'danger')
        return redirect(url_for('prices'))
    # Nächstes Quartal berechnen
    old_from = datetime.strptime(price['valid_from'], '%Y-%m-%d').date()
    old_to = datetime.strptime(price['valid_to'], '%Y-%m-%d').date()
    duration = (old_to - old_from).days + 1
    new_from = old_to + timedelta(days=1)
    new_to = new_from + timedelta(days=duration - 1)
    # Duplikat prüfen
    existing = db.execute("SELECT id FROM prices WHERE valid_from=? AND valid_to=?",
                          (new_from.isoformat(), new_to.isoformat())).fetchone()
    if existing:
        flash(f'Für den Zeitraum {new_from} – {new_to} existiert bereits ein Preis.', 'warning')
        return redirect(url_for('prices'))
    # Neue Periode: Beschreibung anpassen
    new_desc = price['description'] or ''
    # Versuche Q-Nummer hochzuzählen
    import re
    q_match = re.search(r'Q(\d)/(\d{4})', new_desc)
    if q_match:
        q_num = int(q_match.group(1))
        q_year = int(q_match.group(2))
        if q_num < 4:
            new_desc = new_desc.replace(q_match.group(0), f'Q{q_num+1}/{q_year}')
        else:
            new_desc = new_desc.replace(q_match.group(0), f'Q1/{q_year+1}')
    db.execute("""INSERT INTO prices (valid_from, valid_to, price_consumption, price_generation, description)
                  VALUES (?, ?, ?, ?, ?)""",
               (new_from.isoformat(), new_to.isoformat(),
                price['price_consumption'], price['price_generation'], new_desc))
    db.commit()
    audit_log('price_duplicate', f'Preis dupliziert: {new_from} - {new_to} (von ID {id})')
    flash(f'Preis in nächste Periode kopiert: {new_from} – {new_to}', 'success')
    return redirect(url_for('prices'))


@app.route('/prices/<int:id>/delete', methods=['POST'])
@admin_required
def price_delete(id):
    db = get_db()
    price = db.execute("SELECT valid_from, valid_to FROM prices WHERE id=?", (id,)).fetchone()
    db.execute("DELETE FROM prices WHERE id=?", (id,))
    db.commit()
    audit_log('price_delete', f'Preis gelöscht: {price["valid_from"]} - {price["valid_to"]}' if price else f'Preis ID {id} gelöscht')
    flash('Preis gelöscht.', 'success')
    return redirect(url_for('prices'))


def get_price_for_date(db, target_date):
    """Ermittelt den gültigen Preis für ein Datum."""
    row = db.execute("""
        SELECT price_consumption, price_generation FROM prices
        WHERE valid_from <= ? AND valid_to >= ?
        ORDER BY valid_from DESC LIMIT 1
    """, (target_date, target_date)).fetchone()
    if row:
        return row['price_consumption'], row['price_generation']
    # Fallback: Letzten eingetragenen Preis verwenden
    last = db.execute("SELECT price_consumption, price_generation FROM prices ORDER BY valid_from DESC LIMIT 1").fetchone()
    if last:
        return last['price_consumption'], last['price_generation']
    return 12.0, 10.0  # Absoluter Fallback (aktueller Standardpreis 2026)


def get_import_status_for_period(db, period_from, period_to):
    """Prüft, ob fuer einen Abrechnungszeitraum nur finale aktive Importdaten vorliegen."""
    ts_from = period_from + "T00:00:00" if "T" not in period_from else period_from
    ts_to = period_to + "T23:45:00" if "T" not in period_to else period_to
    batches = db.execute("""
        SELECT id, source_file, period_start, period_end, data_status
        FROM import_batches
        WHERE replaced_at IS NULL
          AND period_start <= ?
          AND period_end >= ?
        ORDER BY period_start, id
    """, (ts_to, ts_from)).fetchall()
    has_final = any(batch['data_status'] == 'final' for batch in batches)
    provisional = [batch for batch in batches if batch['data_status'] != 'final']
    if not batches:
        return {
            'data_status': 'provisional',
            'is_final': False,
            'reason': 'Für diesen Zeitraum wurden noch keine Messdaten importiert.',
            'batches': [],
            'provisional_batches': [],
        }
    if provisional:
        return {
            'data_status': 'provisional',
            'is_final': False,
            'reason': 'Im Zeitraum sind noch vorläufige Messdaten vorhanden.',
            'batches': batches,
            'provisional_batches': provisional,
        }
    if not has_final:
        return {
            'data_status': 'provisional',
            'is_final': False,
            'reason': 'Es wurden keine endgültigen Messdaten für diesen Zeitraum gefunden.',
            'batches': batches,
            'provisional_batches': [],
        }
    return {
        'data_status': 'final',
        'is_final': True,
        'reason': '',
        'batches': batches,
        'provisional_batches': [],
    }


def invoice_finalization_blocker(db, invoice):
    """Liefert eine Fehlermeldung, wenn eine Abrechnung nicht finalisiert/versendet werden darf."""
    import_status = get_import_status_for_period(db, invoice['period_from'], invoice['period_to'])
    invoice_data_status = invoice['data_status'] if 'data_status' in invoice.keys() else 'final'
    if invoice_data_status != 'final':
        if import_status['is_final']:
            return 'Diese Abrechnung wurde mit vorläufigen Daten berechnet. Bitte zuerst neu berechnen, danach kann sie versendet werden.'
        return 'Diese Abrechnung basiert auf vorläufigen Messdaten. Versand und Abschluss sind erst mit endgültigen Daten möglich.'
    if not import_status['is_final']:
        return import_status['reason'] or 'Für diesen Zeitraum liegen noch keine endgültigen Messdaten vor.'
    return ''


def get_invoice_carryovers(db, invoice_id, member_id=None):
    """Liefert Finanzvortraege einer Abrechnung, optional fuer ein Mitglied."""
    params = [invoice_id]
    member_filter = ''
    if member_id is not None:
        member_filter = 'AND c.member_id=?'
        params.append(member_id)
    return db.execute(f"""
        SELECT c.*, m.name AS member_name, m.email AS member_email,
               src.period_from AS source_period_from,
               src.period_to AS source_period_to
        FROM invoice_carryovers c
        JOIN members m ON m.id = c.member_id
        JOIN invoices src ON src.id = c.source_invoice_id
        WHERE c.invoice_id=?
          {member_filter}
        ORDER BY m.name, src.period_from, c.source_invoice_id
    """, params).fetchall()


def get_invoice_carryover_map(db, invoice_id):
    """Gruppiert Vortraege nach Mitglied fuer Detailansichten und Zahlungslogik."""
    carryovers = get_invoice_carryovers(db, invoice_id)
    grouped = {}
    for row in carryovers:
        member_id = row['member_id']
        bucket = grouped.setdefault(member_id, {'total': 0.0, 'rows': []})
        bucket['total'] = round(bucket['total'] + row['amount_eur'], 2)
        bucket['rows'].append(row)
    return grouped


def calculate_carryovers_for_period(db, period_from):
    """Berechnet offene Vorperioden, die in eine neue Abrechnung uebernommen werden."""
    carryovers = []
    for row in get_payment_rows(db):
        if row['period_to'] >= period_from:
            continue
        if row.get('invoice_status') not in {'sent', 'finalized'}:
            continue
        if row['paid'] or row.get('is_settled_by_carryover'):
            continue
        if abs(row['net_total']) < 0.005:
            continue
        carryovers.append({
            'member_id': row['member_id'],
            'source_invoice_id': row['invoice_id'],
            'amount': round(row['net_total'], 2),
            'description': 'Buchungsrückstand aus Vorperioden' if row['net_total'] > 0 else 'Guthaben aus Vorperioden',
        })
    return carryovers


def save_invoice_carryovers(db, invoice_id, carryovers):
    for carryover in carryovers:
        db.execute("""
            INSERT OR REPLACE INTO invoice_carryovers (
                invoice_id, member_id, source_invoice_id, amount_eur, description
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            invoice_id,
            carryover['member_id'],
            carryover['source_invoice_id'],
            carryover['amount'],
            carryover.get('description') or '',
        ))


def invoice_recipient_rows(db, invoice_id):
    """Mitglieder, die Positionen oder einen Finanzvortrag in der Abrechnung haben."""
    return db.execute("""
        SELECT m.id AS member_id, m.name, m.email
        FROM members m
        WHERE m.id IN (
            SELECT member_id FROM invoice_items WHERE invoice_id=?
            UNION
            SELECT member_id FROM invoice_carryovers WHERE invoice_id=?
        )
        ORDER BY m.name
    """, (invoice_id, invoice_id)).fetchall()


# === Abrechnung ===

@app.route('/invoices')
@admin_required
def invoices_list():
    db = get_db()
    invoices = db.execute("SELECT * FROM invoices ORDER BY period_from DESC").fetchall()
    return render_template('invoices.html', invoices=invoices)


@app.route('/invoices/new', methods=['GET', 'POST'])
@admin_required
def invoice_new():
    if request.method == 'POST':
        period_from = request.form['period_from']
        period_to = request.form['period_to']
        db = get_db()

        # Duplikat-Prüfung: Keine überlappenden Abrechnungen erlauben
        existing = db.execute("""
            SELECT id, period_from, period_to FROM invoices
            WHERE period_from <= ? AND period_to >= ?
        """, (period_to, period_from)).fetchone()
        if existing:
            flash(f'Es existiert bereits eine Abrechnung für diesen Zeitraum '
                  f'(Nr. {existing["id"]}: {existing["period_from"]} – {existing["period_to"]}). '
                  f'Pro Quartal ist nur eine Abrechnung zulässig.', 'danger')
            return redirect(url_for('invoice_new'))

        # Preise für Zeitraum
        price_cons, price_gen = get_price_for_date(db, period_from)
        import_status = get_import_status_for_period(db, period_from, period_to)

        # Abrechnung berechnen
        result = calculate_billing(db, period_from, period_to, price_cons, price_gen)

        # Speichern
        cur = db.execute("""INSERT INTO invoices (period_from, period_to, total_kwh_traded,
                            total_income, total_expense, total_margin, data_status)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (period_from, period_to, result['total_kwh'],
                          result['total_income'], result['total_expense'], result['total_margin'],
                          import_status['data_status']))
        invoice_id = cur.lastrowid

        # Einzelpositionen
        for item in result['items']:
            db.execute("""INSERT INTO invoice_items (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur)
                          VALUES (?, ?, ?, ?, ?, ?)""",
                       (invoice_id, item['member_id'], item['type'],
                        item['kwh'], item['price'], item['amount']))
        save_invoice_carryovers(db, invoice_id, result['carryovers'])
        db.commit()
        audit_log('invoice_create', f'Abrechnung #{invoice_id} erstellt: {period_from} - {period_to} ({result["total_kwh"]:.1f} kWh)')
        carryover_total = round(sum(item['amount'] for item in result['carryovers']), 2)
        carryover_info = f' Finanzvortrag: {carryover_total:.2f} EUR.' if result['carryovers'] else ''
        if import_status['is_final']:
            flash(f'Abrechnung #{invoice_id} erstellt ({result["total_kwh"]:.1f} kWh).{carryover_info}', 'success')
        else:
            flash(f'Vorläufige Abrechnung #{invoice_id} erstellt ({result["total_kwh"]:.1f} kWh).{carryover_info} Versand und Abschluss sind gesperrt, bis endgültige Daten importiert und die Abrechnung neu berechnet wurde.', 'warning')
        return redirect(url_for('invoice_detail', id=invoice_id))

    # Quartalsvorschläge
    today = date.today()
    q_month = ((today.month - 1) // 3) * 3 + 1
    q_start = date(today.year, q_month, 1)
    if q_month > 3:
        prev_q_start = date(today.year, q_month - 3, 1)
    else:
        prev_q_start = date(today.year - 1, 10, 1)
    prev_q_end = date(q_start.year, q_start.month, 1)
    from calendar import monthrange
    prev_end_month = q_month - 1 if q_month > 1 else 12
    prev_end_year = today.year if q_month > 1 else today.year - 1
    _, last_day = monthrange(prev_end_year, prev_end_month)
    prev_q_end = date(prev_end_year, prev_end_month, last_day)

    return render_template('invoice_new.html',
                           suggested_from=prev_q_start.isoformat(),
                           suggested_to=prev_q_end.isoformat())


@app.route('/invoices/<int:id>')
@admin_required
def invoice_detail(id):
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id=?", (id,)).fetchone()
    items = db.execute("""
        SELECT ii.*, m.name as member_name, m.email as member_email
        FROM invoice_items ii
        JOIN members m ON m.id = ii.member_id
        WHERE ii.invoice_id = ?
        ORDER BY m.name, ii.type
    """, (id,)).fetchall()
    # Pro Mitglied zusammenfassen
    members_map = {}
    for item in items:
        mid = item['member_id']
        if mid not in members_map:
            members_map[mid] = {
                'member_id': mid,
                'member_name': item['member_name'],
                'member_email': item['member_email'],
                'cons_kwh': 0, 'cons_eur': 0, 'cons_price': 0,
                'gen_kwh': 0, 'gen_eur': 0, 'gen_price': 0,
            }
        if item['type'] == 'consumption':
            members_map[mid]['cons_kwh'] = item['kwh']
            members_map[mid]['cons_eur'] = item['amount_eur']
            members_map[mid]['cons_price'] = item['price_per_kwh']
        else:
            members_map[mid]['gen_kwh'] = item['kwh']
            members_map[mid]['gen_eur'] = item['amount_eur']
            members_map[mid]['gen_price'] = item['price_per_kwh']
    for m in members_map.values():
        m['energy_net_eur'] = round(m['cons_eur'] - m['gen_eur'], 2)
        m['carryover_eur'] = 0.0
        m['carryovers'] = []

    carryover_map = get_invoice_carryover_map(db, id)
    for mid, data in carryover_map.items():
        if mid not in members_map:
            first = data['rows'][0]
            members_map[mid] = {
                'member_id': mid,
                'member_name': first['member_name'],
                'member_email': first['member_email'],
                'cons_kwh': 0, 'cons_eur': 0, 'cons_price': 0,
                'gen_kwh': 0, 'gen_eur': 0, 'gen_price': 0,
                'energy_net_eur': 0.0,
            }
        members_map[mid]['carryover_eur'] = data['total']
        members_map[mid]['carryovers'] = data['rows']

    for m in members_map.values():
        m.setdefault('energy_net_eur', round(m['cons_eur'] - m['gen_eur'], 2))
        m.setdefault('carryover_eur', 0.0)
        m.setdefault('carryovers', [])
        m['net_eur'] = round(m['energy_net_eur'] + m['carryover_eur'], 2)
    member_rows = sorted(members_map.values(), key=lambda x: x['member_name'])

    emails = db.execute("""
        SELECT el.*, m.name as member_name
        FROM email_log el
        LEFT JOIN members m ON m.id = el.member_id
        WHERE el.invoice_id=? ORDER BY el.sent_at DESC
    """, (id,)).fetchall()

    # E-Mail-Status pro Mitglied ermitteln
    sent_members = set()
    for e in emails:
        if e['status'] == 'sent' and e['member_id']:
            sent_members.add(e['member_id'])
    for m in member_rows:
        m['email_sent'] = m['member_id'] in sent_members

    import_status = get_import_status_for_period(db, invoice['period_from'], invoice['period_to'])
    finalization_blocker = invoice_finalization_blocker(db, invoice)
    return render_template('invoice_detail.html', invoice=invoice, items=items,
                           member_rows=member_rows, emails=emails,
                           import_status=import_status,
                           finalization_blocker=finalization_blocker)


@app.route('/invoices/<int:id>/regenerate', methods=['POST'])
@admin_required
def invoice_regenerate(id):
    """Abrechnung neu berechnen (z.B. nach Preisänderung)."""
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id=?", (id,)).fetchone()
    if not invoice:
        flash('Abrechnung nicht gefunden.', 'danger')
        return redirect(url_for('invoices_list'))

    period_from = invoice['period_from']
    period_to = invoice['period_to']

    # Aktuelle Preise für Zeitraum laden
    price_cons, price_gen = get_price_for_date(db, period_from)
    import_status = get_import_status_for_period(db, period_from, period_to)

    # Alte Items und Finanzvortraege löschen
    db.execute("DELETE FROM invoice_items WHERE invoice_id=?", (id,))
    db.execute("DELETE FROM invoice_carryovers WHERE invoice_id=?", (id,))

    # Neu berechnen
    result = calculate_billing(db, period_from, period_to, price_cons, price_gen)

    # Invoice-Kopf aktualisieren
    db.execute("""UPDATE invoices SET total_kwh_traded=?, total_income=?, total_expense=?,
                  total_margin=?, data_status=?, status='draft', finalized_at=NULL WHERE id=?""",
               (result['total_kwh'], result['total_income'], result['total_expense'],
                result['total_margin'], import_status['data_status'], id))

    # Neue Einzelpositionen
    for item in result['items']:
        db.execute("""INSERT INTO invoice_items (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (id, item['member_id'], item['type'],
                    item['kwh'], item['price'], item['amount']))
    save_invoice_carryovers(db, id, result['carryovers'])
    db.commit()
    audit_log('invoice_regenerate', f'Abrechnung #{id} neu berechnet: {period_from} - {period_to} '
              f'(Verbrauch: {price_cons} ct, Erzeugung: {price_gen} ct, {result["total_kwh"]:.1f} kWh)')
    if import_status['is_final']:
        flash(f'Abrechnung #{id} wurde mit endgültigen Daten und aktuellen Preisen '
              f'(Verbrauch: {price_cons} ct/kWh, Erzeugung: {price_gen} ct/kWh) neu berechnet.', 'success')
    else:
        flash(f'Abrechnung #{id} wurde vorläufig neu berechnet. Versand und Abschluss bleiben gesperrt, bis endgültige Daten importiert wurden.', 'warning')
    return redirect(url_for('invoice_detail', id=id))


@app.route('/invoices/<int:id>/pdf/<int:member_id>')
@login_required
def invoice_pdf(id, member_id):
    """PDF für ein Mitglied generieren (A4, mehrseitig)."""
    # Members dürfen nur eigene PDFs abrufen
    if not current_user.is_admin and current_user.member_id != member_id:
        audit_log('pdf_access_denied', f'PDF-Zugriff verweigert: Rechnung {id}, Mitglied {member_id}')
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('portal_dashboard'))
    audit_log('pdf_download', f'PDF heruntergeladen: Rechnung {id}, Mitglied {member_id}')
    import math
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id=?", (id,)).fetchone()
    member = db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    items = db.execute("""
        SELECT * FROM invoice_items
        WHERE invoice_id=? AND member_id=?
    """, (id, member_id)).fetchall()
    carryovers = get_invoice_carryovers(db, id, member_id)
    carryover_total = round(sum(row['amount_eur'] for row in carryovers), 2)

    # --- Nettobetrag berechnen (Bezug - Gutschrift) ---
    energy_net_total = 0
    for item in items:
        if item['type'] == 'consumption':
            energy_net_total += item['amount_eur']
        else:
            energy_net_total -= item['amount_eur']
    net_total = round(energy_net_total + carryover_total, 2)

    # --- EPC QR Code für Überweisung ---
    qr_data_uri = ''
    if net_total > 0:
        qr_data_uri = generate_epc_qr(net_total, invoice, member)

    # --- Seite 2: Mitglieder-Statistiken ---
    member_stats = get_member_stats(db, member, invoice['period_from'], invoice['period_to'])

    # --- Seite 3: Community-Statistiken ---
    community_stats = get_community_stats(db, invoice)

    # --- Seite 4: Ersparnis-Berechnung ---
    savings = calculate_member_savings(member_stats, items)
    public_cfg = get_public_config(db)

    # Logo als base64 für PDF-Einbettung
    import base64
    logo_path = os.path.join(BASE_DIR, 'static', 'logo_small.png')
    with open(logo_path, 'rb') as f:
        logo_b64 = 'data:image/png;base64,' + base64.b64encode(f.read()).decode('ascii')

    # --- Pie Chart SVG generieren ---
    def generate_pie_svg(data, colors, size=120):
        """Erzeugt ein SVG-Tortendiagramm."""
        total = sum(d['value'] for d in data)
        if total == 0:
            return ''
        cx, cy, r = size/2, size/2, size/2 - 4
        svg_parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">']
        start_angle = -90
        for i, d in enumerate(data):
            if d['value'] == 0:
                continue
            pct = d['value'] / total
            angle = pct * 360
            end_angle = start_angle + angle
            large_arc = 1 if angle > 180 else 0
            x1 = cx + r * math.cos(math.radians(start_angle))
            y1 = cy + r * math.sin(math.radians(start_angle))
            x2 = cx + r * math.cos(math.radians(end_angle))
            y2 = cy + r * math.sin(math.radians(end_angle))
            color = colors[i % len(colors)]
            if pct >= 0.9999:
                svg_parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')
            else:
                svg_parts.append(f'<path d="M {cx},{cy} L {x1:.2f},{y1:.2f} A {r},{r} 0 {large_arc} 1 {x2:.2f},{y2:.2f} Z" fill="{color}"/>')
            start_angle = end_angle
        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)

    # Pie: Energieverteilung Bezug (pro Mitglied)
    pie_colors = ['#2b7a78', '#3aafa9', '#5cbdb9', '#81cdc6', '#a6ddd6',
                  '#17252a', '#4e8a7a', '#7cc4b5', '#b0e0d6', '#d4f0eb']
    pie_consumption_data = [{'label': m['name'], 'value': m['kwh']}
                            for m in community_stats['member_consumption']]
    pie_consumption_svg = generate_pie_svg(pie_consumption_data, pie_colors, 130)

    # Pie: Erzeugung
    pie_gen_colors = ['#ff9800', '#ffc107', '#ffb74d', '#ffe082', '#fff3e0']
    pie_generation_data = [{'label': m['name'], 'value': m['kwh']}
                           for m in community_stats.get('member_generation', [])]
    pie_generation_svg = generate_pie_svg(pie_generation_data, pie_gen_colors, 130)

    # Pie: Monatlicher Verbrauch des Mitglieds
    pie_monthly_colors = ['#1a535c', '#2b7a78', '#3aafa9', '#5cbdb9', '#7ed6c9',
                          '#a0e8dd', '#c2f5ed', '#17252a', '#4e8a7a', '#81cdc6', '#b0e0d6', '#d4f0eb']
    pie_monthly_data = [{'label': m['label'], 'value': m['consumption']}
                        for m in member_stats['monthly_data']]
    pie_monthly_svg = generate_pie_svg(pie_monthly_data, pie_monthly_colors, 130)

    html = render_template('invoice_pdf.html',
                           invoice=invoice, member=member, items=items,
                           carryovers=carryovers,
                           member_stats=member_stats, community_stats=community_stats,
                           energy_net_total=round(energy_net_total, 2),
                           carryover_total=carryover_total,
                           net_total=net_total, qr_data_uri=qr_data_uri,
                           savings=savings, logo_b64=logo_b64,
                           public_cfg=public_cfg,
                           pie_consumption_svg=pie_consumption_svg,
                           pie_generation_svg=pie_generation_svg,
                           pie_monthly_svg=pie_monthly_svg,
                           pie_consumption_data=pie_consumption_data,
                           pie_generation_data=pie_generation_data,
                           pie_monthly_data=pie_monthly_data,
                           pie_colors=pie_colors,
                           pie_gen_colors=pie_gen_colors,
                           pie_monthly_colors=pie_monthly_colors)

    from weasyprint import HTML
    pdf_filename = safe_invoice_pdf_filename(id, member_id, member['name'])
    pdf_bytes = HTML(string=html, base_url=BASE_DIR).write_pdf()

    return send_file(io.BytesIO(pdf_bytes), as_attachment=True,
                     download_name=pdf_filename, mimetype='application/pdf')


def generate_epc_qr(amount, invoice, member):
    """Generiert einen EPC/GiroCode QR-Code als data URI (base64 PNG)."""
    import qrcode
    import io
    import base64
    cfg = get_public_config(get_db())
    bic = cfg['payment_bic'].replace(' ', '').strip()
    iban = cfg['payment_iban'].replace(' ', '').strip()
    recipient = cfg['payment_recipient'].strip()
    if not bic or not iban:
        return ''

    # EPC QR Code Standard (EPC069-12)
    epc_data = '\n'.join([
        'BCD',                          # Service Tag
        '002',                          # Version
        '1',                            # Encoding (UTF-8)
        'SCT',                          # Identification
        bic,                            # BIC
        recipient[:70],                 # Beneficiary Name
        iban,                           # IBAN (no spaces)
        f'EUR{amount:.2f}',             # Amount
        '',                             # Purpose
        f'EEG-Abr {invoice["id"]}/{invoice["created_at"][:4]} {member["name"][:30]}',  # Remittance
        '',                             # Display text
    ])

    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=4, border=2)
    qr.add_data(epc_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('ascii')
    return f'data:image/png;base64,{b64}'


def calculate_member_savings(member_stats, items, price_cons=None, price_gen=None):
    """Berechnet die Ersparnis eines Mitglieds durch EEG-Teilnahme."""
    # Vergleichswerte für lokale EEG ("kleine EEG")
    # Hinweis: Bei lokaler EEG gilt eine höhere Netzentgelt-Reduktion als bei regionaler EEG.
    market_price_ct = 25.0  # Durchschnittlicher Haushaltsstrompreis AT 2026 in ct/kWh
    elabg_ct = 1.5          # Elektrizitätsabgabe (entfällt in EEG)
    eeg_type = 'lokal'
    local_netz_reduction_pct = 57.0
    # Näherung für den energieabhängigen Netzentgelt-Anteil (ct/kWh), auf den die Reduktion wirkt.
    netzentgelt_base_ct = 4.0
    netzentgelt_reduction_ct = netzentgelt_base_ct * (local_netz_reduction_pct / 100.0)

    # Preise aus den tatsächlichen Rechnungspositionen ableiten
    if price_cons is None or price_gen is None:
        # Aus den Items die tatsächlich berechneten Preise lesen
        for item in items:
            if item['type'] == 'consumption' and item['price_per_kwh']:
                price_cons = item['price_per_kwh']
                break
        for item in items:
            if item['type'] == 'generation' and item['price_per_kwh']:
                price_gen = item['price_per_kwh']
                break
    # Fallback nur wenn gar keine Items vorhanden
    eeg_price_ct = price_cons if price_cons else 12.0
    eeg_gen_price_ct = price_gen if price_gen else 10.0

    cons_kwh = member_stats['total_consumption_kwh']
    gen_kwh = member_stats['total_generation_kwh']

    # Berechnung Bezugsseite
    cost_market = cons_kwh * market_price_ct / 100.0  # Was der Strom am Markt kosten würde
    cost_eeg = cons_kwh * eeg_price_ct / 100.0        # Was er in der EEG kostet
    saving_price = cost_market - cost_eeg             # Ersparnis durch günstigen EEG-Preis
    saving_elabg = cons_kwh * elabg_ct / 100.0        # Ersparnis Elektrizitätsabgabe
    saving_netz = cons_kwh * netzentgelt_reduction_ct / 100.0  # Ersparnis Netzentgelt

    # Einspeiseseite (Vergütung)
    market_einspeisetarif_ct = 4.5  # OeMAG Marktpreis-Einspeisung ca. 4-5 ct
    gen_income_eeg = gen_kwh * eeg_gen_price_ct / 100.0
    gen_income_market = gen_kwh * market_einspeisetarif_ct / 100.0
    saving_generation = gen_income_eeg - gen_income_market

    total_saving = saving_price + saving_elabg + saving_netz + saving_generation

    # Kosten in der EEG (was tatsächlich bezahlt wird)
    actual_cost = 0
    actual_income = 0
    for item in items:
        if item['type'] == 'consumption':
            actual_cost += item['amount_eur']
        else:
            actual_income += item['amount_eur']

    return {
        'cons_kwh': cons_kwh,
        'gen_kwh': gen_kwh,
        'eeg_type': eeg_type,
        'market_price_ct': market_price_ct,
        'eeg_price_ct': eeg_price_ct,
        'elabg_ct': elabg_ct,
        'netzentgelt_base_ct': netzentgelt_base_ct,
        'netzentgelt_reduction_pct': local_netz_reduction_pct,
        'netzentgelt_reduction_ct': netzentgelt_reduction_ct,
        'cost_market': round(cost_market, 2),
        'cost_eeg': round(cost_eeg, 2),
        'saving_price': round(saving_price, 2),
        'saving_elabg': round(saving_elabg, 2),
        'saving_netz': round(saving_netz, 2),
        'saving_generation': round(saving_generation, 2),
        'total_saving': round(total_saving, 2),
        'actual_cost': round(actual_cost, 2),
        'actual_income': round(actual_income, 2),
        'eeg_gen_price_ct': eeg_gen_price_ct,
        'market_einspeisetarif_ct': market_einspeisetarif_ct,
        'gen_income_eeg': round(gen_income_eeg, 2),
        'gen_income_market': round(gen_income_market, 2),
    }


def get_member_stats(db, member, period_from, period_to):
    """Berechnet detaillierte Statistiken für ein Mitglied (Seite 2)."""
    ts_from = period_from + "T00:00:00"
    ts_to = period_to + "T23:45:00"

    # Monatliche Daten Bezug (G.03)
    monthly_cons = db.execute("""
        SELECT strftime('%Y-%m', m.timestamp_start) as month,
               ROUND(SUM(m.value_kwh), 2) as kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE mc.code = '1-1:2.9.0 G.03'
          AND m.metering_point_id = ?
          AND m.timestamp_start >= ? AND m.timestamp_start <= ?
        GROUP BY month ORDER BY month
    """, (member['bezug_zp'], ts_from, ts_to)).fetchall()

    # Monatliche Daten Einspeisung (G.01T - P.01T)
    monthly_gen_raw = {}
    if member['einspeiser_zp']:
        rows = db.execute("""
            SELECT strftime('%Y-%m', m.timestamp_start) as month,
                   mc.code,
                   ROUND(SUM(m.value_kwh), 2) as kwh
            FROM measurements m
            JOIN meter_codes mc ON mc.id = m.meter_code_id
            WHERE mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
              AND m.metering_point_id = ?
              AND m.timestamp_start >= ? AND m.timestamp_start <= ?
            GROUP BY month, mc.code ORDER BY month
        """, (member['einspeiser_zp'], ts_from, ts_to)).fetchall()
        for r in rows:
            if r['month'] not in monthly_gen_raw:
                monthly_gen_raw[r['month']] = {'g01t': 0, 'p01t': 0}
            if 'G.01T' in r['code']:
                monthly_gen_raw[r['month']]['g01t'] = r['kwh']
            else:
                monthly_gen_raw[r['month']]['p01t'] = r['kwh']

    # Gesamter Netz-Bezug für Eigendeckungsgrad
    total_grid = db.execute("""
        SELECT ROUND(SUM(m.value_kwh), 2) as kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE mc.code = '1-1:1.9.0 G.01'
          AND m.metering_point_id = ?
          AND m.timestamp_start >= ? AND m.timestamp_start <= ?
    """, (member['bezug_zp'], ts_from, ts_to)).fetchone()
    total_grid_kwh = total_grid['kwh'] or 0

    # Preise für Berechnung
    price_cons, price_gen = get_price_for_date(db, period_from)

    # Monats-Labels und Daten zusammenführen
    month_names = {'01': 'Jän', '02': 'Feb', '03': 'Mär', '04': 'Apr',
                   '05': 'Mai', '06': 'Jun', '07': 'Jul', '08': 'Aug',
                   '09': 'Sep', '10': 'Okt', '11': 'Nov', '12': 'Dez'}
    monthly_data = []
    total_cons = 0
    total_gen = 0
    for row in monthly_cons:
        month_key = row['month']
        cons = row['kwh'] or 0
        gen_data = monthly_gen_raw.get(month_key, {'g01t': 0, 'p01t': 0})
        gen = max(0, gen_data['g01t'] - gen_data['p01t'])
        net_eur = round(cons * price_cons / 100.0 - gen * price_gen / 100.0, 2)
        label = month_names.get(month_key[-2:], month_key[-2:]) + ' ' + month_key[:4]
        monthly_data.append({
            'month_key': month_key,
            'label': label,
            'consumption': cons,
            'generation': round(gen, 2),
            'net_eur': net_eur
        })
        total_cons += cons
        total_gen += gen

    # Auch Monate mit nur Einspeisung hinzufügen
    existing_months = {row['month'] for row in monthly_cons}
    for month_key in sorted(monthly_gen_raw.keys()):
        if month_key not in existing_months:
            gen_data = monthly_gen_raw[month_key]
            gen = max(0, gen_data['g01t'] - gen_data['p01t'])
            net_eur = round(-gen * price_gen / 100.0, 2)
            label = month_names.get(month_key[-2:], month_key[-2:]) + ' ' + month_key[:4]
            monthly_data.append({
                'month_key': month_key,
                'label': label,
                'consumption': 0,
                'generation': round(gen, 2),
                'net_eur': net_eur
            })
            total_gen += gen
    monthly_data.sort(key=lambda x: x['month_key'])

    # Eigendeckungsgrad: Anteil EEG am Gesamtbezug
    total_member_consumption = total_grid_kwh + total_cons
    self_sufficiency = (total_cons / total_member_consumption * 100) if total_member_consumption > 0 else 0

    monthly_max = max((d['consumption'] for d in monthly_data), default=0)
    monthly_gen_max = max((d['generation'] for d in monthly_data), default=0)

    return {
        'total_consumption_kwh': round(total_cons, 1),
        'total_generation_kwh': round(total_gen, 1),
        'co2_saved_kg': round(total_cons * 0.227, 1),  # 227g CO2/kWh Strommix AT
        'self_sufficiency_pct': round(self_sufficiency, 1),
        'monthly_data': monthly_data,
        'monthly_max': monthly_max,
        'monthly_gen_max': monthly_gen_max,
    }


def get_community_stats(db, invoice):
    """Berechnet EEG-Gesamtstatistiken für Transparenzseite (Seite 3)."""
    ts_from = invoice['period_from'] + "T00:00:00"
    ts_to = invoice['period_to'] + "T23:45:00"
    price_cons, price_gen = get_price_for_date(db, invoice['period_from'])

    # Gehandelte Energie (Summe aller G.03)
    total_traded = db.execute("""
        SELECT ROUND(SUM(m.value_kwh), 1) as kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE mc.code = '1-1:2.9.0 G.03'
          AND m.timestamp_start >= ? AND m.timestamp_start <= ?
    """, (ts_from, ts_to)).fetchone()['kwh'] or 0

    # Erzeugung für Community
    total_generated = db.execute("""
        SELECT
            SUM(CASE WHEN mc.code='1-1:2.9.0 G.01T' THEN m.value_kwh ELSE 0 END) as g01t,
            SUM(CASE WHEN mc.code='1-1:2.9.0 P.01T' THEN m.value_kwh ELSE 0 END) as p01t
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN members mb ON mb.einspeiser_zp = m.metering_point_id
        WHERE mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
          AND m.timestamp_start >= ? AND m.timestamp_start <= ?
    """, (ts_from, ts_to)).fetchone()
    total_gen_kwh = round(max(0, (total_generated['g01t'] or 0) - (total_generated['p01t'] or 0)), 1)

    # Mitglieder-Anzahl
    member_count = db.execute("SELECT COUNT(*) FROM members WHERE active=1").fetchone()[0]
    generator_count = db.execute("SELECT COUNT(*) FROM members WHERE active=1 AND einspeiser_zp IS NOT NULL AND einspeiser_zp != ''").fetchone()[0]

    # Pro-Mitglied Verbrauch
    member_cons = db.execute("""
        SELECT mb.name, ROUND(SUM(m.value_kwh), 1) as kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN members mb ON mb.bezug_zp = m.metering_point_id
        WHERE mc.code = '1-1:2.9.0 G.03'
          AND m.timestamp_start >= ? AND m.timestamp_start <= ?
        GROUP BY mb.id ORDER BY kwh DESC
    """, (ts_from, ts_to)).fetchall()

    member_consumption = [{'name': r['name'], 'kwh': r['kwh']} for r in member_cons]
    max_cons = member_consumption[0]['kwh'] if member_consumption else 0

    # Pro-Mitglied Erzeugung
    member_gen = db.execute("""
        SELECT mb.name,
               ROUND(SUM(CASE WHEN mc.code='1-1:2.9.0 G.01T' THEN m.value_kwh ELSE 0 END) -
                     SUM(CASE WHEN mc.code='1-1:2.9.0 P.01T' THEN m.value_kwh ELSE 0 END), 1) as kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        JOIN members mb ON mb.einspeiser_zp = m.metering_point_id
        WHERE mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
          AND m.timestamp_start >= ? AND m.timestamp_start <= ?
        GROUP BY mb.id ORDER BY kwh DESC
    """, (ts_from, ts_to)).fetchall()
    member_generation = [{'name': r['name'], 'kwh': max(0, r['kwh'])} for r in member_gen]
    max_gen = member_generation[0]['kwh'] if member_generation else 0

    # Durchschnittlicher Eigendeckungsgrad
    avg_self_suff = 0
    if total_traded > 0:
        total_all_grid = db.execute("""
            SELECT ROUND(SUM(m.value_kwh), 1) as kwh
            FROM measurements m
            JOIN meter_codes mc ON mc.id = m.meter_code_id
            JOIN members mb ON mb.bezug_zp = m.metering_point_id
            WHERE mc.code = '1-1:1.9.0 G.01'
              AND m.timestamp_start >= ? AND m.timestamp_start <= ?
        """, (ts_from, ts_to)).fetchone()['kwh'] or 0
        total_all_consumption = total_all_grid + total_traded
        avg_self_suff = (total_traded / total_all_consumption * 100) if total_all_consumption > 0 else 0

    co2_total = total_traded * 0.227
    trees = int(co2_total / 12.5)  # ~12.5 kg CO2 pro Baum/Jahr

    return {
        'member_count': member_count,
        'generator_count': generator_count,
        'total_traded_kwh': total_traded,
        'total_generated_kwh': total_gen_kwh,
        'avg_self_sufficiency': round(avg_self_suff, 1),
        'total_co2_saved_kg': round(co2_total, 0),
        'trees_equivalent': trees,
        'member_consumption': member_consumption,
        'max_consumption': max_cons,
        'member_generation': member_generation,
        'max_generation': max_gen,
        'price_cons': price_cons,
        'price_gen': price_gen,
    }


@app.route('/invoices/<int:id>/send', methods=['POST'])
@admin_required
def invoice_send(id):
    """E-Mails an alle Mitglieder versenden."""
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id=?", (id,)).fetchone()
    blocker = invoice_finalization_blocker(db, invoice)
    if blocker:
        flash(blocker, 'danger')
        audit_log('invoice_send_blocked', f'Rechnung {id}: Sammelversand blockiert ({blocker})')
        return redirect(url_for('invoice_detail', id=id))
    items = invoice_recipient_rows(db, id)

    sent = 0
    failed = 0
    for item in items:
        if not item['email']:
            db.execute("""INSERT INTO email_log (invoice_id, member_id, recipient_email, subject, status, error_message)
                          VALUES (?, ?, ?, ?, 'failed', 'Keine E-Mail-Adresse')""",
                       (id, item['member_id'], '-',
                        f"EEG Abrechnung {invoice['period_from']} - {invoice['period_to']}"))
            failed += 1
            continue

        try:
            send_invoice_email(db, invoice, item)
            db.execute("""INSERT INTO email_log (invoice_id, member_id, recipient_email, subject, status)
                          VALUES (?, ?, ?, ?, 'sent')""",
                       (id, item['member_id'], item['email'],
                        f"EEG Abrechnung {invoice['period_from']} - {invoice['period_to']}"))
            sent += 1
        except Exception as e:
            db.execute("""INSERT INTO email_log (invoice_id, member_id, recipient_email, subject, status, error_message)
                          VALUES (?, ?, ?, ?, 'failed', ?)""",
                       (id, item['member_id'], item['email'],
                        f"EEG Abrechnung {invoice['period_from']} - {invoice['period_to']}",
                        str(e)))
            failed += 1

    db.execute("UPDATE invoices SET status='sent', finalized_at=datetime('now') WHERE id=?", (id,))
    db.commit()
    audit_log('invoice_send_all', f'Rechnung {id}: {sent} E-Mails gesendet, {failed} fehlgeschlagen')
    flash(f'{sent} E-Mails gesendet, {failed} fehlgeschlagen.', 'success' if failed == 0 else 'warning')
    return redirect(url_for('invoice_detail', id=id))


@app.route('/invoices/<int:id>/send/<int:member_id>', methods=['POST'])
@admin_required
def invoice_send_single(id, member_id):
    """E-Mail an ein einzelnes Mitglied senden."""
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id=?", (id,)).fetchone()
    member = db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    blocker = invoice_finalization_blocker(db, invoice)
    if blocker:
        flash(blocker, 'danger')
        audit_log('invoice_send_blocked', f'Rechnung {id}: Einzelversand blockiert ({blocker})')
        return redirect(url_for('invoice_detail', id=id))

    if not member['email']:
        db.execute("""INSERT INTO email_log (invoice_id, member_id, recipient_email, subject, status, error_message)
                      VALUES (?, ?, ?, ?, 'failed', 'Keine E-Mail-Adresse hinterlegt')""",
                   (id, member_id, '-',
                    f"EEG Abrechnung {invoice['period_from']} - {invoice['period_to']}"))
        db.commit()
        flash(f'Keine E-Mail-Adresse für {member["name"]} hinterlegt.', 'danger')
        return redirect(url_for('invoice_detail', id=id))

    try:
        member_row = {'member_id': member_id, 'name': member['name'], 'email': member['email']}
        send_invoice_email(db, invoice, member_row)
        db.execute("""INSERT INTO email_log (invoice_id, member_id, recipient_email, subject, status)
                      VALUES (?, ?, ?, ?, 'sent')""",
                   (id, member_id, member['email'],
                    f"EEG Abrechnung {invoice['period_from']} - {invoice['period_to']}"))
        # Prüfen ob jetzt alle Mitglieder eine E-Mail erhalten haben → Status auf 'sent' setzen
        total_members = db.execute("""
            SELECT COUNT(*) FROM (
                SELECT m.id
                FROM members m
                WHERE m.id IN (
                    SELECT member_id FROM invoice_items WHERE invoice_id=?
                    UNION
                    SELECT member_id FROM invoice_carryovers WHERE invoice_id=?
                )
                AND m.email IS NOT NULL AND m.email != ''
            )
        """, (id, id)).fetchone()[0]
        sent_members = db.execute("""
            SELECT COUNT(DISTINCT member_id) FROM email_log
            WHERE invoice_id=? AND status='sent'
        """, (id,)).fetchone()[0]
        if sent_members >= total_members and total_members > 0:
            db.execute("UPDATE invoices SET status='sent', finalized_at=datetime('now') WHERE id=?", (id,))
        db.commit()
        audit_log('invoice_send', f'E-Mail gesendet: Rechnung {id} an {member["name"]} ({member["email"]})')
        flash(f'E-Mail an {member["name"]} ({member["email"]}) gesendet.', 'success')
    except Exception as e:
        db.execute("""INSERT INTO email_log (invoice_id, member_id, recipient_email, subject, status, error_message)
                      VALUES (?, ?, ?, ?, 'failed', ?)""",
                   (id, member_id, member['email'],
                    f"EEG Abrechnung {invoice['period_from']} - {invoice['period_to']}",
                    str(e)))
        db.commit()
        flash(f'Fehler beim Senden an {member["name"]}: {e}', 'danger')

    return redirect(url_for('invoice_detail', id=id))


@app.route('/invoices/<int:id>/finalize', methods=['POST'])
@admin_required
def invoice_finalize(id):
    """Abrechnung manuell auf 'sent' setzen (z.B. wenn Versand ohne System erfolgte)."""
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id=?", (id,)).fetchone()
    blocker = invoice_finalization_blocker(db, invoice)
    if blocker:
        flash(blocker, 'danger')
        audit_log('invoice_finalize_blocked', f'Abrechnung #{id}: Abschluss blockiert ({blocker})')
        return redirect(url_for('invoice_detail', id=id))
    db.execute("UPDATE invoices SET status='sent', finalized_at=datetime('now') WHERE id=?", (id,))
    db.commit()
    audit_log('invoice_finalize', f'Abrechnung #{id} manuell finalisiert')
    flash(f'Abrechnung #{id} wurde als finalisiert markiert.', 'success')
    return redirect(url_for('invoice_detail', id=id))


def send_invoice_email(db, invoice, member_row):
    """Sendet eine Abrechnungs-E-Mail. Konfiguration aus DB-Settings."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    mail_cfg = _get_valid_mail_config(db)

    # PDF generieren
    member = db.execute("SELECT * FROM members WHERE id=?", (member_row['member_id'],)).fetchone()
    items = db.execute("SELECT * FROM invoice_items WHERE invoice_id=? AND member_id=?",
                       (invoice['id'], member_row['member_id'])).fetchall()
    carryovers = get_invoice_carryovers(db, invoice['id'], member_row['member_id'])
    carryover_total = round(sum(row['amount_eur'] for row in carryovers), 2)

    energy_net_total = 0
    for it in items:
        if it['type'] == 'consumption':
            energy_net_total += it['amount_eur']
        else:
            energy_net_total -= it['amount_eur']
    net_total = round(energy_net_total + carryover_total, 2)

    qr_data_uri = ''
    if net_total > 0:
        qr_data_uri = generate_epc_qr(net_total, invoice, member)

    member_stats = get_member_stats(db, member, invoice['period_from'], invoice['period_to'])
    community_stats = get_community_stats(db, invoice)
    savings = calculate_member_savings(member_stats, items)
    public_cfg = get_public_config(db)

    import base64 as b64mod
    logo_path = os.path.join(BASE_DIR, 'static', 'logo_small.png')
    with open(logo_path, 'rb') as f:
        logo_b64 = 'data:image/png;base64,' + b64mod.b64encode(f.read()).decode('ascii')

    from weasyprint import HTML
    html_content = render_template('invoice_pdf.html', invoice=invoice, member=member, items=items,
                                   carryovers=carryovers,
                                   member_stats=member_stats, community_stats=community_stats,
                                   energy_net_total=round(energy_net_total, 2),
                                   carryover_total=carryover_total,
                                   net_total=net_total, qr_data_uri=qr_data_uri,
                                   savings=savings, logo_b64=logo_b64, public_cfg=public_cfg)
    pdf_bytes = HTML(string=html_content, base_url=BASE_DIR).write_pdf()

    # E-Mail zusammenbauen
    # Templates aus DB laden
    tpl_rows = db.execute("SELECT key, value FROM settings WHERE key IN ('email_subject', 'email_body')").fetchall()
    tpl = {r['key']: r['value'] for r in tpl_rows}
    replacements = {
        'name': member_row['name'],
        'zeitraum_von': invoice['period_from'],
        'zeitraum_bis': invoice['period_to'],
    }
    subject = tpl.get('email_subject', 'EEG Abrechnung {zeitraum_von} - {zeitraum_bis}').format(**replacements)
    body_text = tpl.get('email_body', 'Hallo {name},\n\nanbei Ihre Abrechnung.').format(**replacements)

    # HTML-Version der E-Mail mit Logo
    import base64 as b64mod2
    logo_email_path = os.path.join(BASE_DIR, 'static', 'logo_small.png')
    with open(logo_email_path, 'rb') as f:
        logo_email_b64 = b64mod2.b64encode(f.read()).decode('ascii')

    body_html = f"""<html><body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
<div style="max-width: 600px; margin: 0 auto;">
    <div style="text-align: center; padding: 15px 0; border-bottom: 2px solid #2b5e3a;">
        <img src="data:image/png;base64,{logo_email_b64}" width="50" height="50" style="border-radius: 8px;">
        <h2 style="color: #2b5e3a; margin: 8px 0 0 0; font-size: 18px;">{public_cfg['org_name']}</h2>
    </div>
    <div style="padding: 20px 0;">
        {''.join(f'<p style="margin: 8px 0;">{line}</p>' if line.strip() else '<br>' for line in body_text.split(chr(10)))}
    </div>
    <div style="border-top: 1px solid #ccc; padding-top: 12px; font-size: 11px; color: #777; text-align: center;">
        <strong>{public_cfg['org_name']}</strong><br>
        {public_cfg['org_address']}<br>
        {public_cfg['org_email']}
    </div>
</div>
</body></html>"""

    msg = MIMEMultipart('mixed')
    msg['From'] = mail_cfg['from_header']
    msg['Reply-To'] = mail_cfg['reply_to_header']
    msg['To'] = member_row['email']
    msg['Subject'] = subject

    # Text + HTML Alternative
    msg_alt = MIMEMultipart('alternative')
    msg_alt.attach(MIMEText(body_text, 'plain', 'utf-8'))
    msg_alt.attach(MIMEText(body_html, 'html', 'utf-8'))
    msg.attach(msg_alt)

    pdf_attachment = MIMEApplication(pdf_bytes, _subtype='pdf')
    pdf_attachment.add_header('Content-Disposition', 'attachment',
                             filename=f"EEG_Abrechnung_{invoice['period_from']}_{invoice['period_to']}.pdf")
    msg.attach(pdf_attachment)

    _log_mail_send(mail_cfg, member_row['email'], subject)
    with smtplib.SMTP(mail_cfg['smtp_host'], mail_cfg['smtp_port']) as server:
        if mail_cfg['smtp_tls']:
            server.starttls()
        server.login(mail_cfg['smtp_user'], mail_cfg['smtp_pass'])
        server.send_message(msg, from_addr=mail_cfg['from_address'], to_addrs=[member_row['email']])


# === Reports ===

REPORT_AGGREGATIONS = {
    'day': {'label': 'Tag', 'strftime': '%Y-%m-%d'},
    'month': {'label': 'Monat', 'strftime': '%Y-%m'},
    'year': {'label': 'Jahr', 'strftime': '%Y'},
}


def _report_float(value):
    return float(value or 0)


def _report_round(value, digits=2):
    return round(_report_float(value), digits)


def _report_pct(part, total):
    total = _report_float(total)
    if total <= 0:
        return 0.0
    return round(_report_float(part) / total * 100.0, 1)


def _report_ts_bounds(db):
    row = db.execute("SELECT MIN(timestamp_start) AS min_ts, MAX(timestamp_start) AS max_ts FROM measurements").fetchone()
    today = local_now().date()
    min_date = (row['min_ts'][:10] if row and row['min_ts'] else today.replace(month=1, day=1).isoformat())
    max_date = (row['max_ts'][:10] if row and row['max_ts'] else today.isoformat())
    return min_date, max_date


def _parse_report_date(value, fallback):
    try:
        return date.fromisoformat((value or '').strip()).isoformat()
    except ValueError:
        return fallback


def _month_iter(start_date, end_date):
    cur = date.fromisoformat(start_date).replace(day=1)
    end = date.fromisoformat(end_date).replace(day=1)
    while cur <= end:
        yield cur
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)


def _month_end(day):
    from calendar import monthrange
    return date(day.year, day.month, monthrange(day.year, day.month)[1])


def _dt_ms(value):
    try:
        return int(datetime.fromisoformat(value).timestamp() * 1000)
    except ValueError:
        return 0


def _build_member_report(db, member, period_from, period_to, aggregation):
    ts_from = period_from + 'T00:00:00'
    ts_to = period_to + 'T23:45:00'
    agg = REPORT_AGGREGATIONS.get(aggregation, REPORT_AGGREGATIONS['month'])
    bucket_expr = f"strftime('{agg['strftime']}', m.timestamp_start)"
    price_cons, price_gen = get_price_for_date(db, period_from)
    market_price_ct = 25.0
    market_feed_ct = 4.5

    params = {
        'bezug_zp': member['bezug_zp'] or '',
        'einspeiser_zp': member['einspeiser_zp'] or '',
        'ts_from': ts_from,
        'ts_to': ts_to,
    }
    series_rows = db.execute(f"""
        SELECT {bucket_expr} AS bucket,
               ROUND(SUM(CASE WHEN m.metering_point_id=:bezug_zp AND mc.code='1-1:2.9.0 G.03' THEN m.value_kwh ELSE 0 END), 3) AS eeg,
               ROUND(SUM(CASE WHEN m.metering_point_id=:bezug_zp AND mc.code='1-1:1.9.0 G.01' THEN m.value_kwh ELSE 0 END), 3) AS grid,
               ROUND(SUM(CASE WHEN m.metering_point_id=:einspeiser_zp AND mc.code='1-1:2.9.0 G.01T' THEN m.value_kwh ELSE 0 END), 3) AS generation,
               ROUND(SUM(CASE WHEN m.metering_point_id=:einspeiser_zp AND mc.code='1-1:2.9.0 P.01T' THEN m.value_kwh ELSE 0 END), 3) AS public_feed
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND (
            (m.metering_point_id=:bezug_zp AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01'))
            OR
            (m.metering_point_id=:einspeiser_zp AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T'))
          )
        GROUP BY bucket
        ORDER BY bucket
    """, params).fetchall()

    labels = []
    eeg_values = []
    grid_values = []
    generation_values = []
    public_feed_values = []
    eeg_feed_values = []
    total_consumption_values = []
    eeg_share_values = []
    cost_without_values = []
    cost_actual_values = []
    savings_values = []
    cumulative_savings = []
    running_savings = 0.0
    for row in series_rows:
        eeg = _report_float(row['eeg'])
        grid = _report_float(row['grid'])
        generation = _report_float(row['generation'])
        public_feed = _report_float(row['public_feed'])
        eeg_feed = max(0.0, generation - public_feed)
        total_consumption = eeg + grid
        cost_without = total_consumption * market_price_ct / 100.0 - generation * market_feed_ct / 100.0
        cost_actual = grid * market_price_ct / 100.0 + eeg * price_cons / 100.0 - eeg_feed * price_gen / 100.0 - public_feed * market_feed_ct / 100.0
        savings = cost_without - cost_actual
        running_savings += savings

        labels.append(row['bucket'])
        eeg_values.append(round(eeg, 3))
        grid_values.append(round(grid, 3))
        generation_values.append(round(generation, 3))
        public_feed_values.append(round(public_feed, 3))
        eeg_feed_values.append(round(eeg_feed, 3))
        total_consumption_values.append(round(total_consumption, 3))
        eeg_share_values.append(_report_pct(eeg, total_consumption))
        cost_without_values.append(round(cost_without, 2))
        cost_actual_values.append(round(cost_actual, 2))
        savings_values.append(round(savings, 2))
        cumulative_savings.append(round(running_savings, 2))

    totals = {
        'eeg': round(sum(eeg_values), 2),
        'grid': round(sum(grid_values), 2),
        'consumption': round(sum(total_consumption_values), 2),
        'generation': round(sum(generation_values), 2),
        'public_feed': round(sum(public_feed_values), 2),
        'eeg_feed': round(sum(eeg_feed_values), 2),
        'cost_without': round(sum(cost_without_values), 2),
        'cost_actual': round(sum(cost_actual_values), 2),
        'savings': round(sum(savings_values), 2),
    }
    totals['eeg_share'] = _report_pct(totals['eeg'], totals['consumption'])
    totals['autarky'] = totals['eeg_share']
    totals['avg_savings_per_kwh'] = round(totals['savings'] / totals['consumption'], 4) if totals['consumption'] > 0 else 0
    totals['self_consumption_quote'] = None

    daily_rows = db.execute("""
        SELECT substr(m.timestamp_start, 1, 10) AS day,
               ROUND(SUM(CASE WHEN m.metering_point_id=:bezug_zp AND mc.code='1-1:2.9.0 G.03' THEN m.value_kwh ELSE 0 END), 3) AS eeg,
               ROUND(SUM(CASE WHEN m.metering_point_id=:bezug_zp AND mc.code='1-1:1.9.0 G.01' THEN m.value_kwh ELSE 0 END), 3) AS grid
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND m.metering_point_id=:bezug_zp
          AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01')
        GROUP BY day
        ORDER BY day
    """, params).fetchall()
    daily_shares = []
    for row in daily_rows:
        day_total = _report_float(row['eeg']) + _report_float(row['grid'])
        if day_total > 0:
            daily_shares.append({
                'day': row['day'],
                'eeg_share': _report_pct(row['eeg'], day_total),
                'eeg': _report_round(row['eeg'], 2),
                'grid': _report_round(row['grid'], 2),
            })
    best_day = max(daily_shares, key=lambda item: item['eeg_share'], default=None)
    weakest_day = min(daily_shares, key=lambda item: item['eeg_share'], default=None)

    heat_rows = db.execute("""
        SELECT CAST(strftime('%w', m.timestamp_start) AS INTEGER) AS weekday,
               CAST(strftime('%H', m.timestamp_start) AS INTEGER) AS hour,
               ROUND(SUM(m.value_kwh), 3) AS kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND m.metering_point_id=:bezug_zp
          AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01')
        GROUP BY weekday, hour
        ORDER BY weekday, hour
    """, params).fetchall()
    heatmap = []
    for row in heat_rows:
        weekday = (int(row['weekday']) + 6) % 7
        heatmap.append([int(row['hour']), weekday, _report_round(row['kwh'], 3)])

    hourly_rows = db.execute("""
        SELECT hour,
               ROUND(AVG(hour_sum), 3) AS kwh
        FROM (
            SELECT substr(m.timestamp_start, 1, 13) AS hour_bucket,
                   CAST(strftime('%H', m.timestamp_start) AS INTEGER) AS hour,
                   SUM(m.value_kwh) AS hour_sum
            FROM measurements m
            JOIN meter_codes mc ON mc.id = m.meter_code_id
            WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
              AND m.metering_point_id=:bezug_zp
              AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01')
            GROUP BY hour_bucket
        ) hourly
        GROUP BY hour
        ORDER BY hour
    """, params).fetchall()
    typical_day = [0.0] * 24
    for row in hourly_rows:
        typical_day[int(row['hour'])] = _report_round(row['kwh'], 3)

    peak_rows = db.execute("""
        SELECT m.timestamp_start AS ts, ROUND(SUM(m.value_kwh), 3) AS kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND m.metering_point_id=:bezug_zp
          AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01')
        GROUP BY m.timestamp_start
        ORDER BY kwh DESC
        LIMIT 8
    """, params).fetchall()
    peaks = [{'ts': row['ts'], 'kwh': _report_round(row['kwh'], 3)} for row in peak_rows]

    peak_line_rows = db.execute("""
        SELECT substr(m.timestamp_start, 1, 13) || ':00:00' AS ts, ROUND(SUM(m.value_kwh), 3) AS kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND m.metering_point_id=:bezug_zp
          AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01')
        GROUP BY substr(m.timestamp_start, 1, 13)
        ORDER BY ts
    """, params).fetchall()
    peak_line = [[_dt_ms(row['ts']), _report_round(row['kwh'], 3)] for row in peak_line_rows]
    peak_markers = [[_dt_ms(row['ts']), _report_round(row['kwh'], 3)] for row in peaks]

    quality_rows = db.execute("""
        SELECT COALESCE(NULLIF(TRIM(m.quality), ''), 'unbekannt') AS quality, COUNT(*) AS cnt
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND (
            (m.metering_point_id=:bezug_zp AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01'))
            OR
            (m.metering_point_id=:einspeiser_zp AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T'))
          )
        GROUP BY quality
        ORDER BY cnt DESC
    """, params).fetchall()
    quality_total = sum(row['cnt'] for row in quality_rows) or 1
    quality = [{
        'quality': row['quality'],
        'cnt': row['cnt'],
        'pct': round(row['cnt'] / quality_total * 100.0, 1),
    } for row in quality_rows]

    relevant_code_count = 2 + (2 if member['einspeiser_zp'] else 0)
    actual_by_month = {
        row['bucket']: row['cnt']
        for row in db.execute("""
            SELECT strftime('%Y-%m', m.timestamp_start) AS bucket, COUNT(*) AS cnt
            FROM measurements m
            JOIN meter_codes mc ON mc.id = m.meter_code_id
            WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
              AND (
                (m.metering_point_id=:bezug_zp AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01'))
                OR
                (m.metering_point_id=:einspeiser_zp AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T'))
              )
            GROUP BY bucket
        """, params).fetchall()
    }
    missing_by_month = []
    for month_start in _month_iter(period_from, period_to):
        start = max(month_start, date.fromisoformat(period_from))
        end = min(_month_end(month_start), date.fromisoformat(period_to))
        days = (end - start).days + 1
        expected = max(0, days * 96 * relevant_code_count)
        actual = actual_by_month.get(month_start.strftime('%Y-%m'), 0)
        missing_by_month.append({
            'month': month_start.strftime('%Y-%m'),
            'missing': max(0, expected - actual),
            'expected': expected,
            'actual': actual,
            'completeness': round(actual / expected * 100.0, 1) if expected else 0,
        })
    completeness = round(
        sum(item['actual'] for item in missing_by_month) / max(1, sum(item['expected'] for item in missing_by_month)) * 100.0,
        1
    )

    zeros = db.execute("""
        SELECT COUNT(*)
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND m.value_kwh = 0
          AND (
            (m.metering_point_id=:bezug_zp AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01'))
            OR
            (m.metering_point_id=:einspeiser_zp AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T'))
          )
    """, params).fetchone()[0] or 0
    outliers = db.execute("""
        SELECT COUNT(*)
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND (m.value_kwh < 0 OR m.value_kwh > 100)
          AND (
            (m.metering_point_id=:bezug_zp AND mc.code IN ('1-1:2.9.0 G.03', '1-1:1.9.0 G.01'))
            OR
            (m.metering_point_id=:einspeiser_zp AND mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T'))
          )
    """, params).fetchone()[0] or 0

    community_rows = db.execute("""
        SELECT mb.id,
               ROUND(SUM(CASE WHEN m.metering_point_id=mb.bezug_zp AND mc.code='1-1:2.9.0 G.03' THEN m.value_kwh ELSE 0 END), 3) AS eeg,
               ROUND(SUM(CASE WHEN m.metering_point_id=mb.bezug_zp AND mc.code='1-1:1.9.0 G.01' THEN m.value_kwh ELSE 0 END), 3) AS grid,
               ROUND(SUM(CASE WHEN m.metering_point_id=mb.einspeiser_zp AND mc.code='1-1:2.9.0 G.01T' THEN m.value_kwh ELSE 0 END), 3) AS generation,
               ROUND(SUM(CASE WHEN m.metering_point_id=mb.einspeiser_zp AND mc.code='1-1:2.9.0 P.01T' THEN m.value_kwh ELSE 0 END), 3) AS public_feed
        FROM members mb
        LEFT JOIN measurements m
          ON m.timestamp_start BETWEEN :ts_from AND :ts_to
         AND (m.metering_point_id=mb.bezug_zp OR m.metering_point_id=mb.einspeiser_zp)
        LEFT JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE mb.active=1
        GROUP BY mb.id
    """, params).fetchall()
    community_shares = []
    community_generation = 0.0
    community_eeg_feed = 0.0
    for row in community_rows:
        consumption = _report_float(row['eeg']) + _report_float(row['grid'])
        if consumption > 0:
            community_shares.append(_report_float(row['eeg']) / consumption * 100.0)
        generation = _report_float(row['generation'])
        public_feed = _report_float(row['public_feed'])
        community_generation += generation
        community_eeg_feed += max(0.0, generation - public_feed)
    community_avg_eeg_share = round(sum(community_shares) / len(community_shares), 1) if community_shares else 0
    member_generation_share = _report_pct(totals['eeg_feed'], community_eeg_feed)

    evening_grid = db.execute("""
        SELECT ROUND(SUM(m.value_kwh), 3)
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND m.metering_point_id=:bezug_zp
          AND mc.code='1-1:1.9.0 G.01'
          AND CAST(strftime('%H', m.timestamp_start) AS INTEGER) BETWEEN 17 AND 21
    """, params).fetchone()[0] or 0
    noon_eeg = db.execute("""
        SELECT ROUND(SUM(m.value_kwh), 3)
        FROM measurements m
        JOIN meter_codes mc ON mc.id = m.meter_code_id
        WHERE m.timestamp_start BETWEEN :ts_from AND :ts_to
          AND m.metering_point_id=:bezug_zp
          AND mc.code='1-1:2.9.0 G.03'
          AND CAST(strftime('%H', m.timestamp_start) AS INTEGER) BETWEEN 10 AND 15
    """, params).fetchone()[0] or 0
    optimisation_hints = []
    if evening_grid > max(1.0, totals['grid'] * 0.25):
        optimisation_hints.append('Abends wird viel Strom vom öffentlichen Netz benötigt. Geräte wie Waschmaschine, Geschirrspüler oder Boiler könnten wenn möglich früher laufen.')
    if noon_eeg < max(1.0, totals['eeg'] * 0.25):
        optimisation_hints.append('Rund um die Mittagszeit wird noch wenig Strom aus der Energiegemeinschaft genutzt. Verbrauch in diese Zeit zu verschieben kann helfen.')
    if totals['eeg_share'] < community_avg_eeg_share:
        optimisation_hints.append('Der Anteil an Strom aus der Energiegemeinschaft liegt unter dem Durchschnitt der Gemeinschaft.')
    if not optimisation_hints:
        optimisation_hints.append('Im gewählten Zeitraum gibt es keine auffälligen Hinweise. Die Nutzung wirkt bereits ausgewogen.')

    charts = {
        'labels': labels,
        'eeg': eeg_values,
        'grid': grid_values,
        'generation': generation_values,
        'public_feed': public_feed_values,
        'eeg_feed': eeg_feed_values,
        'consumption': total_consumption_values,
        'eeg_share': eeg_share_values,
        'cost_without': cost_without_values,
        'cost_actual': cost_actual_values,
        'savings': savings_values,
        'cumulative_savings': cumulative_savings,
        'daily_eeg_share': [[item['day'], item['eeg_share']] for item in daily_shares],
        'heatmap': heatmap,
        'typical_day': typical_day,
        'peak_line': peak_line,
        'peak_markers': peak_markers,
        'missing_by_month': missing_by_month,
        'quality': quality,
        'sankey': [
            ['Öffentliches Netz', 'Verbrauch', _report_round(totals['grid'], 2)],
            ['EEG', 'Verbrauch', _report_round(totals['eeg'], 2)],
            ['Erzeugung', 'EEG', _report_round(totals['eeg_feed'], 2)],
            ['Erzeugung', 'Öffentliches Netz', _report_round(totals['public_feed'], 2)],
        ],
    }

    return {
        'totals': totals,
        'charts': charts,
        'best_day': best_day,
        'weakest_day': weakest_day,
        'peaks': peaks,
        'quality_summary': {
            'completeness': completeness,
            'zeros': zeros,
            'outliers': outliers,
            'expected_code_count': relevant_code_count,
        },
        'community': {
            'avg_eeg_share': community_avg_eeg_share,
            'member_generation_share': member_generation_share,
            'eeg_feed_total': round(community_eeg_feed, 2),
            'generation_total': round(community_generation, 2),
        },
        'prices': {
            'eeg_consumption_ct': price_cons,
            'eeg_generation_ct': price_gen,
            'market_consumption_ct': market_price_ct,
            'market_feed_ct': market_feed_ct,
            'is_estimate': True,
        },
        'optimisation_hints': optimisation_hints,
        'data_notes': [
            'Strom aus der Energiegemeinschaft ist jener Anteil, den Sie lokal von der EEG beziehen.',
            'Strom aus dem öffentlichen Netz ist jener Anteil, der nicht durch die EEG gedeckt wurde.',
            'Bei Erzeugern wird angezeigt, wie viel Energie an die EEG geliefert und wie viel ins öffentliche Netz abgegeben wurde.',
            'Direkt im Haus verbrauchter PV-Strom ist mit den vorhandenen Netzbetreiber-Daten nicht exakt getrennt sichtbar.',
            'Die Ersparnis ist eine Schätzung. Für eine exakte Berechnung braucht es einen gepflegten Vergleichstarif je Zeitraum.',
        ],
    }


def _reports_response(portal=False):
    db = get_db()
    min_date, max_date = _report_ts_bounds(db)
    aggregation = request.args.get('aggregation', 'month')
    if aggregation not in REPORT_AGGREGATIONS:
        aggregation = 'month'
    period_from = _parse_report_date(request.args.get('date_from'), min_date)
    period_to = _parse_report_date(request.args.get('date_to'), max_date)
    if period_from > period_to:
        period_from, period_to = period_to, period_from

    members = db.execute("""
        SELECT id, name, bezug_zp, einspeiser_zp
        FROM members
        WHERE active=1
        ORDER BY name
    """).fetchall()
    if portal:
        member_id = current_user.member_id
        if not member_id:
            flash('Kein Mitglied zugeordnet.', 'warning')
            return redirect(url_for('portal_dashboard'))
    else:
        member_id = request.args.get('member_id', type=int)
        if not member_id and members:
            member_id = members[0]['id']
    member = db.execute("SELECT * FROM members WHERE id=? AND active=1", (member_id,)).fetchone() if member_id else None
    if not member:
        flash('Kein aktives Mitglied für den Report gefunden.', 'warning')
        return render_template('reports.html', members=members, selected_member=None, report=None,
                               report_json='{}', period_from=period_from, period_to=period_to,
                               aggregation=aggregation, aggregations=REPORT_AGGREGATIONS, portal=portal,
                               min_date=min_date, max_date=max_date)

    if portal and current_user.member_id != member['id']:
        abort(403)

    report = _build_member_report(db, member, period_from, period_to, aggregation)
    return render_template(
        'reports.html',
        members=members,
        selected_member=member,
        report=report,
        report_json=json.dumps(report, ensure_ascii=False),
        period_from=period_from,
        period_to=period_to,
        aggregation=aggregation,
        aggregations=REPORT_AGGREGATIONS,
        portal=portal,
        min_date=min_date,
        max_date=max_date,
    )


@app.route('/reports')
@admin_required
def reports():
    return _reports_response(portal=False)


@app.route('/portal/reports')
@login_required
def portal_reports():
    return _reports_response(portal=True)


# === Billing Calculation ===

def calculate_billing(db, period_from, period_to, price_cons, price_gen):
    """Berechnet die Abrechnung für einen Zeitraum. Pro Mitglied Bezug + Einspeisung separat."""
    # Zeitraum in DB-Format konvertieren
    ts_from = period_from + "T00:00:00" if "T" not in period_from else period_from
    ts_to = period_to + "T23:45:00" if "T" not in period_to else period_to

    items = []
    total_income = 0
    total_expense = 0
    total_kwh = 0

    # Alle aktiven Mitglieder
    members = db.execute("SELECT id, name, bezug_zp, einspeiser_zp FROM members WHERE active=1").fetchall()

    for member in members:
        cons_kwh = 0
        gen_kwh = 0

        # Verbrauch: Eigendeckung G.03
        if member['bezug_zp']:
            row = db.execute("""
                SELECT ROUND(SUM(m.value_kwh), 3) as kwh
                FROM measurements m
                JOIN meter_codes mc ON mc.id = m.meter_code_id
                WHERE mc.code = '1-1:2.9.0 G.03'
                  AND m.metering_point_id = ?
                  AND m.timestamp_start >= ? AND m.timestamp_start <= ?
            """, (member['bezug_zp'], ts_from, ts_to)).fetchone()
            cons_kwh = row['kwh'] or 0

        # Erzeugung: G.01T - P.01T
        if member['einspeiser_zp']:
            row = db.execute("""
                SELECT
                    ROUND(SUM(CASE WHEN mc.code='1-1:2.9.0 G.01T' THEN m.value_kwh ELSE 0 END), 3) as g01t,
                    ROUND(SUM(CASE WHEN mc.code='1-1:2.9.0 P.01T' THEN m.value_kwh ELSE 0 END), 3) as p01t
                FROM measurements m
                JOIN meter_codes mc ON mc.id = m.meter_code_id
                WHERE mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
                  AND m.metering_point_id = ?
                  AND m.timestamp_start >= ? AND m.timestamp_start <= ?
            """, (member['einspeiser_zp'], ts_from, ts_to)).fetchone()
            gen_kwh = max(0, (row['g01t'] or 0) - (row['p01t'] or 0))

        # Nur Mitglieder mit Aktivität aufnehmen
        if cons_kwh <= 0 and gen_kwh <= 0:
            continue

        # Bezugsposition
        if cons_kwh > 0:
            cons_amount = round(cons_kwh * price_cons / 100.0, 2)
            items.append({
                'member_id': member['id'],
                'type': 'consumption',
                'kwh': round(cons_kwh, 3),
                'price': price_cons,
                'amount': cons_amount,
            })
            total_income += cons_amount
            total_kwh += cons_kwh

        # Einspeiseposition (Gutschrift)
        if gen_kwh > 0:
            gen_amount = round(gen_kwh * price_gen / 100.0, 2)
            items.append({
                'member_id': member['id'],
                'type': 'generation',
                'kwh': round(gen_kwh, 3),
                'price': price_gen,
                'amount': gen_amount,
            })
            total_expense += gen_amount

    carryovers = calculate_carryovers_for_period(db, period_from)

    return {
        'items': items,
        'carryovers': carryovers,
        'total_kwh': total_kwh,
        'total_income': round(total_income, 2),
        'total_expense': round(total_expense, 2),
        'total_margin': round(total_income - total_expense, 2)
    }


# === Settings ===

@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    db = get_db()
    if request.method == 'POST':
        existing_settings = {
            r['key']: r['value']
            for r in db.execute("SELECT key, value FROM settings").fetchall()
        }
        for key in (
            'smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass', 'smtp_from', 'smtp_tls',
            'mail_from_address', 'mail_from_name', 'mail_reply_to', 'mail_reply_to_name',
            'email_subject', 'email_body',
            'org_name', 'org_email', 'org_website', 'org_address', 'org_legal',
            'payment_recipient', 'payment_iban', 'payment_bic'
        ):
            val = request.form.get(key, '')
            if key == 'smtp_pass' and not val:
                val = existing_settings.get('smtp_pass', '')
            db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
        db.commit()
        audit_log('settings_update', 'SMTP-Einstellungen geändert')
        flash('E-Mail-Einstellungen gespeichert.', 'success')
        return redirect(url_for('settings'))

    # Settings aus DB laden
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    smtp = {r['key']: r['value'] for r in rows}
    smtp_configured, _ = _validate_mail_config(_load_mail_config(db))
    return render_template('settings.html', smtp=smtp, smtp_configured=smtp_configured, db_path=DB_PATH)


# === Backup / Restore ===

def _setting_bool(value):
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _setting_int(value, default, min_value=0, max_value=999):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(parsed, max_value))


def _valid_time_or_default(value, default):
    text = str(value or '').strip()
    match = re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', text)
    return text if match else default


def _backup_week_marker(day):
    year, week, _ = day.isocalendar()
    return f'{year}-W{week:02d}'


def _set_setting(db, key, value):
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))


def get_backup_settings(db):
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    raw = dict(BACKUP_SETTING_DEFAULTS)
    raw.update({r['key']: r['value'] for r in rows if r['key'] in BACKUP_SETTING_DEFAULTS})
    public_cfg = get_public_config(db)
    if not raw.get('backup_email_to'):
        raw['backup_email_to'] = public_cfg.get('org_email') or ''

    return {
        'auto_enabled': _setting_bool(raw.get('backup_auto_enabled')),
        'auto_time': _valid_time_or_default(raw.get('backup_auto_time'), BACKUP_SETTING_DEFAULTS['backup_auto_time']),
        'retention_daily': _setting_int(raw.get('backup_retention_daily'), 3, 0, 31),
        'retention_weekly': _setting_int(raw.get('backup_retention_weekly'), 4, 0, 104),
        'retention_monthly': _setting_int(raw.get('backup_retention_monthly'), 6, 0, 120),
        'retention_yearly': _setting_int(raw.get('backup_retention_yearly'), 3, 0, 20),
        'email_enabled': _setting_bool(raw.get('backup_email_enabled')),
        'email_weekday': _setting_int(raw.get('backup_email_weekday'), 6, 0, 6),
        'email_time': _valid_time_or_default(raw.get('backup_email_time'), BACKUP_SETTING_DEFAULTS['backup_email_time']),
        'email_to': (raw.get('backup_email_to') or '').strip(),
        'email_max_mb': _setting_int(raw.get('backup_email_max_mb'), 20, 1, 2000),
        'drive_enabled': _setting_bool(raw.get('backup_drive_enabled')),
        'drive_folder_id': (raw.get('backup_drive_folder_id') or '').strip(),
        'drive_last_upload': raw.get('backup_drive_last_upload') or '',
        'drive_last_check': raw.get('backup_drive_last_check') or '',
        'drive_last_error': raw.get('backup_drive_last_error') or '',
        'auto_last_run_date': raw.get('backup_auto_last_run_date') or '',
        'email_last_attempt_week': raw.get('backup_email_last_attempt_week') or '',
        'email_last_sent_week': raw.get('backup_email_last_sent_week') or '',
    }


def _checkpoint_database():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError('Datenbankdatei wurde nicht gefunden.')
    with sqlite3.connect(DB_PATH) as checkpoint_db:
        checkpoint_db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def write_backup_zip(zip_path):
    """Schreibt ein vollstaendiges ZIP-Backup an den angegebenen Pfad."""
    import zipfile

    with BACKUP_JOB_LOCK:
        _checkpoint_database()
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(DB_PATH, 'eeg_data.db')
            zf.writestr(
                'backup_manifest.txt',
                f"created_at={local_now().isoformat(timespec='seconds')}\n"
                f"database=eeg_data.db\n"
                f"invoices_folder=invoices/\n"
            )
            if os.path.isdir(INVOICE_FOLDER):
                for fname in os.listdir(INVOICE_FOLDER):
                    fpath = os.path.join(INVOICE_FOLDER, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, f'invoices/{fname}')


def create_local_backup(prefix='eeg_auto'):
    os.makedirs(BACKUP_FOLDER, exist_ok=True)
    timestamp = local_now().strftime('%Y%m%d_%H%M%S')
    zip_filename = f'{prefix}_{timestamp}.zip'
    zip_path = os.path.join(BACKUP_FOLDER, zip_filename)
    write_backup_zip(zip_path)
    return zip_path, zip_filename


def _parse_backup_timestamp(filename):
    match = re.match(r'^eeg_(?:auto|manual)_(\d{8}_\d{6})\.zip$', filename)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), '%Y%m%d_%H%M%S').replace(tzinfo=APP_TIMEZONE)
    except ValueError:
        return None


def list_local_backups():
    backups = []
    if not os.path.isdir(BACKUP_FOLDER):
        return backups
    for fname in os.listdir(BACKUP_FOLDER):
        if not fname.endswith('.zip'):
            continue
        created_at = _parse_backup_timestamp(fname)
        if not created_at:
            continue
        fpath = os.path.join(BACKUP_FOLDER, fname)
        if not os.path.isfile(fpath):
            continue
        backups.append({
            'name': fname,
            'path': fpath,
            'size': os.path.getsize(fpath),
            'created_at': created_at,
            'kind': 'Automatisch' if fname.startswith('eeg_auto_') else 'Manuell',
        })
    backups.sort(key=lambda item: item['created_at'], reverse=True)
    return backups


def local_backup_path_for_delete(filename):
    """Validiert eine lokale Backup-Datei und liefert den sicheren Vollpfad."""
    backup_name = os.path.basename(str(filename or '').strip())
    if backup_name != str(filename or '').strip():
        raise ValueError('Ungültiger Backup-Dateiname.')
    if not _parse_backup_timestamp(backup_name):
        raise ValueError('Ungültiger Backup-Dateiname.')
    backup_path = os.path.abspath(os.path.join(BACKUP_FOLDER, backup_name))
    backup_root = os.path.abspath(BACKUP_FOLDER)
    if os.path.commonpath([backup_root, backup_path]) != backup_root:
        raise ValueError('Ungültiger Backup-Pfad.')
    if not os.path.isfile(backup_path):
        raise FileNotFoundError('Backup-Datei wurde nicht gefunden.')
    return backup_path, backup_name


def _google_libs_available():
    try:
        import google.auth.transport.requests  # noqa: F401
        import google.oauth2.credentials  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        import googleapiclient.http  # noqa: F401
    except ImportError:
        return False
    return True


def _secret_cipher_for_key(raw_key):
    if not raw_key:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise RuntimeError('cryptography fehlt. Bitte requirements.txt installieren.') from e

    key_text = str(raw_key).strip()
    try:
        return Fernet(key_text.encode('ascii'))
    except Exception:
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(key_text.encode('utf-8')).digest())
        return Fernet(derived_key)


def _secret_cipher_candidates():
    keys = []
    data_key = os.environ.get('EEG_DATA_ENCRYPTION_KEY')
    if data_key:
        keys.append(data_key)
    if _SECRET_KEY and _SECRET_KEY not in keys:
        keys.append(_SECRET_KEY)
    return [_secret_cipher_for_key(key) for key in keys if key]


def _secret_cipher():
    candidates = _secret_cipher_candidates()
    return candidates[0] if candidates else None


def _atomic_write_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f'{path}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def _write_private_json_file(path, payload):
    """Speichert lokale Secret-JSONs verschluesselt, wenn ein persistenter Key vorhanden ist."""
    cipher = _secret_cipher()
    if cipher:
        encrypted = cipher.encrypt(json.dumps(payload, ensure_ascii=False).encode('utf-8')).decode('ascii')
        _atomic_write_json_file(path, {
            '_eeg_encrypted': 1,
            'cipher': 'fernet-sha256-v1',
            'payload': encrypted,
        })
        return
    if _IS_PRODUCTION:
        raise RuntimeError('EEG_DATA_ENCRYPTION_KEY oder EEG_SECRET_KEY muss fuer Secret-Speicherung gesetzt sein.')
    app.logger.warning('Secret JSON wird unverschluesselt gespeichert, weil kein persistenter Encryption-Key gesetzt ist.')
    _atomic_write_json_file(path, payload)


def _load_private_json_file(path):
    with open(path, encoding='utf-8') as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or not payload.get('_eeg_encrypted'):
        return payload

    candidates = _secret_cipher_candidates()
    if not candidates:
        raise RuntimeError('Secret-Datei ist verschluesselt, aber EEG_DATA_ENCRYPTION_KEY/EEG_SECRET_KEY fehlt.')
    encrypted = str(payload.get('payload') or '').encode('ascii')
    for cipher in candidates:
        try:
            decrypted = cipher.decrypt(encrypted)
            return json.loads(decrypted.decode('utf-8'))
        except Exception:
            continue
    raise RuntimeError('Secret-Datei konnte nicht entschluesselt werden. Encryption-Key pruefen.')


def _load_json_payload(file_field, text_field, label):
    upload = request.files.get(file_field)
    raw = ''
    if upload and upload.filename:
        raw = upload.read().decode('utf-8')
    else:
        raw = (request.form.get(text_field) or '').strip()
    if not raw:
        raise ValueError(f'{label} fehlt.')
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f'{label} ist kein gültiges JSON: {e}') from e


def _manual_google_client_payload():
    client_id = (request.form.get('google_client_id') or '').strip()
    client_secret = (request.form.get('google_client_secret') or '').strip()
    if not client_id and not client_secret:
        return None
    if not client_id or not client_secret:
        raise ValueError('Client-ID und Client-Secret müssen beide ausgefüllt sein.')
    return {
        'web': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': (request.form.get('google_auth_uri') or 'https://accounts.google.com/o/oauth2/auth').strip(),
            'token_uri': (request.form.get('google_token_uri') or 'https://oauth2.googleapis.com/token').strip(),
            'redirect_uris': [_google_redirect_uri_for_display()],
        }
    }


def _manual_google_token_payload():
    refresh_token = (request.form.get('google_refresh_token') or '').strip()
    if not refresh_token:
        return None

    client_id = (request.form.get('google_token_client_id') or '').strip()
    client_secret = (request.form.get('google_token_client_secret') or '').strip()
    if (not client_id or not client_secret) and os.path.exists(GOOGLE_CLIENT_SECRETS_FILE):
        client_payload = _load_private_json_file(GOOGLE_CLIENT_SECRETS_FILE)
        section = client_payload.get('web') or client_payload.get('installed') or {}
        client_id = client_id or section.get('client_id', '')
        client_secret = client_secret or section.get('client_secret', '')

    if not client_id or not client_secret:
        raise ValueError('Für einen manuellen Token brauchen wir Refresh-Token, Client-ID und Client-Secret.')

    return {
        'token': (request.form.get('google_access_token') or '').strip(),
        'refresh_token': refresh_token,
        'token_uri': (request.form.get('google_token_token_uri') or 'https://oauth2.googleapis.com/token').strip(),
        'client_id': client_id,
        'client_secret': client_secret,
        'scopes': GOOGLE_DRIVE_SCOPES,
    }


def validate_google_client_config(payload):
    if not isinstance(payload, dict):
        raise ValueError('OAuth Client-Konfiguration muss ein JSON-Objekt sein.')
    section_name = 'web' if isinstance(payload.get('web'), dict) else 'installed'
    section = payload.get(section_name)
    if not isinstance(section, dict):
        raise ValueError('OAuth Client-JSON muss einen Bereich "web" oder "installed" enthalten.')
    missing = [
        key for key in ('client_id', 'client_secret', 'auth_uri', 'token_uri')
        if not section.get(key)
    ]
    if missing:
        raise ValueError(f'OAuth Client-JSON ist unvollständig: {", ".join(missing)} fehlt.')
    return section_name


def validate_google_token_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Token muss ein JSON-Objekt sein.')
    missing = [
        key for key in ('refresh_token', 'token_uri', 'client_id', 'client_secret')
        if not payload.get(key)
    ]
    if missing:
        raise ValueError(f'Token-JSON ist unvollständig: {", ".join(missing)} fehlt.')
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise RuntimeError('Google Drive Python-Bibliotheken fehlen. Bitte requirements.txt installieren.') from e
    Credentials.from_authorized_user_info(payload, GOOGLE_DRIVE_SCOPES)
    return True


def _pkce_code_verifier():
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b'=').decode('ascii')


def _pkce_code_challenge(code_verifier):
    digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def _oauth_verifier_fingerprint(code_verifier):
    return hashlib.sha256(code_verifier.encode('ascii')).hexdigest()[:12]


def _store_google_oauth_pkce(correlation_id, state, code_verifier):
    db = get_db()
    db.execute("DELETE FROM oauth_pkce_sessions WHERE expires_at <= ?", (utc_now_string(),))
    db.execute(
        """INSERT OR REPLACE INTO oauth_pkce_sessions
           (id, user_id, state, code_verifier, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, datetime(?, '+15 minutes'))""",
        (
            correlation_id,
            current_user.id if current_user and current_user.is_authenticated else None,
            state,
            code_verifier,
            utc_now_string(),
            utc_now_string(),
        )
    )
    db.commit()


def _pop_google_oauth_pkce(correlation_id, state):
    db = get_db()
    row = db.execute(
        """SELECT * FROM oauth_pkce_sessions
           WHERE id=? AND state=? AND expires_at > ?""",
        (correlation_id, state, utc_now_string())
    ).fetchone()
    db.execute("DELETE FROM oauth_pkce_sessions WHERE id=?", (correlation_id,))
    db.commit()
    if not row:
        return None
    if row['user_id'] and current_user and current_user.is_authenticated and row['user_id'] != current_user.id:
        return None
    return row['code_verifier']


def get_google_drive_status():
    token_exists = os.path.exists(GOOGLE_TOKEN_FILE)
    client_exists = os.path.exists(GOOGLE_CLIENT_SECRETS_FILE)
    connected = False
    error = ''
    if token_exists and _google_libs_available():
        try:
            credentials = _load_google_drive_credentials(refresh=True)
            connected = credentials and credentials.valid
        except Exception as e:
            error = str(e)
    return {
        'libs_available': _google_libs_available(),
        'client_file': GOOGLE_CLIENT_SECRETS_FILE,
        'client_configured': client_exists,
        'token_file': GOOGLE_TOKEN_FILE,
        'connected': connected,
        'error': error,
        'redirect_uri': _google_redirect_uri_for_display(),
    }


def _google_redirect_uri():
    return GOOGLE_OAUTH_REDIRECT_URI or public_url_for('admin_backup_google_callback')


def _google_redirect_uri_for_display():
    if GOOGLE_OAUTH_REDIRECT_URI:
        return GOOGLE_OAUTH_REDIRECT_URI
    return public_url_for('admin_backup_google_callback')


def _google_drive_flow():
    if not os.path.exists(GOOGLE_CLIENT_SECRETS_FILE):
        raise RuntimeError(f'Google OAuth Client-Datei fehlt: {GOOGLE_CLIENT_SECRETS_FILE}')
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as e:
        raise RuntimeError('Google Drive Python-Bibliotheken fehlen. Bitte requirements.txt installieren.') from e
    client_config = _load_private_json_file(GOOGLE_CLIENT_SECRETS_FILE)
    return Flow.from_client_config(
        client_config,
        scopes=GOOGLE_DRIVE_SCOPES,
        redirect_uri=_google_redirect_uri(),
    )


def _load_google_drive_credentials(refresh=False):
    if not os.path.exists(GOOGLE_TOKEN_FILE):
        return None
    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise RuntimeError('Google Drive Python-Bibliotheken fehlen. Bitte requirements.txt installieren.') from e

    token_payload = _load_private_json_file(GOOGLE_TOKEN_FILE)
    credentials = Credentials.from_authorized_user_info(token_payload, GOOGLE_DRIVE_SCOPES)
    if refresh and credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleAuthRequest())
        _write_private_json_file(GOOGLE_TOKEN_FILE, json.loads(credentials.to_json()))
    return credentials


def _google_drive_service():
    credentials = _load_google_drive_credentials(refresh=True)
    if not credentials or not credentials.valid:
        raise RuntimeError('Google Drive ist noch nicht verbunden.')
    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError('Google Drive Python-Bibliotheken fehlen. Bitte requirements.txt installieren.') from e
    return build('drive', 'v3', credentials=credentials, cache_discovery=False)


def check_google_drive_connection(db):
    service = _google_drive_service()
    service.files().list(pageSize=1, fields='files(id,name)').execute()
    checked_at = local_now().isoformat(timespec='seconds')
    _set_setting(db, 'backup_drive_last_check', checked_at)
    _set_setting(db, 'backup_drive_last_error', '')
    db.commit()
    return checked_at


def upload_backup_to_google_drive(db, backup_path):
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as e:
        raise RuntimeError('Google Drive Python-Bibliotheken fehlen. Bitte requirements.txt installieren.') from e

    settings = get_backup_settings(db)
    service = _google_drive_service()
    backup_name = os.path.basename(backup_path)
    metadata = {'name': backup_name}
    if settings['drive_folder_id']:
        metadata['parents'] = [settings['drive_folder_id']]
    media = MediaFileUpload(backup_path, mimetype='application/zip', resumable=True)
    uploaded = service.files().create(
        body=metadata,
        media_body=media,
        fields='id,name,webViewLink',
        supportsAllDrives=True,
    ).execute()
    _set_setting(db, 'backup_drive_last_upload', local_now().isoformat(timespec='seconds'))
    _set_setting(db, 'backup_drive_last_error', '')
    db.commit()
    return uploaded


def _drive_query_literal(value):
    return str(value).replace('\\', '\\\\').replace("'", "\\'")


def _is_google_backup_name(filename):
    return bool(_parse_backup_timestamp(str(filename or '').strip()))


def _normalize_google_drive_backup_file(item):
    size = item.get('size')
    try:
        size = int(size) if size is not None else 0
    except (TypeError, ValueError):
        size = 0
    return {
        'id': item.get('id', ''),
        'name': item.get('name', ''),
        'size': size,
        'created_at': item.get('createdTime') or item.get('modifiedTime') or '',
        'modified_at': item.get('modifiedTime') or '',
        'web_view_link': item.get('webViewLink') or '',
        'mime_type': item.get('mimeType') or '',
    }


def list_google_drive_backups(db, limit=50):
    """Listet von dieser App erreichbare EEG-Backup-ZIP-Dateien in Google Drive."""
    settings = get_backup_settings(db)
    service = _google_drive_service()
    query_parts = [
        "trashed=false",
        "name contains 'eeg_'",
        "name contains '.zip'",
    ]
    if settings['drive_folder_id']:
        folder_id = _drive_query_literal(settings['drive_folder_id'])
        query_parts.append(f"'{folder_id}' in parents")
    response = service.files().list(
        q=' and '.join(query_parts),
        pageSize=max(1, min(int(limit), 100)),
        fields='files(id,name,size,createdTime,modifiedTime,webViewLink,mimeType)',
        orderBy='createdTime desc',
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    backups = []
    for item in response.get('files', []):
        if _is_google_backup_name(item.get('name')):
            backups.append(_normalize_google_drive_backup_file(item))
    return backups


def trash_google_drive_backup(db, file_id):
    """Verschiebt ein von der App verwaltbares Drive-Backup in den Papierkorb."""
    drive_file_id = str(file_id or '').strip()
    if not re.match(r'^[A-Za-z0-9_-]{8,}$', drive_file_id):
        raise ValueError('Ungültige Google Drive Datei-ID.')

    service = _google_drive_service()
    metadata = service.files().get(
        fileId=drive_file_id,
        fields='id,name,mimeType,trashed',
        supportsAllDrives=True,
    ).execute()
    backup_name = metadata.get('name') or ''
    if metadata.get('trashed'):
        raise ValueError('Dieses Google Drive Backup liegt bereits im Papierkorb.')
    if not _is_google_backup_name(backup_name):
        raise ValueError('Aus Sicherheitsgründen können nur EEG-Backup-ZIP-Dateien gelöscht werden.')

    deleted = service.files().update(
        fileId=drive_file_id,
        body={'trashed': True},
        fields='id,name,trashed',
        supportsAllDrives=True,
    ).execute()
    _set_setting(db, 'backup_drive_last_error', '')
    db.commit()
    return deleted


def apply_backup_retention(settings):
    """Wendet eine einfache Grossvater-Vater-Sohn-Aufbewahrung auf Auto-Backups an."""
    auto_backups = [
        item for item in list_local_backups()
        if item['name'].startswith('eeg_auto_')
    ]
    now = local_now()
    kept_buckets = set()
    keep_paths = set()

    for item in auto_backups:
        ts = item['created_at']
        age_days = (now.date() - ts.date()).days
        month_distance = (now.year - ts.year) * 12 + (now.month - ts.month)
        year_distance = now.year - ts.year

        bucket = None
        if age_days < settings['retention_daily']:
            bucket = f"day:{ts.strftime('%Y-%m-%d')}"
        elif age_days < settings['retention_weekly'] * 7:
            if settings['retention_weekly'] > 0:
                bucket = f"week:{ts.strftime('%G-W%V')}"
        elif month_distance < settings['retention_monthly']:
            if settings['retention_monthly'] > 0:
                bucket = f"month:{ts.strftime('%Y-%m')}"
        elif year_distance < settings['retention_yearly']:
            if settings['retention_yearly'] > 0:
                bucket = f"year:{ts.strftime('%Y')}"

        if bucket and bucket not in kept_buckets:
            kept_buckets.add(bucket)
            keep_paths.add(item['path'])

    deleted = 0
    for item in auto_backups:
        if item['path'] in keep_paths:
            continue
        try:
            os.remove(item['path'])
            deleted += 1
        except OSError:
            app.logger.warning('Could not delete old backup %s', item['path'], exc_info=True)
    return deleted


def _time_reached(now, time_text):
    hour, minute = [int(part) for part in _valid_time_or_default(time_text, '00:00').split(':')]
    return (now.hour, now.minute) >= (hour, minute)


def send_backup_email(db, backup_path, recipient, max_mb):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    if not _is_valid_email(recipient):
        raise RuntimeError('Empfängeradresse für Backup-Mail ist ungültig.')

    size_mb = os.path.getsize(backup_path) / 1024 / 1024
    if size_mb > max_mb:
        raise RuntimeError(f'Backup ist {size_mb:.1f} MB groß und überschreitet das konfigurierte Mail-Limit von {max_mb} MB.')

    mail_cfg = _get_valid_mail_config(db)
    public_cfg = get_public_config(db)
    backup_name = os.path.basename(backup_path)
    subject = f"EEG Backup {local_now().strftime('%d.%m.%Y')}"
    body_text = (
        f"Automatisches Backup der Webapp {public_cfg['org_name']}.\n\n"
        f"Datei: {backup_name}\n"
        f"Groesse: {size_mb:.1f} MB\n"
        f"Erstellt am: {local_now().strftime('%d.%m.%Y %H:%M')} {getattr(APP_TIMEZONE, 'key', 'Europe/Vienna')}\n\n"
        "Bitte diese Datei geschuetzt aufbewahren, da sie personenbezogene Daten enthalten kann."
    )

    msg = MIMEMultipart('mixed')
    msg['From'] = mail_cfg['from_header']
    msg['Reply-To'] = mail_cfg['reply_to_header']
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

    with open(backup_path, 'rb') as f:
        attachment = MIMEApplication(f.read(), _subtype='zip')
    attachment.add_header('Content-Disposition', 'attachment', filename=backup_name)
    msg.attach(attachment)

    _log_mail_send(mail_cfg, recipient, subject)
    with smtplib.SMTP(mail_cfg['smtp_host'], mail_cfg['smtp_port']) as server:
        if mail_cfg['smtp_tls']:
            server.starttls()
        server.login(mail_cfg['smtp_user'], mail_cfg['smtp_pass'])
        server.send_message(msg, from_addr=mail_cfg['from_address'], to_addrs=[recipient])


def _run_due_backup_jobs():
    with app.app_context():
        db = get_db()
        settings = get_backup_settings(db)
        now = local_now()
        today = now.strftime('%Y-%m-%d')
        week_marker = _backup_week_marker(now.date())

        if settings['auto_enabled'] and _time_reached(now, settings['auto_time']):
            if settings['auto_last_run_date'] != today:
                zip_path, zip_filename = create_local_backup('eeg_auto')
                deleted = apply_backup_retention(settings)
                drive_detail = ''
                if settings['drive_enabled']:
                    try:
                        uploaded = upload_backup_to_google_drive(db, zip_path)
                        drive_detail = f' · Google Drive Upload: {uploaded.get("id")}'
                    except Exception as e:
                        _set_setting(db, 'backup_drive_last_error', str(e))
                        db.commit()
                        app.logger.exception('Google Drive backup upload failed')
                        audit_log('backup_drive_failed', f'Google Drive Upload fehlgeschlagen: {zip_filename} ({e})')
                _set_setting(db, 'backup_auto_last_run_date', today)
                db.commit()
                audit_log('backup_auto', f'Automatisches Backup erstellt: {zip_filename} ({deleted} alte Backups entfernt){drive_detail}')
                app.logger.info('Automatic backup created: %s', zip_path)

        if (settings['email_enabled']
                and now.weekday() == settings['email_weekday']
                and _time_reached(now, settings['email_time'])
                and settings['email_last_attempt_week'] != week_marker):
            email_path = None
            try:
                email_path, zip_filename = create_local_backup('eeg_mail')
                send_backup_email(db, email_path, settings['email_to'], settings['email_max_mb'])
                _set_setting(db, 'backup_email_last_sent_week', week_marker)
                audit_log('backup_email', f'Woechentliches Backup per Mail versendet: {zip_filename} an {settings["email_to"]}')
            except Exception as e:
                app.logger.exception('Weekly backup mail failed')
                audit_log('backup_email_failed', f'Woechentliches Backup-Mail fehlgeschlagen: {e}')
            finally:
                _set_setting(db, 'backup_email_last_attempt_week', week_marker)
                db.commit()
                if email_path and os.path.exists(email_path):
                    try:
                        os.remove(email_path)
                    except OSError:
                        app.logger.warning('Could not remove temporary mail backup %s', email_path, exc_info=True)


def _backup_scheduler_loop():
    while True:
        try:
            _run_due_backup_jobs()
        except Exception:
            app.logger.exception('Automatic backup scheduler failed')
        time.sleep(60)


def start_backup_scheduler():
    global BACKUP_SCHEDULER_STARTED
    with BACKUP_SCHEDULER_LOCK:
        if BACKUP_SCHEDULER_STARTED:
            return
        thread = threading.Thread(target=_backup_scheduler_loop, name='eeg-backup-scheduler', daemon=True)
        thread.start()
        BACKUP_SCHEDULER_STARTED = True


def get_backup_info():
    invoice_count = 0
    invoice_size = 0
    if os.path.isdir(INVOICE_FOLDER):
        for fname in os.listdir(INVOICE_FOLDER):
            fpath = os.path.join(INVOICE_FOLDER, fname)
            if os.path.isfile(fpath):
                invoice_count += 1
                invoice_size += os.path.getsize(fpath)
    return {
        'db_path': DB_PATH,
        'db_size': os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0,
        'invoice_folder': INVOICE_FOLDER,
        'backup_folder': BACKUP_FOLDER,
        'invoice_count': invoice_count,
        'invoice_size': invoice_size,
    }


@app.route('/admin/backup')
@admin_required
def admin_backup():
    """Admin-Seite fuer Backup und Restore."""
    db = get_db()
    smtp_configured, _ = _validate_mail_config(_load_mail_config(db))
    google_drive = get_google_drive_status()
    drive_backups = []
    drive_backups_error = ''
    if google_drive['connected']:
        try:
            drive_backups = list_google_drive_backups(db)
        except Exception as e:
            drive_backups_error = str(e)
            app.logger.warning('Could not list Google Drive backups: %s', e, exc_info=True)
    return render_template(
        'admin_backup.html',
        info=get_backup_info(),
        backup_settings=get_backup_settings(db),
        backup_files=list_local_backups()[:20],
        google_drive=google_drive,
        drive_backups=drive_backups,
        drive_backups_error=drive_backups_error,
        smtp_configured=smtp_configured,
        weekdays=[
            (0, 'Montag'),
            (1, 'Dienstag'),
            (2, 'Mittwoch'),
            (3, 'Donnerstag'),
            (4, 'Freitag'),
            (5, 'Samstag'),
            (6, 'Sonntag'),
        ],
    )


@app.route('/admin/backup/settings', methods=['POST'])
@admin_required
def admin_backup_settings():
    """Speichert Zeitplan, Aufbewahrung und Mail-Backup-Konfiguration."""
    db = get_db()
    email_enabled = form_switch_enabled('backup_email_enabled')
    email_to = (request.form.get('backup_email_to') or '').strip()
    if email_enabled and not _is_valid_email(email_to):
        flash('Bitte eine gültige Empfängeradresse für das Mail-Backup eintragen.', 'danger')
        return redirect(url_for('admin_backup'))
    drive_enabled = form_switch_enabled('backup_drive_enabled')
    if drive_enabled and not get_google_drive_status()['connected']:
        flash('Google Drive muss zuerst verbunden werden, bevor der automatische Drive-Upload aktiviert werden kann.', 'danger')
        return redirect(url_for('admin_backup'))

    values = {
        'backup_auto_enabled': 'true' if form_switch_enabled('backup_auto_enabled') else 'false',
        'backup_auto_time': _valid_time_or_default(request.form.get('backup_auto_time'), BACKUP_SETTING_DEFAULTS['backup_auto_time']),
        'backup_retention_daily': _setting_int(request.form.get('backup_retention_daily'), 3, 0, 31),
        'backup_retention_weekly': _setting_int(request.form.get('backup_retention_weekly'), 4, 0, 104),
        'backup_retention_monthly': _setting_int(request.form.get('backup_retention_monthly'), 6, 0, 120),
        'backup_retention_yearly': _setting_int(request.form.get('backup_retention_yearly'), 3, 0, 20),
        'backup_email_enabled': 'true' if email_enabled else 'false',
        'backup_email_weekday': _setting_int(request.form.get('backup_email_weekday'), 6, 0, 6),
        'backup_email_time': _valid_time_or_default(request.form.get('backup_email_time'), BACKUP_SETTING_DEFAULTS['backup_email_time']),
        'backup_email_to': email_to,
        'backup_email_max_mb': _setting_int(request.form.get('backup_email_max_mb'), 20, 1, 2000),
        'backup_drive_enabled': 'true' if drive_enabled else 'false',
        'backup_drive_folder_id': (request.form.get('backup_drive_folder_id') or '').strip(),
    }
    for key, value in values.items():
        _set_setting(db, key, value)
    db.commit()

    settings = get_backup_settings(db)
    deleted = apply_backup_retention(settings)
    audit_log('backup_settings_update', f'Backup-Konfiguration geändert ({deleted} alte Auto-Backups entfernt)')
    flash('Backup-Konfiguration gespeichert.', 'success')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/connect')
@admin_required
def admin_backup_google_connect():
    """Startet den Google OAuth-Flow fuer Drive-Backups."""
    try:
        flow = _google_drive_flow()
        correlation_id = secrets.token_hex(12)
        oauth_state = secrets.token_urlsafe(32)
        code_verifier = _pkce_code_verifier()
        code_challenge = _pkce_code_challenge(code_verifier)
        _store_google_oauth_pkce(correlation_id, oauth_state, code_verifier)
        session['google_drive_oauth_state'] = oauth_state
        session['google_drive_oauth_correlation_id'] = correlation_id
        session.modified = True
        app.logger.info(
            'Google Drive OAuth start | correlation=%s | verifier_stored=%s | verifier_fp=%s | redirect_uri=%s | secure_cookie=%s | samesite=%s',
            correlation_id,
            True,
            _oauth_verifier_fingerprint(code_verifier),
            _google_redirect_uri(),
            app.config.get('SESSION_COOKIE_SECURE'),
            app.config.get('SESSION_COOKIE_SAMESITE'),
        )
        authorization_url, state = flow.authorization_url(
            state=oauth_state,
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            code_challenge=code_challenge,
            code_challenge_method='S256',
        )
        if state != oauth_state:
            app.logger.warning('Google Drive OAuth state changed by library | correlation=%s', correlation_id)
        return redirect(authorization_url)
    except Exception as e:
        audit_log('backup_drive_connect_failed', f'Google Drive Verbindung fehlgeschlagen: {e}')
        flash(f'Google Drive Verbindung konnte nicht gestartet werden: {e}', 'danger')
        return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/client-config', methods=['POST'])
@admin_required
def admin_backup_google_client_config():
    """Speichert die Google OAuth Client-Konfiguration aus dem Webinterface."""
    try:
        payload = _manual_google_client_payload()
        if payload is None:
            payload = _load_json_payload('google_client_file', 'google_client_json', 'OAuth Client-JSON')
        section_name = validate_google_client_config(payload)
        _write_private_json_file(GOOGLE_CLIENT_SECRETS_FILE, payload)
        if os.path.exists(GOOGLE_TOKEN_FILE):
            os.remove(GOOGLE_TOKEN_FILE)
        db = get_db()
        _set_setting(db, 'backup_drive_enabled', 'false')
        _set_setting(db, 'backup_drive_last_error', '')
        db.commit()
        audit_log('backup_drive_client_config', f'Google OAuth Client-Konfiguration gespeichert ({section_name})')
        flash('Google OAuth Client-Konfiguration gespeichert. Ein vorhandener Token wurde zur Sicherheit entfernt; bitte Google Drive neu verbinden.', 'success')
    except Exception as e:
        audit_log('backup_drive_client_config_failed', f'Google OAuth Client-Konfiguration fehlgeschlagen: {e}')
        flash(f'Google OAuth Client-Konfiguration konnte nicht gespeichert werden: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/token', methods=['POST'])
@admin_required
def admin_backup_google_token():
    """Speichert ein vorhandenes Google OAuth Token-JSON aus dem Webinterface."""
    try:
        payload = _manual_google_token_payload()
        if payload is None:
            payload = _load_json_payload('google_token_file', 'google_token_json', 'Google Token-JSON')
        validate_google_token_payload(payload)
        _write_private_json_file(GOOGLE_TOKEN_FILE, payload)
        db = get_db()
        _set_setting(db, 'backup_drive_last_error', '')
        db.commit()
        audit_log('backup_drive_token', 'Google Drive Token hinterlegt')
        flash('Google Drive Token wurde gespeichert.', 'success')
    except Exception as e:
        audit_log('backup_drive_token_failed', f'Google Drive Token konnte nicht gespeichert werden: {e}')
        flash(f'Google Drive Token konnte nicht gespeichert werden: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/callback')
@admin_required
def admin_backup_google_callback():
    """OAuth Callback fuer Google Drive."""
    correlation_id = session.get('google_drive_oauth_correlation_id')
    code_verifier = None
    try:
        state = session.get('google_drive_oauth_state')
        callback_state = request.args.get('state')
        verifier_found = False
        if state and callback_state and correlation_id:
            code_verifier = _pop_google_oauth_pkce(correlation_id, callback_state)
            verifier_found = bool(code_verifier)
        app.logger.info(
            'Google Drive OAuth callback | correlation=%s | session_state_present=%s | state_matches=%s | verifier_found=%s | scheme=%s | host=%s',
            correlation_id or 'missing',
            bool(state),
            bool(state and state == callback_state),
            verifier_found,
            request.scheme,
            request.host,
        )
        if not state or state != callback_state:
            raise RuntimeError('OAuth-State ist ungültig.')
        if not code_verifier:
            raise RuntimeError('PKCE Code-Verifier wurde in der Session nicht gefunden. Bitte Google Drive erneut verbinden.')
        flow = _google_drive_flow()
        flow.fetch_token(authorization_response=request.url, code_verifier=code_verifier)
        credentials = flow.credentials
        _write_private_json_file(GOOGLE_TOKEN_FILE, json.loads(credentials.to_json()))
        db = get_db()
        _set_setting(db, 'backup_drive_last_error', '')
        db.commit()
        audit_log('backup_drive_connect', 'Google Drive verbunden')
        flash('Google Drive wurde erfolgreich verbunden.', 'success')
    except Exception as e:
        audit_log('backup_drive_connect_failed', f'Google Drive Verbindung fehlgeschlagen: {e}')
        flash(f'Google Drive konnte nicht verbunden werden: {e}', 'danger')
    finally:
        session.pop('google_drive_oauth_state', None)
        session.pop('google_drive_oauth_correlation_id', None)
        session.modified = True
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/client-config/delete', methods=['POST'])
@admin_required
def admin_backup_google_client_config_delete():
    """Entfernt lokale Google Client- und Token-Dateien."""
    try:
        for path in (GOOGLE_TOKEN_FILE, GOOGLE_CLIENT_SECRETS_FILE):
            if os.path.exists(path):
                os.remove(path)
        db = get_db()
        _set_setting(db, 'backup_drive_enabled', 'false')
        _set_setting(db, 'backup_drive_last_error', '')
        db.commit()
        audit_log('backup_drive_client_config_delete', 'Google Drive Client-Konfiguration und Token entfernt')
        flash('Google Drive Client-Konfiguration und Token wurden entfernt.', 'success')
    except Exception as e:
        audit_log('backup_drive_client_config_delete_failed', f'Google Drive Client-Konfiguration konnte nicht entfernt werden: {e}')
        flash(f'Google Drive Client-Konfiguration konnte nicht entfernt werden: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/disconnect', methods=['POST'])
@admin_required
def admin_backup_google_disconnect():
    """Entfernt das lokal gespeicherte Google OAuth-Token."""
    try:
        if os.path.exists(GOOGLE_TOKEN_FILE):
            os.remove(GOOGLE_TOKEN_FILE)
        db = get_db()
        _set_setting(db, 'backup_drive_enabled', 'false')
        _set_setting(db, 'backup_drive_last_error', '')
        db.commit()
        audit_log('backup_drive_disconnect', 'Google Drive getrennt')
        flash('Google Drive wurde getrennt. Automatischer Drive-Upload ist deaktiviert.', 'success')
    except Exception as e:
        audit_log('backup_drive_disconnect_failed', f'Google Drive Trennung fehlgeschlagen: {e}')
        flash(f'Google Drive konnte nicht getrennt werden: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/test', methods=['POST'])
@admin_required
def admin_backup_google_test():
    """Prüft Refresh-Token und Google Drive API Zugriff."""
    db = get_db()
    try:
        checked_at = check_google_drive_connection(db)
        audit_log('backup_drive_test', 'Google Drive Verbindung erfolgreich geprüft')
        flash(f'Google Drive Verbindung erfolgreich geprüft: {checked_at}', 'success')
    except Exception as e:
        _set_setting(db, 'backup_drive_last_error', str(e))
        db.commit()
        audit_log('backup_drive_test_failed', f'Google Drive Verbindungstest fehlgeschlagen: {e}')
        flash(f'Google Drive Verbindungstest fehlgeschlagen: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/run', methods=['POST'])
@admin_required
def admin_backup_run():
    """Erstellt ein lokales Backup im Backup-Ordner."""
    try:
        zip_path, zip_filename = create_local_backup('eeg_manual')
        audit_log('backup_manual', f'Manuelles lokales Backup erstellt: {zip_filename}')
        flash(f'Lokales Backup erstellt: {zip_filename}', 'success')
        app.logger.info('Manual local backup created: %s', zip_path)
    except Exception as e:
        audit_log('backup_manual_failed', f'Manuelles lokales Backup fehlgeschlagen: {e}')
        flash(f'Backup konnte nicht erstellt werden: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/upload-drive', methods=['POST'])
@admin_required
def admin_backup_upload_drive():
    """Kopiert eine lokale Backup-Datei manuell nach Google Drive."""
    filename = request.form.get('backup_name', '')
    try:
        backup_path, backup_name = local_backup_path_for_delete(filename)
        uploaded = upload_backup_to_google_drive(get_db(), backup_path)
        audit_log('backup_drive_upload', f'Backup nach Google Drive kopiert: {backup_name} ({uploaded.get("id")})')
        flash(f'Backup wurde nach Google Drive kopiert: {backup_name}', 'success')
    except Exception as e:
        db = get_db()
        _set_setting(db, 'backup_drive_last_error', str(e))
        db.commit()
        audit_log('backup_drive_failed', f'Google Drive Upload fehlgeschlagen: {filename} ({e})')
        flash(f'Google Drive Upload fehlgeschlagen: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/google/delete', methods=['POST'])
@admin_required
def admin_backup_google_delete():
    """Verschiebt eine Google Drive Backup-Datei in den Papierkorb."""
    drive_file_id = request.form.get('drive_file_id', '')
    try:
        deleted = trash_google_drive_backup(get_db(), drive_file_id)
        backup_name = deleted.get('name') or drive_file_id
        audit_log('backup_drive_delete', f'Google Drive Backup in den Papierkorb verschoben: {backup_name} ({deleted.get("id")})')
        flash(f'Google Drive Backup wurde in den Papierkorb verschoben: {backup_name}', 'success')
    except Exception as e:
        db = get_db()
        _set_setting(db, 'backup_drive_last_error', str(e))
        db.commit()
        audit_log('backup_drive_delete_failed', f'Google Drive Backup konnte nicht gelöscht werden: {drive_file_id} ({e})')
        flash(f'Google Drive Backup konnte nicht gelöscht werden: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/delete', methods=['POST'])
@admin_required
def admin_backup_delete():
    """Löscht eine lokale Backup-Datei nach serverseitiger Sicherheitsprüfung."""
    filename = request.form.get('backup_name', '')
    try:
        backup_path, backup_name = local_backup_path_for_delete(filename)
        size_mb = os.path.getsize(backup_path) / 1024 / 1024
        os.remove(backup_path)
        audit_log('backup_delete', f'Lokales Backup gelöscht: {backup_name} ({size_mb:.1f} MB)')
        flash(f'Backup gelöscht: {backup_name}', 'success')
    except Exception as e:
        audit_log('backup_delete_failed', f'Backup-Löschung fehlgeschlagen: {filename} ({e})')
        flash(f'Backup konnte nicht gelöscht werden: {e}', 'danger')
    return redirect(url_for('admin_backup'))


@app.route('/admin/backup/send-mail', methods=['POST'])
@admin_required
def admin_backup_send_mail():
    """Sendet ein Backup sofort per Mail an die konfigurierte Adresse."""
    db = get_db()
    settings = get_backup_settings(db)
    recipient = (request.form.get('backup_email_to') or settings['email_to']).strip()
    max_mb = _setting_int(request.form.get('backup_email_max_mb'), settings['email_max_mb'], 1, 2000)
    email_path = None
    try:
        if not _is_valid_email(recipient):
            raise RuntimeError('Empfängeradresse für Backup-Mail ist ungültig.')
        email_path, zip_filename = create_local_backup('eeg_mail')
        send_backup_email(db, email_path, recipient, max_mb)
        audit_log('backup_email_manual', f'Backup-Mail manuell versendet: {zip_filename} an {recipient}')
        flash(f'Backup-Mail wurde an {recipient} gesendet.', 'success')
    except Exception as e:
        audit_log('backup_email_manual_failed', f'Manuelle Backup-Mail fehlgeschlagen: {e}')
        flash(f'Backup-Mail konnte nicht gesendet werden: {e}', 'danger')
    finally:
        if email_path and os.path.exists(email_path):
            try:
                os.remove(email_path)
            except OSError:
                app.logger.warning('Could not remove temporary mail backup %s', email_path, exc_info=True)
    return redirect(url_for('admin_backup'))


@app.route('/backup')
@admin_required
def backup_download():
    """Erstellt ein ZIP-Backup (DB + Rechnungs-PDFs) zum Download."""
    import tempfile

    timestamp = local_now().strftime('%Y%m%d_%H%M%S')
    zip_filename = f"eeg_backup_{timestamp}.zip"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    tmp.close()
    write_backup_zip(tmp.name)

    audit_log('backup_download', f'Backup heruntergeladen: {zip_filename}')

    response = send_file(tmp.name, as_attachment=True, download_name=zip_filename,
                         mimetype='application/zip')

    @response.call_on_close
    def cleanup_backup_file():
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    return response


@app.route('/backup/restore', methods=['POST'])
@admin_required
def backup_restore():
    """Stellt ein Backup aus einem ZIP-File wieder her."""
    import zipfile, tempfile, shutil

    if 'backup_file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('admin_backup'))

    file = request.files['backup_file']
    if not file.filename.lower().endswith('.zip'):
        flash('Nur ZIP-Dateien sind erlaubt.', 'danger')
        return redirect(url_for('admin_backup'))
    if request.form.get('restore_confirm') != '1':
        flash('Bitte bestätigen Sie die Wiederherstellung ausdrücklich.', 'danger')
        return redirect(url_for('admin_backup'))

    # Temporär speichern
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    file.save(tmp.name)
    tmp.close()

    try:
        if not zipfile.is_zipfile(tmp.name):
            flash('Ungültiges Backup: Die Datei ist kein lesbares ZIP-Archiv.', 'danger')
            return redirect(url_for('admin_backup'))

        with zipfile.ZipFile(tmp.name, 'r') as zf:
            names = validate_backup_zip(zf)

            # DB schließen
            close_db()

            # DB ersetzen
            target_db = safe_extract_zip_member(zf, 'eeg_data.db', os.path.dirname(DB_PATH))
            if os.path.abspath(target_db) != os.path.abspath(DB_PATH):
                shutil.move(target_db, DB_PATH)

            # PDFs wiederherstellen
            for name in names:
                if name.startswith('invoices/') and name != 'invoices/':
                    safe_extract_zip_member(zf, name, os.path.dirname(INVOICE_FOLDER))

        # WAL-Dateien entfernen falls vorhanden
        for suffix in ('-wal', '-shm'):
            wal_file = DB_PATH + suffix
            if os.path.exists(wal_file):
                os.remove(wal_file)

        audit_log('backup_restore', f'Backup wiederhergestellt aus: {file.filename}')
        flash('Backup erfolgreich wiederhergestellt. Bitte Server neu starten.', 'success')
    except Exception as e:
        audit_log('backup_restore_failed', f'Backup-Wiederherstellung fehlgeschlagen: {e}')
        flash(f'Fehler beim Wiederherstellen: {e}', 'danger')
    finally:
        os.unlink(tmp.name)

    return redirect(url_for('admin_backup'))


# === Datenbank-Wartung ===

def _quote_identifier(name):
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None


def _column_exists(conn, table_name, column_name):
    if not _table_exists(conn, table_name):
        return False
    return any(row['name'] == column_name for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})"))


def get_database_stats():
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    wal_path = DB_PATH + '-wal'
    shm_path = DB_PATH + '-shm'
    stats = {
        'db_path': DB_PATH,
        'db_size': db_size,
        'wal_size': os.path.getsize(wal_path) if os.path.exists(wal_path) else 0,
        'shm_size': os.path.getsize(shm_path) if os.path.exists(shm_path) else 0,
        'page_count': 0,
        'page_size': 0,
        'freelist_count': 0,
        'fragmentation_mb': 0,
        'tables': [],
    }
    if not os.path.exists(DB_PATH):
        return stats

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        stats['page_count'] = conn.execute("PRAGMA page_count").fetchone()[0]
        stats['page_size'] = conn.execute("PRAGMA page_size").fetchone()[0]
        stats['freelist_count'] = conn.execute("PRAGMA freelist_count").fetchone()[0]
        stats['fragmentation_mb'] = stats['freelist_count'] * stats['page_size'] / 1024 / 1024
        tables = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()
        for table in tables:
            name = table['name']
            count = conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(name)}").fetchone()[0]
            stats['tables'].append({'name': name, 'count': count})
    return stats


def _quality_result(title, status, detail, count=None):
    return {
        'title': title,
        'status': status,
        'detail': detail,
        'count': count,
    }


def _quality_count(conn, title, sql, error_detail, ok_detail='Keine Auffälligkeiten gefunden.'):
    count = conn.execute(sql).fetchone()[0]
    status = 'ok' if count == 0 else 'warning'
    detail = ok_detail if count == 0 else error_detail
    return _quality_result(title, status, detail, count)


def run_database_quality_check():
    results = []
    with BACKUP_JOB_LOCK:
        with sqlite3.connect(DB_PATH, timeout=60) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")

            integrity_rows = [row[0] for row in conn.execute("PRAGMA integrity_check").fetchall()]
            if integrity_rows == ['ok']:
                results.append(_quality_result('SQLite Integritätsprüfung', 'ok', 'Datenbankdatei ist konsistent.', 0))
            else:
                results.append(_quality_result('SQLite Integritätsprüfung', 'error', '; '.join(integrity_rows[:5]), len(integrity_rows)))

            fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_rows:
                results.append(_quality_result('Fremdschlüsselprüfung', 'error', f'{len(fk_rows)} verletzte Referenzen gefunden.', len(fk_rows)))
            else:
                results.append(_quality_result('Fremdschlüsselprüfung', 'ok', 'Keine verletzten Fremdschlüssel gefunden.', 0))

            if _table_exists(conn, 'invoice_items'):
                results.append(_quality_count(
                    conn,
                    'Abrechnungspositionen ohne Abrechnung',
                    """SELECT COUNT(*) FROM invoice_items ii
                       LEFT JOIN invoices i ON i.id = ii.invoice_id
                       WHERE i.id IS NULL""",
                    'Abrechnungspositionen verweisen auf gelöschte oder fehlende Abrechnungen.'
                ))
                results.append(_quality_count(
                    conn,
                    'Abrechnungspositionen ohne Mitglied',
                    """SELECT COUNT(*) FROM invoice_items ii
                       LEFT JOIN members m ON m.id = ii.member_id
                       WHERE m.id IS NULL""",
                    'Abrechnungspositionen verweisen auf gelöschte oder fehlende Mitglieder.'
                ))

            if _table_exists(conn, 'email_log'):
                results.append(_quality_count(
                    conn,
                    'E-Mail-Log ohne Abrechnung',
                    """SELECT COUNT(*) FROM email_log el
                       LEFT JOIN invoices i ON i.id = el.invoice_id
                       WHERE el.invoice_id IS NOT NULL AND i.id IS NULL""",
                    'E-Mail-Protokolle verweisen auf fehlende Abrechnungen.'
                ))
                results.append(_quality_count(
                    conn,
                    'E-Mail-Log ohne Mitglied',
                    """SELECT COUNT(*) FROM email_log el
                       LEFT JOIN members m ON m.id = el.member_id
                       WHERE el.member_id IS NOT NULL AND m.id IS NULL""",
                    'E-Mail-Protokolle verweisen auf fehlende Mitglieder.'
                ))

            if _table_exists(conn, 'contracts'):
                results.append(_quality_count(
                    conn,
                    'Verträge ohne Mitglied',
                    """SELECT COUNT(*) FROM contracts c
                       LEFT JOIN members m ON m.id = c.member_id
                       WHERE m.id IS NULL""",
                    'Verträge verweisen auf fehlende Mitglieder.'
                ))

            if _table_exists(conn, 'newsletter_log'):
                results.append(_quality_count(
                    conn,
                    'Newsletter-Log ohne Newsletter',
                    """SELECT COUNT(*) FROM newsletter_log nl
                       LEFT JOIN newsletters n ON n.id = nl.newsletter_id
                       WHERE n.id IS NULL""",
                    'Newsletter-Protokolle verweisen auf fehlende Newsletter.'
                ))
                results.append(_quality_count(
                    conn,
                    'Newsletter-Log ohne Mitglied',
                    """SELECT COUNT(*) FROM newsletter_log nl
                       LEFT JOIN members m ON m.id = nl.member_id
                       WHERE m.id IS NULL""",
                    'Newsletter-Protokolle verweisen auf fehlende Mitglieder.'
                ))

            if _column_exists(conn, 'users', 'member_id'):
                results.append(_quality_count(
                    conn,
                    'Benutzer ohne zugeordnetes Mitglied',
                    """SELECT COUNT(*) FROM users u
                       LEFT JOIN members m ON m.id = u.member_id
                       WHERE u.member_id IS NOT NULL AND m.id IS NULL""",
                    'Benutzerkonten verweisen auf fehlende Mitglieder.'
                ))

            if _table_exists(conn, 'members'):
                results.append(_quality_count(
                    conn,
                    'Aktive Mitglieder ohne Zählpunkt',
                    """SELECT COUNT(*) FROM members
                       WHERE active=1
                         AND COALESCE(TRIM(bezug_zp), '') = ''
                         AND COALESCE(TRIM(einspeiser_zp), '') = ''""",
                    'Aktive Mitglieder ohne Bezugs- oder Einspeise-Zählpunkt gefunden.',
                    ok_detail='Alle aktiven Mitglieder haben mindestens einen Zählpunkt.'
                ))

            if _table_exists(conn, 'measurements'):
                results.append(_quality_count(
                    conn,
                    'Messwerte ohne Import-Batch',
                    """SELECT COUNT(*) FROM measurements m
                       LEFT JOIN import_batches b ON b.id = m.batch_id
                       WHERE b.id IS NULL""",
                    'Messwerte verweisen auf fehlende Import-Batches.'
                ))
                results.append(_quality_count(
                    conn,
                    'Messwerte ohne Meter-Code',
                    """SELECT COUNT(*) FROM measurements m
                       LEFT JOIN meter_codes mc ON mc.id = m.meter_code_id
                       WHERE mc.id IS NULL""",
                    'Messwerte verweisen auf fehlende Meter-Codes.'
                ))
                results.append(_quality_count(
                    conn,
                    'Messwerte mit ungültigem Zeitintervall',
                    """SELECT COUNT(*) FROM measurements
                       WHERE timestamp_start >= timestamp_end OR interval_minutes <= 0""",
                    'Messwerte mit ungültigem Zeitraum oder Intervall gefunden.'
                ))
                results.append(_quality_count(
                    conn,
                    'Messwerte mit negativer Energie',
                    "SELECT COUNT(*) FROM measurements WHERE value_kwh < 0",
                    'Negative kWh-Werte gefunden.'
                ))
                results.append(_quality_count(
                    conn,
                    'Messwerte ohne Qualitätskennzeichen',
                    "SELECT COUNT(*) FROM measurements WHERE COALESCE(TRIM(quality), '') = ''",
                    'Messwerte ohne Qualitätskennzeichen gefunden.'
                ))

            if _table_exists(conn, 'overview_totals'):
                results.append(_quality_count(
                    conn,
                    'Übersichtswerte ohne Import-Batch',
                    """SELECT COUNT(*) FROM overview_totals ot
                       LEFT JOIN import_batches b ON b.id = ot.batch_id
                       WHERE b.id IS NULL""",
                    'Übersichtswerte verweisen auf fehlende Import-Batches.'
                ))
                results.append(_quality_count(
                    conn,
                    'Übersichtswerte ohne Meter-Code',
                    """SELECT COUNT(*) FROM overview_totals ot
                       LEFT JOIN meter_codes mc ON mc.id = ot.meter_code_id
                       WHERE mc.id IS NULL""",
                    'Übersichtswerte verweisen auf fehlende Meter-Codes.'
                ))

    has_error = any(item['status'] == 'error' for item in results)
    has_warning = any(item['status'] == 'warning' for item in results)
    summary = 'Fehler gefunden' if has_error else ('Auffälligkeiten gefunden' if has_warning else 'Keine Fehler gefunden')
    return {
        'checked_at': local_now(),
        'summary': summary,
        'status': 'error' if has_error else ('warning' if has_warning else 'ok'),
        'results': results,
    }


def run_database_maintenance(action):
    action_labels = {
        'checkpoint': 'WAL-Checkpoint',
        'analyze': 'Statistiken aktualisieren',
        'optimize': 'SQLite optimieren',
        'vacuum': 'Defragmentierung',
        'full': 'Komplette Wartung',
    }
    if action not in action_labels:
        raise ValueError('Unbekannte Wartungsaktion.')

    backup_filename = None
    if action in ('vacuum', 'full'):
        _, backup_filename = create_local_backup('eeg_manual')

    before = get_database_stats()
    close_db()
    with BACKUP_JOB_LOCK:
        with sqlite3.connect(DB_PATH, timeout=120, isolation_level=None) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            if action in ('checkpoint', 'full'):
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            if action in ('vacuum', 'full'):
                conn.execute("VACUUM")
            if action in ('analyze', 'full'):
                conn.execute("ANALYZE")
            if action in ('optimize', 'full'):
                conn.execute("PRAGMA optimize")
    after = get_database_stats()
    return {
        'action': action,
        'label': action_labels[action],
        'backup_filename': backup_filename,
        'before_size': before['db_size'],
        'after_size': after['db_size'],
        'before_fragmentation': before['fragmentation_mb'],
        'after_fragmentation': after['fragmentation_mb'],
    }


@app.route('/admin/database')
@admin_required
def admin_database():
    """Admin-Seite fuer Datenbank-Wartung und Qualitaetscheck."""
    return render_template('admin_database.html', stats=get_database_stats())


@app.route('/admin/database/check', methods=['POST'])
@admin_required
def admin_database_check():
    """Führt Integritäts- und Plausibilitätsprüfungen aus."""
    try:
        check_result = run_database_quality_check()
        audit_log('database_quality_check', check_result['summary'])
        flash(f'Datenbank-Qualitätscheck abgeschlossen: {check_result["summary"]}.', 'success' if check_result['status'] == 'ok' else 'warning')
    except Exception as e:
        check_result = None
        audit_log('database_quality_check_failed', f'Datenbank-Qualitätscheck fehlgeschlagen: {e}')
        flash(f'Qualitätscheck fehlgeschlagen: {e}', 'danger')
    return render_template('admin_database.html', stats=get_database_stats(), check_result=check_result)


@app.route('/admin/database/maintenance', methods=['POST'])
@admin_required
def admin_database_maintenance():
    """Führt ausgewählte SQLite-Wartungsaktionen aus."""
    action = request.form.get('maintenance_action', '')
    try:
        result = run_database_maintenance(action)
        detail = f'{result["label"]} ausgeführt'
        if result['backup_filename']:
            detail += f' (Sicherungsbackup: {result["backup_filename"]})'
        audit_log('database_maintenance', detail)
        flash(f'{result["label"]} erfolgreich abgeschlossen.', 'success')
    except Exception as e:
        result = None
        audit_log('database_maintenance_failed', f'Datenbank-Wartung fehlgeschlagen: {e}')
        flash(f'Datenbank-Wartung fehlgeschlagen: {e}', 'danger')
    return render_template('admin_database.html', stats=get_database_stats(), maintenance_result=result)


# === Überweisungsliste / Forderungen ===

def _parse_booking_date(value):
    text = (value or '').strip()
    if not text:
        raise ValueError('Bitte ein Buchungsdatum eintragen.')
    try:
        booking_date = date.fromisoformat(text)
    except ValueError as e:
        raise ValueError('Das Buchungsdatum ist ungültig.') from e
    if booking_date > local_now().date():
        raise ValueError('Das Buchungsdatum darf nicht in der Zukunft liegen.')
    if booking_date < date(2000, 1, 1):
        raise ValueError('Das Buchungsdatum ist zu weit in der Vergangenheit.')
    return booking_date


def _paid_at_from_booking_date(booking_date):
    booked_at = datetime.combine(booking_date, datetime.min.time().replace(hour=12), tzinfo=APP_TIMEZONE)
    return booked_at.isoformat(timespec='seconds')


def _row_reference_date(row):
    for key in ('finalized_at', 'created_at', 'period_to'):
        dt = to_local_datetime(row.get(key) if hasattr(row, 'get') else row[key])
        if dt:
            return dt.date()
    return local_now().date()


def _booking_due_date(row):
    return _row_reference_date(row) + timedelta(days=7)


def _active_payment_booking(db, invoice_id, member_id):
    return db.execute("""
        SELECT *
        FROM payment_bookings
        WHERE invoice_id=? AND member_id=? AND reversed_at IS NULL
        ORDER BY booking_date DESC, id DESC
        LIMIT 1
    """, (invoice_id, member_id)).fetchone()


def get_payment_rows(db, member_id=None):
    """Liefert Netto-Zahlungszeilen pro Mitglied und Abrechnung."""
    params = []
    member_filter = ''
    if member_id is not None:
        member_filter = 'WHERE ii.member_id=?'
        params.append(member_id)
    items = db.execute(f"""
        SELECT ii.id, ii.invoice_id, ii.member_id, m.name, m.iban, m.bic, m.account_holder,
               i.period_from, i.period_to, i.status AS invoice_status, i.created_at, i.finalized_at,
               ii.type, ii.kwh, ii.amount_eur, COALESCE(ii.paid, 0) AS paid, ii.paid_at
        FROM invoice_items ii
        JOIN members m ON m.id = ii.member_id
        JOIN invoices i ON i.id = ii.invoice_id
        {member_filter}
        ORDER BY i.period_from DESC, m.name
    """, params).fetchall()

    from collections import defaultdict
    grouped = defaultdict(lambda: {'items': [], 'carryovers': [], 'member': None, 'invoice': None})
    latest_period_by_member = {}

    def ensure_group(invoice_id, member_id_value, member_data, invoice_data):
        key = (invoice_id, member_id_value)
        grouped[key]['member'] = member_data
        grouped[key]['invoice'] = invoice_data
        current_latest = latest_period_by_member.get(member_id_value)
        if current_latest is None or invoice_data['period_to'] > current_latest:
            latest_period_by_member[member_id_value] = invoice_data['period_to']
        return key

    for item in items:
        key = ensure_group(
            item['invoice_id'],
            item['member_id'],
            {
                'id': item['member_id'],
                'name': item['name'],
                'iban': item['iban'],
                'bic': item['bic'],
                'account_holder': item['account_holder'],
            },
            {
                'id': item['invoice_id'],
                'period_from': item['period_from'],
                'period_to': item['period_to'],
                'status': item['invoice_status'],
                'created_at': item['created_at'],
                'finalized_at': item['finalized_at'],
            },
        )
        grouped[key]['items'].append(item)

    carryover_params = []
    carryover_member_filter = ''
    if member_id is not None:
        carryover_member_filter = 'WHERE c.member_id=?'
        carryover_params.append(member_id)
    carryover_rows = db.execute(f"""
        SELECT c.*, m.name, m.iban, m.bic, m.account_holder,
               i.period_from, i.period_to, i.status AS invoice_status, i.created_at, i.finalized_at,
               src.period_from AS source_period_from,
               src.period_to AS source_period_to
        FROM invoice_carryovers c
        JOIN members m ON m.id = c.member_id
        JOIN invoices i ON i.id = c.invoice_id
        JOIN invoices src ON src.id = c.source_invoice_id
        {carryover_member_filter}
        ORDER BY i.period_from DESC, m.name, src.period_from
    """, carryover_params).fetchall()
    for carryover in carryover_rows:
        key = ensure_group(
            carryover['invoice_id'],
            carryover['member_id'],
            {
                'id': carryover['member_id'],
                'name': carryover['name'],
                'iban': carryover['iban'],
                'bic': carryover['bic'],
                'account_holder': carryover['account_holder'],
            },
            {
                'id': carryover['invoice_id'],
                'period_from': carryover['period_from'],
                'period_to': carryover['period_to'],
                'status': carryover['invoice_status'],
                'created_at': carryover['created_at'],
                'finalized_at': carryover['finalized_at'],
            },
        )
        grouped[key]['carryovers'].append(carryover)

    payment_rows = []
    today = local_now().date()
    for key, data in grouped.items():
        energy_net = 0
        for item in data['items']:
            if item['type'] == 'consumption':
                energy_net += item['amount_eur']
            else:
                energy_net -= item['amount_eur']
        carryover_total = round(sum(item['amount_eur'] for item in data['carryovers']), 2)
        net = round(energy_net + carryover_total, 2)
        active_booking = _active_payment_booking(db, key[0], key[1])
        all_paid = bool(data['items']) and all(item['paid'] for item in data['items'])
        paid = bool(active_booking or all_paid or abs(net) < 0.005)
        paid_at = data['items'][0]['paid_at'] if all_paid and data['items'] else None
        booking_date = active_booking['booking_date'] if active_booking else ''
        if not booking_date and paid_at:
            paid_dt = to_local_datetime(paid_at)
            booking_date = paid_dt.date().isoformat() if paid_dt else ''
        carried_forward = db.execute("""
            SELECT c.invoice_id, i.period_from, i.period_to
            FROM invoice_carryovers c
            JOIN invoices i ON i.id = c.invoice_id
            WHERE c.source_invoice_id=? AND c.member_id=?
            ORDER BY i.period_from DESC, c.invoice_id DESC
            LIMIT 1
        """, (key[0], key[1])).fetchone()
        row = {
            'invoice_id': key[0],
            'member_id': key[1],
            'member_name': data['member']['name'],
            'iban': data['member']['iban'],
            'bic': data['member']['bic'],
            'account_holder': data['member']['account_holder'],
            'period_from': data['invoice']['period_from'],
            'period_to': data['invoice']['period_to'],
            'invoice_status': data['invoice']['status'],
            'created_at': data['invoice']['created_at'],
            'finalized_at': data['invoice']['finalized_at'],
            'reference_date': _row_reference_date(data['invoice']),
            'due_on': _booking_due_date(data['invoice']),
            'net_total': round(net, 2),
            'energy_total': round(energy_net, 2),
            'carryover_total': carryover_total,
            'carryovers': data['carryovers'],
            'paid': paid,
            'paid_at': paid_at,
            'booking_date': booking_date,
            'booking_note': active_booking['note'] if active_booking else '',
            'booking_id': active_booking['id'] if active_booking else None,
            'direction': 'member_to_eeg' if net > 0 else 'eeg_to_member' if net < 0 else 'balanced',
            'is_settled_by_carryover': bool(carried_forward and not paid),
            'carried_forward_to_invoice_id': carried_forward['invoice_id'] if carried_forward and not paid else None,
        }
        row['is_overdue'] = (not row['paid'] and not row['is_settled_by_carryover'] and row['net_total'] > 0 and today >= row['due_on'])
        row['is_previous_period_open'] = (
            not row['paid']
            and not row['is_settled_by_carryover']
            and latest_period_by_member.get(row['member_id']) is not None
            and row['period_to'] < latest_period_by_member[row['member_id']]
        )
        payment_rows.append(row)

    payment_rows.sort(key=lambda item: (
        item['paid'],
        not item['is_overdue'],
        item['member_name'].lower(),
        item['period_from'],
    ))
    return payment_rows


def get_payment_row(db, invoice_id, member_id):
    for row in get_payment_rows(db, member_id=member_id):
        if row['invoice_id'] == invoice_id:
            return row
    return None


def get_member_account_summary(db, member_id):
    rows = get_payment_rows(db, member_id=member_id)
    active_open_rows = [row for row in rows if not row['paid'] and not row['is_settled_by_carryover']]
    balance = round(sum(row['net_total'] for row in active_open_rows), 2)
    open_claims = round(sum(row['net_total'] for row in active_open_rows if row['net_total'] > 0), 2)
    open_credits = round(sum(row['net_total'] for row in active_open_rows if row['net_total'] < 0), 2)
    overdue_claims = round(sum(row['net_total'] for row in rows if row['is_overdue']), 2)
    previous_open = [row for row in rows if row['is_previous_period_open']]

    events = []
    for row in rows:
        invoice_date = _row_reference_date(row)
        net = row['net_total']
        events.append({
            'sort_date': invoice_date,
            'date': invoice_date,
            'kind': 'invoice',
            'label': f"Abrechnung {row['period_from']} - {row['period_to']}",
            'invoice_id': row['invoice_id'],
            'amount': net,
            'status': 'gebucht' if row['paid'] else 'vorgetragen' if row['is_settled_by_carryover'] else 'offen',
            'is_overdue': row['is_overdue'],
            'is_previous_period_open': row['is_previous_period_open'],
        })
        if row['is_settled_by_carryover']:
            events.append({
                'sort_date': invoice_date,
                'date': invoice_date,
                'kind': 'carryover',
                'label': f"Vortrag in Abrechnung #{row['carried_forward_to_invoice_id']}",
                'invoice_id': row['carried_forward_to_invoice_id'],
                'amount': -net,
                'status': 'vorgetragen',
                'is_overdue': False,
                'is_previous_period_open': False,
            })
        if row['paid']:
            if row['booking_date']:
                booking_date = date.fromisoformat(row['booking_date'])
            else:
                booking_date = invoice_date
            events.append({
                'sort_date': booking_date,
                'date': booking_date,
                'kind': 'booking',
                'label': 'Zahlung gebucht' if net > 0 else 'Gutschrift ausbezahlt' if net < 0 else 'Ausgeglichen',
                'invoice_id': row['invoice_id'],
                'amount': -net,
                'status': 'gebucht',
                'is_overdue': False,
                'is_previous_period_open': False,
            })

    running = 0
    for event in sorted(events, key=lambda item: (item['sort_date'], 0 if item['kind'] == 'invoice' else 1, item['invoice_id'])):
        running = round(running + event['amount'], 2)
        event['balance_after'] = running

    return {
        'balance': balance,
        'open_claims': open_claims,
        'open_credits': open_credits,
        'overdue_claims': overdue_claims,
        'previous_open': previous_open,
        'rows': rows,
        'history': list(reversed(events)),
    }


@app.route('/payments')
@admin_required
def payments():
    """Überweisungsliste: offene und bezahlte Forderungen."""
    db = get_db()
    payment_list = get_payment_rows(db)
    return render_template('payments.html', payments=payment_list, today=local_now().date().isoformat())


@app.route('/payments/mark_paid', methods=['POST'])
@admin_required
def payment_mark_paid():
    """Bucht eine Forderung oder Gutschrift mit Bank-Buchungsdatum."""
    db = get_db()
    invoice_id = request.form.get('invoice_id', type=int)
    member_id = request.form.get('member_id', type=int)
    try:
        booking_date = _parse_booking_date(request.form.get('booking_date'))
        note = (request.form.get('booking_note') or '').strip()[:500]
        row = get_payment_row(db, invoice_id, member_id)
        if not row:
            raise ValueError('Die Buchung wurde nicht gefunden.')
        if row['paid']:
            raise ValueError('Diese Buchung ist bereits als gebucht markiert.')
        if row['is_settled_by_carryover']:
            raise ValueError(f'Diese offene Buchung wurde bereits in Abrechnung #{row["carried_forward_to_invoice_id"]} vorgetragen.')
        if abs(row['net_total']) >= 0.005:
            db.execute("""
                INSERT INTO payment_bookings (
                    invoice_id, member_id, amount_eur, direction, booking_date,
                    recorded_by_user_id, recorded_by_username, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                invoice_id,
                member_id,
                row['net_total'],
                row['direction'],
                booking_date.isoformat(),
                current_user.id if current_user.is_authenticated else None,
                current_user.username if current_user.is_authenticated else None,
                note,
            ))
        db.execute("""UPDATE invoice_items SET paid=1, paid_at=?
                      WHERE invoice_id=? AND member_id=?""",
                   (_paid_at_from_booking_date(booking_date), invoice_id, member_id))
        db.commit()
        action_label = 'Zahlung' if row['net_total'] > 0 else 'Gutschrift' if row['net_total'] < 0 else 'Ausgleich'
        audit_log('payment_paid', f'{action_label} gebucht: {row["member_name"]}, Rechnung {invoice_id}, Betrag {row["net_total"]:.2f} EUR, Buchungsdatum {booking_date.isoformat()}')
        flash(f'{action_label} für {row["member_name"]} mit Buchungsdatum {booking_date.strftime("%d.%m.%Y")} gebucht.', 'success')
    except Exception as e:
        db.rollback()
        audit_log('payment_paid_failed', f'Zahlungsbuchung fehlgeschlagen: Mitglied {member_id}, Rechnung {invoice_id} ({e})')
        flash(f'Buchung konnte nicht gespeichert werden: {e}', 'danger')
    return redirect(url_for('payments'))


@app.route('/payments/mark_unpaid', methods=['POST'])
@admin_required
def payment_mark_unpaid():
    """Markiert eine Forderung als offen (Storno)."""
    db = get_db()
    invoice_id = request.form.get('invoice_id', type=int)
    member_id = request.form.get('member_id', type=int)
    try:
        row = get_payment_row(db, invoice_id, member_id)
        if not row:
            raise ValueError('Die Buchung wurde nicht gefunden.')
        if not row['paid']:
            raise ValueError('Diese Buchung ist bereits offen.')
        db.execute("""
            UPDATE payment_bookings
            SET reversed_at=datetime('now'),
                reversed_by_user_id=?,
                reversed_by_username=?,
                reverse_note=?
            WHERE invoice_id=? AND member_id=? AND reversed_at IS NULL
        """, (
            current_user.id if current_user.is_authenticated else None,
            current_user.username if current_user.is_authenticated else None,
            'Zahlung durch Admin auf offen zurückgesetzt',
            invoice_id,
            member_id,
        ))
        db.execute("""UPDATE invoice_items SET paid=0, paid_at=NULL
                      WHERE invoice_id=? AND member_id=?""", (invoice_id, member_id))
        db.commit()
        audit_log('payment_unpaid', f'Buchung storniert: {row["member_name"]}, Rechnung {invoice_id}')
        flash('Buchung wurde storniert und wieder als offen markiert.', 'info')
    except Exception as e:
        db.rollback()
        audit_log('payment_unpaid_failed', f'Buchungsstorno fehlgeschlagen: Mitglied {member_id}, Rechnung {invoice_id} ({e})')
        flash(f'Buchung konnte nicht zurückgesetzt werden: {e}', 'danger')
    return redirect(url_for('payments'))


# ═══════════════════════════════════════════════════════
# BENUTZERVERWALTUNG (Admin)
# ═══════════════════════════════════════════════════════

CONTRACTS_FOLDER = os.path.join(BASE_DIR, '..', 'contracts')
os.makedirs(CONTRACTS_FOLDER, exist_ok=True)


@app.route('/admin/users')
@admin_required
def admin_users():
    """Benutzerverwaltung – alle User anzeigen."""
    db = get_db()
    users = db.execute("""
        SELECT u.*, m.name as member_name, m.email as member_email
        FROM users u LEFT JOIN members m ON u.member_id = m.id
        WHERE NOT EXISTS (
            SELECT 1
            FROM users other
            WHERE other.id != u.id
              AND (
                  (u.member_id IS NOT NULL AND other.member_id = u.member_id)
                  OR (
                      u.email IS NOT NULL AND u.email != ''
                      AND other.email IS NOT NULL AND other.email != ''
                      AND LOWER(other.email) = LOWER(u.email)
                  )
              )
              AND (
                  (other.invite_token IS NULL AND u.invite_token IS NOT NULL)
                  OR (
                      (other.invite_token IS NULL) = (u.invite_token IS NULL)
                      AND other.id < u.id
                  )
              )
        )
        ORDER BY u.is_admin DESC, u.username
    """).fetchall()
    members = db.execute("SELECT id, name, email FROM members WHERE active=1 ORDER BY name").fetchall()
    return render_template('admin_users.html', users=users, members=members)


@app.route('/admin/users/create', methods=['POST'])
@admin_required
def admin_user_create():
    """Neuen Benutzer für ein Mitglied anlegen."""
    db = get_db()
    member_id = request.form.get('member_id', type=int)
    role = request.form.get('role', 'member')
    if role not in ('admin', 'member'):
        role = 'member'

    member = db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    if not member:
        flash('Mitglied nicht gefunden.', 'danger')
        return redirect(url_for('admin_users'))

    # Username: email oder vorname+nachname lowercase
    if member['email']:
        username = member['email'].lower().strip()
    else:
        username = member['name'].lower().replace(' ', '').replace('&', '')
        # Umlaute normalisieren
        for old, new in [('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')]:
            username = username.replace(old, new)

    existing = db.execute("""
        SELECT id, username FROM users
        WHERE LOWER(username)=?
           OR member_id=?
           OR (? != '' AND email IS NOT NULL AND email != '' AND LOWER(email)=?)
        ORDER BY CASE WHEN invite_token IS NULL THEN 0 ELSE 1 END, id
        LIMIT 1
    """, (username.lower(), member_id, (member['email'] or '').strip(), (member['email'] or '').strip().lower())).fetchone()
    if existing:
        flash(f'Für dieses Mitglied existiert bereits der Benutzer "{existing["username"]}".', 'warning')
        return redirect(url_for('admin_users'))

    # Einladungs-Token generieren
    invite_token = secrets.token_urlsafe(32)
    invite_expires = (datetime.now().replace(hour=23, minute=59) +
                      __import__('datetime').timedelta(days=14)).isoformat()
    # Temporäres Passwort (wird beim ersten Login über Invite-Link gesetzt)
    temp_hash = generate_password_hash(secrets.token_hex(16))

    db.execute("""INSERT INTO users (username, password_hash, email, is_admin, role, member_id,
                  invite_token, invite_expires) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
               (username, temp_hash, member['email'], 1 if role == 'admin' else 0,
                role, member_id, invite_token, invite_expires))
    db.commit()

    invite_url = public_url_for('invite_accept', token=invite_token)
    audit_log('user_create', f'Benutzer angelegt: {username} (Rolle: {role}, Mitglied-ID: {member_id})')
    if member['email']:
        invite_user = {
            'username': username,
            'email': member['email'],
            'role': role,
            'member_name': member['name'],
        }
        try:
            send_invitation_email(db, invite_user, invite_url, invite_expires)
            flash(f'Benutzer "{username}" angelegt und Einladung an {member["email"]} gesendet.', 'success')
        except Exception as e:
            app.logger.exception('Invitation mail failed for user %s', username)
            flash(f'Benutzer "{username}" angelegt, aber die Einladung konnte nicht per E-Mail gesendet werden: {e}', 'warning')
            flash(f'Einladungslink: {invite_url}', 'info')
    else:
        flash(f'Benutzer "{username}" angelegt. Keine E-Mail-Adresse hinterlegt; Einladungslink: {invite_url}', 'warning')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:id>/invite', methods=['POST'])
@admin_required
def admin_user_reinvite(id):
    """Neuen Einladungslink generieren."""
    db = get_db()
    invite_action = request.form.get('invite_action', 'send')
    if invite_action not in ('show', 'send'):
        invite_action = 'send'
    invite_token = secrets.token_urlsafe(32)
    invite_expires = (datetime.now().replace(hour=23, minute=59) +
                      __import__('datetime').timedelta(days=14)).isoformat()
    db.execute("UPDATE users SET invite_token=?, invite_expires=? WHERE id=?",
               (invite_token, invite_expires, id))
    db.commit()
    user = db.execute("""
        SELECT u.*, m.name as member_name
        FROM users u LEFT JOIN members m ON u.member_id = m.id
        WHERE u.id=?
    """, (id,)).fetchone()
    invite_url = public_url_for('invite_accept', token=invite_token)
    audit_log('user_reinvite', f'Neuer Einladungslink für: {user["username"]}' if user else f'Reinvite User-ID {id}')
    if invite_action == 'show':
        flash(f'Neuer Einladungslink generiert: {invite_url}', 'info')
    elif not user:
        flash(f'Neuer Einladungslink generiert: {invite_url}', 'success')
    elif user['email']:
        try:
            send_invitation_email(db, user, invite_url, invite_expires)
            flash(f'Neuer Einladungslink für "{user["username"]}" generiert und an {user["email"]} gesendet.', 'success')
        except Exception as e:
            app.logger.exception('Invitation mail failed for user %s', user['username'])
            flash(f'Neuer Einladungslink generiert, aber die Einladung konnte nicht per E-Mail gesendet werden: {e}', 'warning')
            flash(f'Einladungslink: {invite_url}', 'info')
    else:
        flash(f'Neuer Einladungslink generiert. Keine E-Mail-Adresse hinterlegt; Link: {invite_url}', 'warning')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:id>/toggle-role', methods=['POST'])
@admin_required
def admin_user_toggle_role(id):
    """Rolle umschalten admin <-> member."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
    if not user:
        flash('Benutzer nicht gefunden.', 'danger')
        return redirect(url_for('admin_users'))
    new_role = 'member' if user['role'] == 'admin' else 'admin'
    new_admin = 1 if new_role == 'admin' else 0
    db.execute("UPDATE users SET role=?, is_admin=? WHERE id=?", (new_role, new_admin, id))
    db.commit()
    audit_log('user_role_change', f'Rolle geändert: {user["username"]} → {new_role}')
    flash(f'Rolle auf "{new_role}" geändert.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:id>/delete', methods=['POST'])
@admin_required
def admin_user_delete(id):
    """Benutzer löschen."""
    if id == current_user.id:
        flash('Sie können sich nicht selbst löschen.', 'danger')
        return redirect(url_for('admin_users'))
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id=?", (id,)).fetchone()
    db.execute("DELETE FROM users WHERE id=?", (id,))
    db.commit()
    audit_log('user_delete', f'Benutzer gelöscht: {user["username"]}' if user else f'User-ID {id} gelöscht')
    flash('Benutzer gelöscht.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/contracts/upload', methods=['POST'])
@admin_required
def admin_contract_upload():
    """Vertrag hochladen für ein Mitglied."""
    db = get_db()
    member_id = request.form.get('member_id', type=int)
    contract_type = request.form.get('type', '')
    if contract_type not in ('bezieher', 'einspeiser'):
        flash('Ungültiger Vertragstyp.', 'danger')
        return redirect(url_for('admin_users'))
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('admin_users'))
    filename = secure_filename(file.filename)
    if not filename.lower().endswith('.pdf'):
        flash('Nur PDF-Dateien sind als Vertrag erlaubt.', 'danger')
        return redirect(url_for('admin_users'))
    file_data = file.read()
    if len(file_data) > 10 * 1024 * 1024:
        flash('Datei zu groß (max. 10 MB).', 'danger')
        return redirect(url_for('admin_users'))
    if not file_data.startswith(b'%PDF-'):
        flash('Die hochgeladene Datei ist keine gültige PDF-Datei.', 'danger')
        return redirect(url_for('admin_users'))
    db.execute("""INSERT INTO contracts (member_id, type, filename, file_data, uploaded_by)
                  VALUES (?, ?, ?, ?, ?)""",
               (member_id, contract_type, filename, file_data, current_user.username))
    db.commit()
    member = db.execute("SELECT name FROM members WHERE id=?", (member_id,)).fetchone()
    audit_log('contract_upload', f'Vertrag hochgeladen: {filename} ({contract_type}) für {member["name"]}')
    flash(f'Vertrag "{filename}" hochgeladen.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/contracts/<int:id>/download')
@login_required
def contract_download(id):
    """Vertrag herunterladen (Admins alle, Members nur eigene)."""
    db = get_db()
    contract = db.execute("SELECT * FROM contracts WHERE id=?", (id,)).fetchone()
    if not contract:
        flash('Vertrag nicht gefunden.', 'danger')
        return redirect(url_for('admin_users'))
    if not current_user.is_admin and current_user.member_id != contract['member_id']:
        flash('Zugriff verweigert.', 'danger')
        return redirect(url_for('portal_dashboard'))
    audit_log('contract_download', f'Vertrag heruntergeladen: {contract["filename"]} (ID {id})')
    import io
    return send_file(
        io.BytesIO(contract['file_data']),
        as_attachment=True,
        download_name=contract['filename']
    )


@app.route('/contracts/<int:id>/delete', methods=['POST'])
@admin_required
def contract_delete(id):
    """Vertrag löschen."""
    db = get_db()
    contract = db.execute("SELECT filename, member_id FROM contracts WHERE id=?", (id,)).fetchone()
    db.execute("DELETE FROM contracts WHERE id=?", (id,))
    db.commit()
    audit_log('contract_delete', f'Vertrag gelöscht: {contract["filename"]}' if contract else f'Vertrag ID {id} gelöscht')
    flash('Vertrag gelöscht.', 'success')
    return redirect(url_for('admin_users'))


# ═══════════════════════════════════════════════════════
# EINLADUNG / PASSWORT SETZEN
# ═══════════════════════════════════════════════════════

@app.route('/invite/<token>', methods=['GET', 'POST'])
def invite_accept(token):
    """Einladungslink – Passwort setzen."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE invite_token=?", (token,)).fetchone()
    if not user:
        flash('Ungültiger Einladungslink.', 'danger')
        return redirect(url_for('login'))
    if user['invite_expires'] and user['invite_expires'] < datetime.now().isoformat():
        flash('Einladungslink abgelaufen. Bitte Admin kontaktieren.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if len(password) < 6:
            flash('Passwort muss mindestens 6 Zeichen haben.', 'danger')
            return render_template('invite.html', token=token, username=user['username'])
        if password != confirm:
            flash('Passwörter stimmen nicht überein.', 'danger')
            return render_template('invite.html', token=token, username=user['username'])
        db.execute("UPDATE users SET password_hash=?, invite_token=NULL, invite_expires=NULL WHERE id=?",
                   (generate_password_hash(password), user['id']))
        db.commit()
        audit_log('invite_accept', f'Einladung angenommen, Passwort gesetzt', user_id=user['id'], username=user['username'])
        flash('Passwort erfolgreich gesetzt. Sie können sich jetzt einloggen.', 'success')
        return redirect(url_for('login'))

    return render_template('invite.html', token=token, username=user['username'])


@app.route('/api/contracts')
@admin_required
def api_contracts():
    """JSON-API: Alle Verträge auflisten."""
    db = get_db()
    rows = db.execute("""
        SELECT c.id, c.member_id, c.type, c.filename, c.uploaded_at, c.uploaded_by, m.name as member_name
        FROM contracts c JOIN members m ON m.id = c.member_id
        ORDER BY m.name, c.type
    """).fetchall()
    data = []
    for row in rows:
        item = dict(row)
        item['uploaded_at'] = format_local_date(item.get('uploaded_at'))
        data.append(item)
    return jsonify(data)


@app.route('/admin/audit')
@admin_required
def admin_audit():
    """Audit-Log anzeigen."""
    db = get_db()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    # Filter
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    where_clauses = []
    params = []
    if action_filter:
        where_clauses.append("a.action = ?")
        params.append(action_filter)
    if user_filter:
        where_clauses.append("a.username LIKE ?")
        params.append(f'%{user_filter}%')
    if date_from:
        date_from_utc, _ = local_day_bounds_as_utc_strings(date_from)
        where_clauses.append("a.timestamp >= ?")
        params.append(date_from_utc)
    if date_to:
        _, date_to_utc = local_day_bounds_as_utc_strings(date_to)
        where_clauses.append("a.timestamp <= ?")
        params.append(date_to_utc)

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total = db.execute(f"SELECT COUNT(*) FROM audit_log a{where_sql}", params).fetchone()[0]
    logs = db.execute(f"""
        SELECT a.* FROM audit_log a{where_sql}
        ORDER BY a.timestamp DESC LIMIT ? OFFSET ?
    """, params + [per_page, offset]).fetchall()
    logs = [dict(row) for row in logs]
    for log in logs:
        log['timestamp_display'] = format_local_datetime(log.get('timestamp'))

    # Alle vorhandenen Aktionstypen für Filter-Dropdown
    actions = db.execute("SELECT DISTINCT action FROM audit_log ORDER BY action").fetchall()
    action_list = [r['action'] for r in actions]

    # Statistiken
    today_from_utc, today_to_utc = local_day_bounds_as_utc_strings()
    stats = {
        'total_entries': db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
        'today_entries': db.execute(
            "SELECT COUNT(*) FROM audit_log WHERE timestamp >= ? AND timestamp <= ?",
            (today_from_utc, today_to_utc)
        ).fetchone()[0],
        'active_users': db.execute(
            "SELECT COUNT(DISTINCT username) FROM audit_log WHERE timestamp >= ? AND timestamp <= ?",
            (today_from_utc, today_to_utc)
        ).fetchone()[0],
    }

    total_pages = (total + per_page - 1) // per_page

    return render_template('admin_audit.html',
                           logs=logs, page=page, total_pages=total_pages, total=total,
                           action_filter=action_filter, user_filter=user_filter,
                           date_from=date_from, date_to=date_to,
                           action_list=action_list, stats=stats)


# ═══════════════════════════════════════════════════════
# MITGLIEDER-PORTAL
# ═══════════════════════════════════════════════════════

@app.route('/portal')
@login_required
def portal_dashboard():
    """Teilnehmer-Dashboard."""
    if current_user.is_admin and not current_user.member_id:
        return redirect(url_for('dashboard'))
    db = get_db()
    member_id = current_user.member_id
    if not member_id:
        flash('Kein Mitglied zugeordnet.', 'warning')
        return render_template('portal_dashboard.html', member=None, invoices=[], stats=None, account=None)

    member = db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    account = get_member_account_summary(db, member_id)
    # Abrechnungen des Mitglieds
    invoices = db.execute("""
        SELECT DISTINCT i.* FROM invoices i
        WHERE i.id IN (
            SELECT invoice_id FROM invoice_items WHERE member_id=?
            UNION
            SELECT invoice_id FROM invoice_carryovers WHERE member_id=?
        )
        ORDER BY i.period_from DESC
    """, (member_id, member_id)).fetchall()

    # Letzte Abrechnung: Stats berechnen
    stats = None
    if invoices:
        latest = invoices[0]
        stats = get_member_stats(db, member, latest['period_from'], latest['period_to'])
        # Net total
        items = db.execute("SELECT * FROM invoice_items WHERE invoice_id=? AND member_id=?",
                           (latest['id'], member_id)).fetchall()
        carryovers = get_invoice_carryovers(db, latest['id'], member_id)
        net = sum(i['amount_eur'] if i['type'] == 'consumption' else -i['amount_eur'] for i in items)
        net += sum(c['amount_eur'] for c in carryovers)
        stats['net_total'] = round(net, 2)
        stats['invoice_id'] = latest['id']

    return render_template('portal_dashboard.html', member=member, invoices=invoices, stats=stats, account=account)


@app.route('/portal/data', methods=['GET', 'POST'])
@login_required
def portal_data():
    """Teilnehmer kann eigene Stammdaten bearbeiten."""
    if not current_user.member_id:
        flash('Kein Mitglied zugeordnet.', 'warning')
        return redirect(url_for('portal_dashboard'))
    db = get_db()
    member = db.execute("SELECT * FROM members WHERE id=?", (current_user.member_id,)).fetchone()

    if request.method == 'POST':
        newsletter_optout = 0 if form_switch_enabled('newsletter_enabled') else 1
        db.execute("""UPDATE members SET
            name=?, email=?, phone=?,
            address_street=?, address_zip=?, address_city=?,
            iban=?, bic=?, account_holder=?, newsletter_optout=?,
            updated_at=datetime('now')
            WHERE id=?""", (
            request.form.get('name', member['name']),
            request.form.get('email', member['email']),
            request.form.get('phone', member['phone']),
            request.form.get('address_street', member['address_street']),
            request.form.get('address_zip', member['address_zip']),
            request.form.get('address_city', member['address_city']),
            request.form.get('iban', member['iban']),
            request.form.get('bic', member['bic']),
            request.form.get('account_holder', member['account_holder']),
            newsletter_optout,
            current_user.member_id))
        db.commit()
        audit_log('portal_data_update', f'Eigene Stammdaten aktualisiert')
        flash('Daten aktualisiert.', 'success')
        return redirect(url_for('portal_data'))

    return render_template('portal_data.html', member=member)


@app.route('/portal/invoices')
@login_required
def portal_invoices():
    """Teilnehmer: Eigene Abrechnungen."""
    if not current_user.member_id:
        flash('Kein Mitglied zugeordnet.', 'warning')
        return redirect(url_for('portal_dashboard'))
    db = get_db()
    account = get_member_account_summary(db, current_user.member_id)
    rows = db.execute("""
        SELECT i.id, i.period_from, i.period_to, i.status, i.created_at,
               COALESCE(SUM(CASE WHEN ii.type='consumption' THEN ii.amount_eur ELSE 0 END), 0) as total_cons,
               COALESCE(SUM(CASE WHEN ii.type='generation' THEN ii.amount_eur ELSE 0 END), 0) as total_gen,
               COALESCE(SUM(ii.kwh), 0) as total_kwh
        FROM invoices i
        LEFT JOIN invoice_items ii ON ii.invoice_id = i.id AND ii.member_id = ?
        WHERE i.id IN (
            SELECT invoice_id FROM invoice_items WHERE member_id=?
            UNION
            SELECT invoice_id FROM invoice_carryovers WHERE member_id=?
        )
        GROUP BY i.id
        ORDER BY i.period_from DESC
    """, (current_user.member_id, current_user.member_id, current_user.member_id)).fetchall()
    payment_by_invoice = {row['invoice_id']: row for row in account['rows']}
    return render_template(
        'portal_invoices.html',
        invoices=rows,
        member_id=current_user.member_id,
        payment_by_invoice=payment_by_invoice,
    )


@app.route('/portal/contracts')
@login_required
def portal_contracts():
    """Teilnehmer: Eigene Verträge."""
    if not current_user.member_id:
        flash('Kein Mitglied zugeordnet.', 'warning')
        return redirect(url_for('portal_dashboard'))
    db = get_db()
    contracts = db.execute("SELECT * FROM contracts WHERE member_id=? ORDER BY uploaded_at DESC",
                           (current_user.member_id,)).fetchall()
    return render_template('portal_contracts.html', contracts=contracts)


@app.route('/portal/newsletter', methods=['POST'])
@login_required
def portal_newsletter_toggle():
    """Teilnehmer: Newsletter an/abbestellen."""
    db = get_db()
    if not current_user.member_id:
        flash('Kein Mitglied zugeordnet.', 'warning')
        return redirect(url_for('portal_data'))
    if 'newsletter_enabled' in request.form:
        optout = 0 if form_switch_enabled('newsletter_enabled') else 1
    else:
        optout = 1 if request.form.get('optout') == '1' else 0
    db.execute("UPDATE members SET newsletter_optout=? WHERE id=?", (optout, current_user.member_id))
    db.commit()
    if optout:
        audit_log('newsletter_optout', f'Newsletter abbestellt (Mitglied {current_user.member_id})')
        flash('Newsletter abbestellt.', 'info')
    else:
        audit_log('newsletter_optin', f'Newsletter wieder abonniert (Mitglied {current_user.member_id})')
        flash('Newsletter abonniert.', 'success')
    return redirect(url_for('portal_data'))


@app.route('/newsletter/unsubscribe/<token>')
def newsletter_unsubscribe(token):
    """Öffentliche Abmeldung per Link aus E-Mail."""
    if not token or len(token) < 16:
        return render_template('newsletter_unsubscribe.html', status='invalid', member=None), 400
    db = get_db()
    member = db.execute("SELECT id, name FROM members WHERE unsubscribe_token=?", (token,)).fetchone()
    if not member:
        return render_template('newsletter_unsubscribe.html', status='invalid', member=None), 404
    db.execute("UPDATE members SET newsletter_optout=1 WHERE id=?", (member['id'],))
    db.commit()
    audit_log('newsletter_optout', f'Newsletter per Link abbestellt: {member["name"]} (ID {member["id"]})',
              user_id=None, username='system')
    return render_template('newsletter_unsubscribe.html', status='success', member=member)


# === Newsletter Admin ===

@app.route('/newsletter')
@admin_required
def newsletter_list():
    """Alle Newsletter anzeigen."""
    db = get_db()
    newsletters = db.execute("SELECT * FROM newsletters ORDER BY created_at DESC").fetchall()
    return render_template('newsletter_list.html', newsletters=newsletters)


@app.route('/newsletter/new', methods=['GET', 'POST'])
@admin_required
def newsletter_new():
    """Neuen Newsletter erstellen."""
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        body_html = sanitize_newsletter_html(request.form.get('body_html', '').strip())
        if not subject or not body_html:
            flash('Betreff und Inhalt sind erforderlich.', 'danger')
            return render_template('newsletter_edit.html', newsletter=None,
                                   subject=subject, body_html=body_html)
        db = get_db()
        db.execute("INSERT INTO newsletters (subject, body_html, created_by) VALUES (?,?,?)",
                   (subject, body_html, current_user.username))
        db.commit()
        audit_log('newsletter_create', f'Newsletter erstellt: {subject}')
        flash('Newsletter gespeichert.', 'success')
        return redirect(url_for('newsletter_list'))
    return render_template('newsletter_edit.html', newsletter=None, subject='', body_html='')


@app.route('/newsletter/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def newsletter_edit(id):
    """Newsletter bearbeiten."""
    db = get_db()
    nl = db.execute("SELECT * FROM newsletters WHERE id=?", (id,)).fetchone()
    if not nl:
        flash('Newsletter nicht gefunden.', 'danger')
        return redirect(url_for('newsletter_list'))
    if nl['sent_at']:
        flash('Bereits versendeter Newsletter kann nicht bearbeitet werden.', 'warning')
        return redirect(url_for('newsletter_list'))
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        body_html = sanitize_newsletter_html(request.form.get('body_html', '').strip())
        if not subject or not body_html:
            flash('Betreff und Inhalt sind erforderlich.', 'danger')
            return render_template('newsletter_edit.html', newsletter=nl,
                                   subject=subject, body_html=body_html)
        db.execute("UPDATE newsletters SET subject=?, body_html=? WHERE id=?", (subject, body_html, id))
        db.commit()
        audit_log('newsletter_edit', f'Newsletter bearbeitet: {subject} (ID {id})')
        flash('Newsletter aktualisiert.', 'success')
        return redirect(url_for('newsletter_list'))
    return render_template('newsletter_edit.html', newsletter=nl,
                           subject=nl['subject'], body_html=sanitize_newsletter_html(nl['body_html']))


@app.route('/newsletter/<int:id>/preview')
@admin_required
def newsletter_preview(id):
    """Vorschau des Newsletters im E-Mail-Template."""
    db = get_db()
    nl = db.execute("SELECT * FROM newsletters WHERE id=?", (id,)).fetchone()
    if not nl:
        flash('Newsletter nicht gefunden.', 'danger')
        return redirect(url_for('newsletter_list'))
    logo_url = public_url_for('static', filename='logo.png')
    html = render_template('newsletter_email.html',
        subject=nl['subject'],
        preview_text=nl['subject'],
        logo_url=logo_url,
        edition_label=nl['subject'].split('–')[0].strip() if '\u2013' in nl['subject'] else nl['subject'],
        headline=nl['subject'],
        subtitle='',
        body_html=sanitize_newsletter_html(nl['body_html']),
        unsubscribe_url='#',
    )
    return html


@app.route('/newsletter/<int:id>/test', methods=['POST'])
@admin_required
def newsletter_test(id):
    """Test-E-Mail an eine einzelne Adresse senden."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    test_email = request.form.get('test_email', '').strip()
    if not _is_valid_email(test_email):
        flash('Bitte eine gültige Test-E-Mail-Adresse eingeben.', 'danger')
        return redirect(url_for('newsletter_list'))

    db = get_db()
    nl = db.execute("SELECT * FROM newsletters WHERE id=?", (id,)).fetchone()
    if not nl:
        flash('Newsletter nicht gefunden.', 'danger')
        return redirect(url_for('newsletter_list'))

    try:
        mail_cfg = _get_valid_mail_config(db)
    except RuntimeError as e:
        flash(f'E-Mail-Konfiguration ungültig: {e}', 'danger')
        return redirect(url_for('newsletter_list'))

    base_url = public_base_url()
    logo_url = public_url_for('static', filename='logo.png')

    full_html = render_template('newsletter_email.html',
        subject=nl['subject'],
        preview_text=nl['subject'],
        logo_url=logo_url,
        edition_label=nl['subject'].split('–')[0].strip() if '\u2013' in nl['subject'] else nl['subject'],
        headline=nl['subject'],
        subtitle='',
        body_html=sanitize_newsletter_html(nl['body_html']),
        unsubscribe_url=f"{base_url}/newsletter/unsubscribe/test-preview",
    )

    try:
        with smtplib.SMTP(mail_cfg['smtp_host'], mail_cfg['smtp_port']) as server:
            if mail_cfg['smtp_tls']:
                server.starttls()
            server.login(mail_cfg['smtp_user'], mail_cfg['smtp_pass'])

            msg = MIMEMultipart('alternative')
            msg['From'] = mail_cfg['from_header']
            msg['Reply-To'] = mail_cfg['reply_to_header']
            msg['To'] = test_email
            msg['Subject'] = f"[TEST] {nl['subject']}"
            msg.attach(MIMEText(full_html, 'html', 'utf-8'))

            _log_mail_send(mail_cfg, test_email, msg['Subject'])
            server.sendmail(mail_cfg['from_address'], [test_email], msg.as_string())
        flash(f'Test-E-Mail erfolgreich an {test_email} gesendet.', 'success')
    except Exception as e:
        flash(f'Fehler beim Senden der Test-E-Mail: {e}', 'danger')

    audit_log('newsletter_test', f'Test-E-Mail für "{nl["subject"]}" an {test_email}')
    return redirect(url_for('newsletter_list'))


@app.route('/newsletter/<int:id>/send', methods=['POST'])
@admin_required
def newsletter_send(id):
    """Newsletter an alle aktiven Mitglieder mit E-Mail senden (die nicht abbestellt haben)."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import secrets

    db = get_db()
    nl = db.execute("SELECT * FROM newsletters WHERE id=?", (id,)).fetchone()
    if not nl:
        flash('Newsletter nicht gefunden.', 'danger')
        return redirect(url_for('newsletter_list'))

    try:
        mail_cfg = _get_valid_mail_config(db)
    except RuntimeError as e:
        flash(f'E-Mail-Konfiguration ungültig: {e}', 'danger')
        return redirect(url_for('newsletter_list'))

    # Empfänger: aktive Mitglieder mit E-Mail, die nicht abbestellt haben
    members = db.execute("""
        SELECT id, name, email, unsubscribe_token FROM members
        WHERE active=1 AND email IS NOT NULL AND email != ''
          AND (newsletter_optout IS NULL OR newsletter_optout=0)
    """).fetchall()

    if not members:
        flash('Keine Empfänger gefunden (alle abbestellt oder keine E-Mail hinterlegt).', 'warning')
        return redirect(url_for('newsletter_list'))

    sent = 0
    failed = 0
    # Logo-URL für E-Mail
    logo_url = public_url_for('static', filename='logo.png')

    try:
        server = smtplib.SMTP(mail_cfg['smtp_host'], mail_cfg['smtp_port'])
        if mail_cfg['smtp_tls']:
            server.starttls()
        server.login(mail_cfg['smtp_user'], mail_cfg['smtp_pass'])

        for member in members:
            # Unsubscribe-Token generieren falls nicht vorhanden
            unsub_token = member['unsubscribe_token']
            if not unsub_token:
                unsub_token = secrets.token_urlsafe(32)
                db.execute("UPDATE members SET unsubscribe_token=? WHERE id=?", (unsub_token, member['id']))
                db.commit()

            unsub_url = public_url_for('newsletter_unsubscribe', token=unsub_token)

            # HTML aus Template rendern
            full_html = render_template('newsletter_email.html',
                subject=nl['subject'],
                preview_text=nl['subject'],
                logo_url=logo_url,
                edition_label=nl['subject'].split('–')[0].strip() if '–' in nl['subject'] else nl['subject'],
                headline=nl['subject'],
                subtitle='',
                body_html=sanitize_newsletter_html(nl['body_html']),
                unsubscribe_url=unsub_url,
            )

            msg = MIMEMultipart('alternative')
            msg['From'] = mail_cfg['from_header']
            msg['Reply-To'] = mail_cfg['reply_to_header']
            msg['To'] = member['email']
            msg['Subject'] = nl['subject']
            msg['List-Unsubscribe'] = f'<{unsub_url}>'
            msg.attach(MIMEText(full_html, 'html', 'utf-8'))

            try:
                _log_mail_send(mail_cfg, member['email'], nl['subject'])
                server.sendmail(mail_cfg['from_address'], [member['email']], msg.as_string())
                db.execute("""INSERT INTO newsletter_log (newsletter_id, member_id, email, status)
                              VALUES (?,?,?,?)""", (id, member['id'], member['email'], 'sent'))
                sent += 1
            except Exception as e:
                db.execute("""INSERT INTO newsletter_log (newsletter_id, member_id, email, status, error_message)
                              VALUES (?,?,?,?,?)""", (id, member['id'], member['email'], 'failed', str(e)))
                failed += 1

        server.quit()
    except Exception as e:
        flash(f'SMTP-Verbindungsfehler: {e}', 'danger')
        return redirect(url_for('newsletter_list'))

    db.execute("UPDATE newsletters SET sent_at=datetime('now'), recipients_count=? WHERE id=?", (sent, id))
    db.commit()
    audit_log('newsletter_send', f'Newsletter "{nl["subject"]}" versendet: {sent} gesendet, {failed} fehlgeschlagen')
    flash(f'Newsletter versendet: {sent} erfolgreich, {failed} fehlgeschlagen.', 'success')
    return redirect(url_for('newsletter_list'))


@app.route('/newsletter/<int:id>/delete', methods=['POST'])
@admin_required
def newsletter_delete(id):
    """Newsletter löschen."""
    db = get_db()
    nl = db.execute("SELECT subject FROM newsletters WHERE id=?", (id,)).fetchone()
    if nl:
        db.execute("DELETE FROM newsletter_log WHERE newsletter_id=?", (id,))
        db.execute("DELETE FROM newsletters WHERE id=?", (id,))
        db.commit()
        audit_log('newsletter_delete', f'Newsletter gelöscht: {nl["subject"]} (ID {id})')
        flash('Newsletter gelöscht.', 'success')
    return redirect(url_for('newsletter_list'))


# === Entry Point ===

if __name__ == '__main__':
    init_db()
    _startup_mail_config_check()
    start_backup_scheduler()
    app.run(
        host=os.environ.get('EEG_HOST', '127.0.0.1'),
        port=int(os.environ.get('EEG_PORT', '5000')),
        debug=os.environ.get('FLASK_DEBUG') == '1'
    )
