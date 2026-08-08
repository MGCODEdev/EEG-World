"""Sichere Mitglieder-API für native Mobil-Clients."""

import hashlib
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from services.historical_energy import (
    historical_data_status,
    historical_series,
    historical_summary,
    member_metering_points,
)
from services.mobile_link import (
    MobileLinkError,
    begin_redeem_mobile_link,
    create_mobile_link,
    device_identifier_hash,
    register_mobile_link_request,
)


ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
MAX_ENERGY_RANGE_DAYS = 366 * 3
PROFILE_FIELD_LIMITS = {
    'email': 254,
    'phone': 50,
    'address_street': 200,
    'address_zip': 20,
    'address_city': 100,
    'account_holder': 200,
    'iban': 34,
    'bic': 11,
}
APNS_TOKEN_LENGTHS = {64, 128}
FCM_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_:\-.]{20,4096}$')
REFERENCE_GRID_CONSUMPTION_CT = float(
    os.environ.get('EEG_REFERENCE_GRID_PRICE_CT', '25.0'))
REFERENCE_PUBLIC_FEED_CT = float(
    os.environ.get('EEG_REFERENCE_PUBLIC_FEED_PRICE_CT', '4.5'))


def _utc_now():
    return datetime.now(timezone.utc)


def _timestamp(value):
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _token_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _serialize(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _error(message, status=400, code='invalid_request'):
    return jsonify({'error': {'code': code, 'message': message}}), status


def create_mobile_api_blueprint(
        get_db, get_real_ip, check_login_rate, record_failed_login,
        reset_login_attempts, audit_log, get_member_stats,
        get_member_account_summary, get_invoice_carryovers,
        render_invoice_pdf, send_mobile_link_email, mobile_link_url,
        get_public_config, send_member_feedback_email, csrf):
    api = Blueprint('mobile_api', __name__, url_prefix='/api/v1')
    csrf.exempt(api)

    def issue_tokens(db, user_id, device_hash=None, device_name=None, commit=True):
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(48)
        now = _utc_now()
        access_expires = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
        refresh_expires = now + timedelta(days=REFRESH_TOKEN_DAYS)
        db.execute(
            'DELETE FROM mobile_api_tokens WHERE refresh_expires_at <= ?',
            (_timestamp(now),),
        )
        db.execute("""
            INSERT INTO mobile_api_tokens (
                user_id, access_token_hash, refresh_token_hash,
                created_at, access_expires_at, refresh_expires_at,
                device_identifier_hash, device_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, _token_hash(access_token), _token_hash(refresh_token),
            _timestamp(now), _timestamp(access_expires), _timestamp(refresh_expires),
            device_hash, (device_name or '')[:80] or None,
        ))
        if commit:
            db.commit()
        return {
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': ACCESS_TOKEN_MINUTES * 60,
            'refresh_token': refresh_token,
            'refresh_expires_in': REFRESH_TOKEN_DAYS * 86400,
        }

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get('Authorization', '')
            scheme, _, token = header.partition(' ')
            if scheme.lower() != 'bearer' or not token:
                return _error('Anmeldung erforderlich.', 401, 'unauthorized')
            db = get_db()
            row = db.execute("""
                SELECT t.id AS token_id, t.user_id, t.device_identifier_hash,
                       u.username, u.email,
                       u.member_id, u.is_admin, u.role
                FROM mobile_api_tokens t
                JOIN users u ON u.id=t.user_id
                WHERE t.access_token_hash=? AND t.revoked_at IS NULL
                  AND t.access_expires_at > ?
            """, (_token_hash(token), _timestamp(_utc_now()))).fetchone()
            if not row:
                return _error('Sitzung ist abgelaufen.', 401, 'token_expired')
            if row['device_identifier_hash']:
                try:
                    request_device_hash = device_identifier_hash(
                        request.headers.get('X-EEG-Device-ID', ''))
                except MobileLinkError:
                    return _error('Gerätebindung fehlt.', 401, 'device_mismatch')
                if not secrets.compare_digest(
                        row['device_identifier_hash'], request_device_hash):
                    return _error('Diese Sitzung gehört zu einem anderen Gerät.', 401, 'device_mismatch')
            if not row['member_id']:
                return _error('Diesem Konto ist kein Mitglied zugeordnet.', 403, 'member_required')
            member = db.execute(
                'SELECT * FROM members WHERE id=? AND active=1',
                (row['member_id'],),
            ).fetchone()
            if not member:
                return _error('Mitglied ist nicht aktiv.', 403, 'member_inactive')
            g.mobile_user = dict(row)
            g.mobile_member = member
            db.execute(
                'UPDATE mobile_api_tokens SET last_used_at=? WHERE id=?',
                (_timestamp(_utc_now()), row['token_id']),
            )
            db.commit()
            return view(*args, **kwargs)
        return wrapped

    @api.after_request
    def api_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @api.errorhandler(Exception)
    def api_exception(error):
        if isinstance(error, HTTPException):
            return _error(error.description, error.code or 500, 'http_error')
        current_app.logger.exception('Mobile API error')
        return _error('Interner Serverfehler.', 500, 'server_error')

    @api.post('/auth/login')
    def login():
        ip = get_real_ip()
        blocked_for = check_login_rate(ip)
        if blocked_for > 0:
            return _error(
                f'Zu viele Fehlversuche. Bitte {blocked_for} Sekunden warten.',
                429, 'rate_limited',
            )
        payload = request.get_json(silent=True) or {}
        identifier = str(payload.get('username') or '').strip().lower()
        password = str(payload.get('password') or '')
        if not identifier or not password:
            return _error('Benutzername und Passwort sind erforderlich.')
        db = get_db()
        candidates = db.execute("""
            SELECT * FROM users
            WHERE LOWER(username)=? OR LOWER(email)=?
            ORDER BY id
        """, (identifier, identifier)).fetchall()
        user = next(
            (candidate for candidate in candidates
             if check_password_hash(candidate['password_hash'], password)),
            None,
        )
        if not user:
            record_failed_login(ip)
            audit_log('mobile_login_failed', f'Mobile Login fehlgeschlagen für "{identifier}"',
                      user_id=0, username=identifier)
            return _error('Ungültiger Benutzername oder Passwort.', 401, 'invalid_credentials')
        if user['password_change_required']:
            return _error(
                'Bitte das Passwort zuerst im Webportal ändern.',
                403, 'password_change_required',
            )
        if not user['member_id']:
            return _error('Diesem Konto ist kein Mitglied zugeordnet.', 403, 'member_required')
        member = db.execute(
            'SELECT id, name FROM members WHERE id=? AND active=1',
            (user['member_id'],),
        ).fetchone()
        if not member:
            return _error('Mitglied ist nicht aktiv.', 403, 'member_inactive')
        reset_login_attempts(ip)
        raw_device_id = str(payload.get('device_id') or '').strip()
        device_hash = None
        if raw_device_id:
            try:
                device_hash = device_identifier_hash(raw_device_id)
            except MobileLinkError as exc:
                return _error(str(exc))
        tokens = issue_tokens(
            db, user['id'], device_hash, str(payload.get('device_name') or '')[:80])
        audit_log('mobile_login', 'Anmeldung über die iOS-API',
                  user_id=user['id'], username=user['username'])
        return jsonify({
            **tokens,
            'user': {
                'id': user['id'], 'username': user['username'],
                'member_id': member['id'], 'member_name': member['name'],
            },
        })

    @api.post('/auth/link/request')
    def request_mobile_link():
        ip = get_real_ip()
        blocked_for = check_login_rate(ip)
        if blocked_for > 0:
            return _error(
                f'Zu viele Anfragen. Bitte {blocked_for} Sekunden warten.',
                429, 'rate_limited',
            )
        payload = request.get_json(silent=True) or {}
        email = str(payload.get('email') or '').strip().lower()
        if not email or len(email) > 254 or email.count('@') != 1:
            return _error('Bitte eine gültige E-Mail-Adresse angeben.')
        db = get_db()
        allowed = register_mobile_link_request(db, email, ip)
        user = db.execute("""
            SELECT u.id, u.username, u.email, u.member_id, u.password_change_required,
                   m.name AS member_name
            FROM users u JOIN members m ON m.id=u.member_id AND m.active=1
            WHERE LOWER(COALESCE(u.email, ''))=? AND u.password_change_required=0
            ORDER BY u.id LIMIT 1
        """, (email,)).fetchone()
        if user and allowed:
            try:
                link = create_mobile_link(db, user['id'], delivery='email')
                send_mobile_link_email(
                    db, user, mobile_link_url(link['link_token']),
                    link['code'], link['expires_at'],
                )
                audit_log('mobile_link_email', 'App-Verbindungslink per E-Mail angefordert',
                          user_id=user['id'], username=user['username'])
            except Exception:
                current_app.logger.exception('Mobile connection email could not be sent')
        return jsonify({
            'accepted': True,
            'message': 'Falls ein aktives Mitgliedskonto gefunden wurde, wurde eine E-Mail versendet.',
        })

    @api.post('/auth/link/redeem')
    def redeem_mobile_link():
        ip = get_real_ip()
        blocked_for = check_login_rate(ip)
        if blocked_for > 0:
            return _error(
                f'Zu viele Fehlversuche. Bitte {blocked_for} Sekunden warten.',
                429, 'rate_limited',
            )
        payload = request.get_json(silent=True) or {}
        db = get_db()
        try:
            user, install_hash = begin_redeem_mobile_link(
                db,
                code=str(payload.get('code') or '').strip() or None,
                link_token=str(payload.get('link_token') or '').strip() or None,
                device_id=str(payload.get('device_id') or '').strip(),
            )
        except MobileLinkError as exc:
            record_failed_login(ip)
            audit_log('mobile_link_failed', 'Ungültiger App-Verbindungsversuch',
                      user_id=0, username='mobile-link')
            return _error(str(exc), 401, 'invalid_connection_code')
        tokens = issue_tokens(
            db, user['user_id'], install_hash,
            str(payload.get('device_name') or '')[:80], commit=False,
        )
        db.commit()
        reset_login_attempts(ip)
        audit_log('mobile_link_redeemed', 'iOS-App einmalig verbunden',
                  user_id=user['user_id'], username=user['username'])
        return jsonify({
            **tokens,
            'user': {
                'id': user['user_id'], 'username': user['username'],
                'member_id': user['member_id'], 'member_name': user['member_name'],
            },
        })

    @api.post('/auth/refresh')
    def refresh():
        payload = request.get_json(silent=True) or {}
        refresh_token = str(payload.get('refresh_token') or '')
        if not refresh_token:
            return _error('Refresh-Token fehlt.', 401, 'unauthorized')
        db = get_db()
        row = db.execute("""
            SELECT t.id, t.user_id, t.device_identifier_hash, t.device_name
            FROM mobile_api_tokens t
            JOIN users u ON u.id=t.user_id
            JOIN members m ON m.id=u.member_id AND m.active=1
            WHERE t.refresh_token_hash=? AND t.revoked_at IS NULL
              AND t.refresh_expires_at > ?
              AND u.password_change_required=0
        """, (_token_hash(refresh_token), _timestamp(_utc_now()))).fetchone()
        if not row:
            return _error('Sitzung kann nicht erneuert werden.', 401, 'refresh_expired')
        if row['device_identifier_hash']:
            try:
                request_device_hash = device_identifier_hash(
                    request.headers.get('X-EEG-Device-ID', ''))
            except MobileLinkError:
                return _error('Gerätebindung fehlt.', 401, 'device_mismatch')
            if not secrets.compare_digest(row['device_identifier_hash'], request_device_hash):
                return _error('Diese Sitzung gehört zu einem anderen Gerät.', 401, 'device_mismatch')
        else:
            try:
                request_device_hash = device_identifier_hash(
                    request.headers.get('X-EEG-Device-ID', ''))
            except MobileLinkError:
                request_device_hash = None
        db.execute(
            'UPDATE mobile_api_tokens SET revoked_at=? WHERE id=?',
            (_timestamp(_utc_now()), row['id']),
        )
        db.commit()
        return jsonify(issue_tokens(
            db, row['user_id'], row['device_identifier_hash'] or request_device_hash,
            row['device_name']))

    @api.post('/auth/logout')
    @authenticated
    def logout():
        db = get_db()
        if g.mobile_user.get('device_identifier_hash'):
            db.execute(
                "UPDATE mobile_devices SET disabled_at=datetime('now') "
                "WHERE user_id=? AND install_identifier_hash=?",
                (g.mobile_user['user_id'], g.mobile_user['device_identifier_hash']),
            )
        else:
            # Legacy sessions without installation binding may only disable
            # equally unbound device registrations, never another bound iPhone.
            db.execute(
                "UPDATE mobile_devices SET disabled_at=datetime('now') "
                "WHERE user_id=? AND install_identifier_hash IS NULL",
                (g.mobile_user['user_id'],),
            )
        db.execute(
            'UPDATE mobile_api_tokens SET revoked_at=? WHERE id=?',
            (_timestamp(_utc_now()), g.mobile_user['token_id']),
        )
        db.commit()
        audit_log('mobile_logout', 'Abmeldung über die iOS-API',
                  user_id=g.mobile_user['user_id'], username=g.mobile_user['username'])
        return '', 204

    @api.put('/devices/current')
    @authenticated
    def register_device():
        payload = request.get_json(silent=True) or {}
        platform = str(payload.get('platform') or 'ios').strip().lower()
        raw_device_token = str(payload.get('device_token') or '').strip()
        device_token = raw_device_token.lower() if platform == 'ios' else raw_device_token
        environment = str(payload.get('environment') or 'sandbox').strip().lower()
        app_version = str(payload.get('app_version') or '').strip()[:40]
        if platform not in {'ios', 'android'}:
            return _error('Ungültige Geräteplattform.')
        if platform == 'ios' and (
                len(device_token) not in APNS_TOKEN_LENGTHS
                or any(char not in '0123456789abcdef' for char in device_token)):
            return _error('Ungültiges APNs-Geräte-Token.')
        if platform == 'android' and not FCM_TOKEN_PATTERN.fullmatch(device_token):
            return _error('Ungültiges FCM-Geräte-Token.')
        if platform == 'ios' and environment not in {'sandbox', 'production'}:
            return _error('Ungültige APNs-Umgebung.')
        if platform == 'android':
            environment = 'production'
        db = get_db()
        db.execute("""
            INSERT INTO mobile_devices (
                user_id, device_token, platform, apns_environment, app_version,
                install_identifier_hash,
                last_seen_at, disabled_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), NULL)
            ON CONFLICT(device_token) DO UPDATE SET
                user_id=excluded.user_id,
                platform=excluded.platform,
                apns_environment=excluded.apns_environment,
                app_version=excluded.app_version,
                install_identifier_hash=excluded.install_identifier_hash,
                last_seen_at=datetime('now'),
                disabled_at=NULL
        """, (
            g.mobile_user['user_id'], device_token, platform, environment, app_version,
            g.mobile_user.get('device_identifier_hash'),
        ))
        db.commit()
        return jsonify({'registered': True})

    @api.delete('/devices/current')
    @authenticated
    def unregister_device():
        payload = request.get_json(silent=True) or {}
        device_token = str(payload.get('device_token') or '').strip().lower()
        db = get_db()
        db.execute(
            "UPDATE mobile_devices SET disabled_at=datetime('now') "
            'WHERE user_id=? AND device_token=?',
            (g.mobile_user['user_id'], device_token),
        )
        db.commit()
        return '', 204

    @api.get('/notification-preferences')
    @authenticated
    def notification_preferences():
        row = get_db().execute("""
            SELECT notifications_enabled, sound_enabled, invoice_notifications,
                   community_notifications
            FROM mobile_devices
            WHERE user_id=? AND disabled_at IS NULL
            ORDER BY last_seen_at DESC LIMIT 1
        """, (g.mobile_user['user_id'],)).fetchone()
        defaults = {
            'notifications_enabled': True, 'sound_enabled': True,
            'invoice_notifications': True, 'community_notifications': True,
        }
        if row:
            defaults = {key: bool(row[key]) for key in defaults}
        return jsonify({'preferences': defaults})

    @api.patch('/notification-preferences')
    @authenticated
    def update_notification_preferences():
        payload = request.get_json(silent=True) or {}
        fields = (
            'notifications_enabled', 'sound_enabled',
            'invoice_notifications', 'community_notifications',
        )
        values = {}
        for field in fields:
            if field in payload:
                if not isinstance(payload[field], bool):
                    return _error(f'{field} muss ein Wahrheitswert sein.')
                values[field] = int(payload[field])
        if not values:
            return _error('Keine Benachrichtigungseinstellung übermittelt.')
        assignments = ', '.join(f'{field}=?' for field in values)
        db = get_db()
        db.execute(
            f'UPDATE mobile_devices SET {assignments} WHERE user_id=? AND disabled_at IS NULL',
            (*values.values(), g.mobile_user['user_id']),
        )
        db.commit()
        return jsonify({'updated': True})

    def public_member(member, include_sensitive=True):
        fields = (
            'id', 'name', 'email', 'phone', 'address_street', 'address_zip',
            'address_city', 'account_holder', 'iban', 'bic', 'bezug_zp',
            'einspeiser_zp', 'teilnahme', 'newsletter_optout', 'active',
        )
        if not include_sensitive:
            fields = ('id', 'name', 'email', 'phone', 'newsletter_optout')
        payload = {field: member[field] for field in fields}
        if 'active' in payload:
            payload['active'] = bool(payload['active'])
        return payload

    @api.get('/me')
    @authenticated
    def me():
        organization = get_public_config(get_db())
        legal = organization.get('org_legal') or ''
        zvr_match = re.search(r'ZVR\D*(\d+)', legal, re.IGNORECASE)
        return jsonify({
            'member': public_member(g.mobile_member),
            'organization': {
                'name': organization.get('org_name') or 'EEG Trabocherstraße',
                'address': organization.get('org_address') or '',
                'legal': legal,
                'zvr': f'ZVR {zvr_match.group(1)}' if zvr_match else legal,
            },
        })

    @api.patch('/me')
    @authenticated
    def update_me():
        payload = request.get_json(silent=True) or {}
        allowed = (
            'email', 'phone', 'address_street', 'address_zip', 'address_city',
            'account_holder', 'iban', 'bic', 'newsletter_optout',
        )
        values = {}
        for field in allowed:
            if field in payload:
                values[field] = payload[field]
        if not values:
            return _error('Keine änderbaren Felder übermittelt.')
        if 'newsletter_optout' in values:
            newsletter_value = values['newsletter_optout']
            if not isinstance(newsletter_value, bool) and newsletter_value not in (0, 1):
                return _error('newsletter_optout muss ein Wahrheitswert sein.')
            values['newsletter_optout'] = 1 if bool(newsletter_value) else 0
        for field in PROFILE_FIELD_LIMITS:
            if field in values and not isinstance(values[field], str):
                return _error(f'{field} muss Text sein.')
        if 'iban' in values:
            values['iban'] = ''.join(values['iban'].split()).upper()
        if 'bic' in values:
            values['bic'] = ''.join(values['bic'].split()).upper()
        for field, limit in PROFILE_FIELD_LIMITS.items():
            if field not in values:
                continue
            values[field] = values[field].strip()
            if len(values[field]) > limit:
                return _error(f'{field} darf höchstens {limit} Zeichen enthalten.')
        email = values.get('email')
        if email and (email.count('@') != 1 or email.startswith('@') or email.endswith('@')):
            return _error('Bitte eine gültige E-Mail-Adresse angeben.')
        iban = values.get('iban')
        if iban and (not iban.isalnum() or not 15 <= len(iban) <= 34):
            return _error('Bitte eine gültige IBAN angeben.')
        bic = values.get('bic')
        if bic and (not bic.isalnum() or len(bic) not in (8, 11)):
            return _error('Bitte einen gültigen BIC angeben.')
        assignments = ', '.join(f'{field}=?' for field in values)
        db = get_db()
        db.execute(
            f"UPDATE members SET {assignments}, updated_at=datetime('now') WHERE id=?",
            (*values.values(), g.mobile_member['id']),
        )
        db.commit()
        audit_log('mobile_profile_update', 'Eigene Stammdaten über iOS aktualisiert',
                  user_id=g.mobile_user['user_id'], username=g.mobile_user['username'])
        member = db.execute('SELECT * FROM members WHERE id=?', (g.mobile_member['id'],)).fetchone()
        return jsonify({'member': public_member(member)})

    @api.get('/me/photo')
    @authenticated
    def profile_photo():
        row = get_db().execute(
            'SELECT mime_type, photo_data FROM member_profile_photos WHERE member_id=?',
            (g.mobile_member['id'],),
        ).fetchone()
        if not row:
            return _error('Kein Profilfoto hinterlegt.', 404, 'not_found')
        from flask import Response
        return Response(row['photo_data'], mimetype=row['mime_type'])

    @api.put('/me/photo')
    @authenticated
    def update_profile_photo():
        mime_type = (request.content_type or '').split(';', 1)[0].lower()
        photo = request.get_data(cache=False)
        valid_signature = (
            mime_type == 'image/jpeg' and photo.startswith(b'\xff\xd8\xff')
        ) or (
            mime_type == 'image/png' and photo.startswith(b'\x89PNG\r\n\x1a\n')
        )
        if not valid_signature:
            return _error('Bitte ein gültiges JPEG- oder PNG-Foto auswählen.')
        if len(photo) > 2 * 1024 * 1024:
            return _error('Das Profilfoto darf höchstens 2 MB groß sein.', 413, 'file_too_large')
        db = get_db()
        db.execute("""
            INSERT INTO member_profile_photos(member_id, mime_type, photo_data, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(member_id) DO UPDATE SET
                mime_type=excluded.mime_type,
                photo_data=excluded.photo_data,
                updated_at=datetime('now')
        """, (g.mobile_member['id'], mime_type, photo))
        db.commit()
        audit_log('mobile_profile_photo', 'Profilfoto über iOS aktualisiert',
                  user_id=g.mobile_user['user_id'], username=g.mobile_user['username'])
        return jsonify({'updated': True})

    @api.delete('/me/photo')
    @authenticated
    def delete_profile_photo():
        db = get_db()
        db.execute(
            'DELETE FROM member_profile_photos WHERE member_id=?',
            (g.mobile_member['id'],),
        )
        db.commit()
        return '', 204

    @api.post('/member-feedback')
    @authenticated
    def create_member_feedback():
        message = str(request.form.get('message') or '').strip()
        if len(message) > 4000:
            return _error('Die Nachricht darf höchstens 4.000 Zeichen enthalten.')
        files = request.files.getlist('attachments')
        if len(files) > 5:
            return _error('Es können höchstens fünf Anlagen übermittelt werden.')
        attachments = []
        total_size = 0
        signatures = {
            'image/jpeg': lambda data: data.startswith(b'\xff\xd8\xff'),
            'image/png': lambda data: data.startswith(b'\x89PNG\r\n\x1a\n'),
            'application/pdf': lambda data: data.startswith(b'%PDF-'),
        }
        for uploaded in files:
            mime_type = (uploaded.mimetype or '').lower()
            data = uploaded.read(5 * 1024 * 1024 + 1)
            if mime_type not in signatures or not signatures[mime_type](data):
                return _error('Erlaubt sind ausschließlich JPEG-, PNG- und PDF-Dateien.')
            if len(data) > 5 * 1024 * 1024:
                return _error('Eine Anlage darf höchstens 5 MB groß sein.', 413, 'file_too_large')
            total_size += len(data)
            if total_size > 15 * 1024 * 1024:
                return _error('Alle Anlagen dürfen zusammen höchstens 15 MB groß sein.', 413, 'file_too_large')
            filename = secure_filename(uploaded.filename or '') or (
                'foto.jpg' if mime_type == 'image/jpeg'
                else 'foto.png' if mime_type == 'image/png' else 'dokument.pdf'
            )
            attachments.append((filename[:180], mime_type, data))

        def optional_float(name, minimum, maximum):
            raw = str(request.form.get(name) or '').strip()
            if not raw:
                return None
            try:
                value = float(raw)
            except ValueError as exc:
                raise ValueError(f'{name} ist ungültig.') from exc
            if not minimum <= value <= maximum:
                raise ValueError(f'{name} liegt außerhalb des gültigen Bereichs.')
            return value

        try:
            latitude = optional_float('latitude', -90, 90)
            longitude = optional_float('longitude', -180, 180)
            accuracy = optional_float('location_accuracy_m', 0, 100000)
        except ValueError as error:
            return _error(str(error))
        if latitude is None or longitude is None:
            return _error(
                'Zum Schutz und zur Zuordnung der Nachricht ist ein freigegebener Standort erforderlich.',
                400, 'location_required')
        if not message and not attachments:
            return _error('Bitte eine Nachricht oder Anlage hinzufügen.')

        db = get_db()
        feedback_id = db.execute("""
            INSERT INTO member_feedback(
                member_id, user_id, message, latitude, longitude,
                location_accuracy_m, source_ip, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
        """, (
            g.mobile_member['id'], g.mobile_user['user_id'], message or None,
            latitude, longitude, accuracy, get_real_ip(),
        )).lastrowid
        db.executemany("""
            INSERT INTO member_feedback_attachments(
                feedback_id, filename, mime_type, file_size, file_data
            ) VALUES (?, ?, ?, ?, ?)
        """, [
            (feedback_id, filename, mime_type, len(data), data)
            for filename, mime_type, data in attachments
        ])
        db.commit()
        audit_log(
            'mobile_member_feedback',
            f'Mitgliedsnachricht #{feedback_id} mit {len(attachments)} Anlage(n) übermittelt',
            user_id=g.mobile_user['user_id'], username=g.mobile_user['username'],
        )
        email_recipient_count = 0
        try:
            email_recipient_count = send_member_feedback_email(db, feedback_id)
        except Exception:
            current_app.logger.exception(
                'Admin mail for member feedback %s could not be sent', feedback_id)
        return jsonify({
            'id': feedback_id,
            'received': True,
            'attachment_count': len(attachments),
            'email_recipient_count': email_recipient_count,
        }), 201

    def account_payload(db, member_id):
        account = get_member_account_summary(db, member_id)
        keys = ('balance', 'open_claims', 'open_credits', 'overdue_claims')
        return {
            **{key: account.get(key, 0) for key in keys},
            'history': _serialize(account.get('history', [])[:100]),
        }

    def unread_messages(db):
        rows = db.execute("""
            SELECT m.id, m.title, m.body, m.level, m.created_at, m.expires_at
            FROM mobile_messages m
            LEFT JOIN mobile_message_reads r
              ON r.message_id=m.id AND r.user_id=?
            WHERE m.active=1 AND r.message_id IS NULL
              AND (m.member_id IS NULL OR m.member_id=?)
              AND m.starts_at <= datetime('now')
              AND (m.expires_at IS NULL OR m.expires_at > datetime('now'))
            ORDER BY m.created_at, m.id
        """, (g.mobile_user['user_id'], g.mobile_member['id'])).fetchall()
        return [dict(row) for row in rows]

    def invoice_rows(db, member_id):
        rows = db.execute("""
            SELECT i.id, i.period_from, i.period_to, i.status, i.data_status, i.created_at,
                   COALESCE(SUM(CASE WHEN ii.type='consumption' THEN ii.amount_eur ELSE 0 END), 0) total_cons,
                   COALESCE(SUM(CASE WHEN ii.type='generation' THEN ii.amount_eur ELSE 0 END), 0) total_gen,
                   COALESCE(SUM(ii.kwh), 0) total_kwh
            FROM invoices i
            LEFT JOIN invoice_items ii ON ii.invoice_id=i.id AND ii.member_id=?
            WHERE i.id IN (
                SELECT invoice_id FROM invoice_items WHERE member_id=?
                UNION SELECT invoice_id FROM invoice_carryovers WHERE member_id=?
            )
            GROUP BY i.id ORDER BY i.period_from DESC
        """, (member_id, member_id, member_id)).fetchall()
        account = get_member_account_summary(db, member_id)
        payment_by_invoice = {row['invoice_id']: row for row in account['rows']}
        result = []
        for row in rows:
            item = dict(row)
            payment = payment_by_invoice.get(row['id'])
            item['net_total'] = payment['net_total'] if payment else round(row['total_cons'] - row['total_gen'], 2)
            item['paid'] = bool(payment['paid']) if payment else False
            item['booking_date'] = payment['booking_date'] if payment else ''
            result.append(item)
        return result

    @api.get('/dashboard')
    @authenticated
    def dashboard():
        db = get_db()
        invoices = invoice_rows(db, g.mobile_member['id'])
        stats = None
        if invoices:
            latest = invoices[0]
            stats = get_member_stats(
                db, g.mobile_member, latest['period_from'], latest['period_to'],
            )
            stats['net_total'] = latest['net_total']
            stats['invoice_id'] = latest['id']
        return jsonify({
            'member': public_member(g.mobile_member, include_sensitive=False),
            'account': account_payload(db, g.mobile_member['id']),
            'stats': stats,
            'recent_invoices': invoices[:5],
            'unread_messages': unread_messages(db),
        })

    @api.get('/energy')
    @authenticated
    def energy():
        today = date.today()
        try:
            period_to = date.fromisoformat(request.args.get('to') or today.isoformat())
            period_from = date.fromisoformat(
                request.args.get('from') or period_to.replace(day=1).isoformat()
            )
        except ValueError:
            return _error('Zeitraum muss im Format YYYY-MM-DD angegeben werden.')
        if period_from > period_to or (period_to - period_from).days > MAX_ENERGY_RANGE_DAYS:
            return _error('Ungültiger oder zu großer Zeitraum.')
        stats = get_member_stats(
            get_db(), g.mobile_member, period_from.isoformat(), period_to.isoformat(),
        )
        return jsonify({'from': period_from.isoformat(), 'to': period_to.isoformat(), 'stats': stats})

    @api.get('/data-status')
    @authenticated
    def data_status():
        return jsonify({'data_status': historical_data_status(get_db(), g.mobile_member)})

    @api.get('/metering-points')
    @authenticated
    def metering_points():
        points = member_metering_points(get_db(), g.mobile_member)
        return jsonify({'metering_points': [{
            'id': point['metering_point_id'],
            'masked_id': point['masked_id'],
            'direction': point['direction'],
            'role': point['role'],
            'valid_from': point['valid_from'],
            'valid_to': point['valid_to'],
        } for point in points]})

    @api.get('/energy/summary')
    @authenticated
    def energy_summary():
        today = date.today()
        try:
            period_to = date.fromisoformat(request.args.get('to') or today.isoformat())
            period_from = date.fromisoformat(
                request.args.get('from') or period_to.replace(day=1).isoformat()
            )
        except ValueError:
            return _error('Zeitraum muss im Format YYYY-MM-DD angegeben werden.')
        if period_from > period_to or (period_to - period_from).days > MAX_ENERGY_RANGE_DAYS:
            return _error('Ungültiger oder zu großer Zeitraum.')
        selected_point = (request.args.get('metering_point') or '').strip() or None
        try:
            summary = historical_summary(
                get_db(), g.mobile_member, period_from, period_to, selected_point
            )
        except PermissionError:
            return _error('Zählpunkt nicht gefunden.', 404, 'not_found')
        return jsonify({
            'from': period_from.isoformat(),
            'to': period_to.isoformat(),
            'is_live': False,
            'notice': 'Historische Energiedaten aus dem letzten Datenimport.',
            **summary,
        })

    @api.get('/energy/series')
    @authenticated
    def energy_series():
        try:
            period_to = date.fromisoformat(request.args.get('to') or '')
            period_from = date.fromisoformat(request.args.get('from') or '')
        except ValueError:
            return _error('Zeitraum muss im Format YYYY-MM-DD angegeben werden.')
        resolution = (request.args.get('resolution') or 'day').strip()
        limits = {'quarter_hour': 31, 'hour': 366, 'day': 366 * 3, 'month': 366 * 10}
        if resolution not in limits:
            return _error('Auflösung muss quarter_hour, hour, day oder month sein.')
        if period_from > period_to or (period_to - period_from).days > limits[resolution]:
            return _error('Ungültiger oder für diese Auflösung zu großer Zeitraum.')
        selected_point = (request.args.get('metering_point') or '').strip() or None
        try:
            values = historical_series(
                get_db(), g.mobile_member, period_from, period_to,
                resolution, selected_point,
            )
        except PermissionError:
            return _error('Zählpunkt nicht gefunden.', 404, 'not_found')
        return jsonify({
            'from': period_from.isoformat(),
            'to': period_to.isoformat(),
            'resolution': resolution,
            'is_live': False,
            'unit': 'kWh',
            'series': values,
        })

    @api.get('/prices')
    @authenticated
    def energy_prices():
        rows = get_db().execute("""
            SELECT id, valid_from, valid_to, price_consumption,
                   price_generation, description
            FROM prices
            ORDER BY valid_from DESC, id DESC
        """).fetchall()
        today = date.today().isoformat()

        def price_payload(row):
            return {
                'id': row['id'],
                'valid_from': row['valid_from'],
                'valid_to': row['valid_to'],
                'eeg_consumption_ct': float(row['price_consumption']),
                'eeg_generation_ct': float(row['price_generation']),
                'description': row['description'],
            }

        prices = [price_payload(row) for row in rows]
        current = next(
            (price for price in prices
             if price['valid_from'] <= today <= price['valid_to']),
            prices[0] if prices else None,
        )
        return jsonify({
            'current': current,
            'history': prices,
            'reference': {
                'grid_consumption_ct': REFERENCE_GRID_CONSUMPTION_CT,
                'public_feed_ct': REFERENCE_PUBLIC_FEED_CT,
                'is_estimate': True,
            },
        })

    @api.get('/invoices')
    @authenticated
    def invoices():
        return jsonify({'invoices': invoice_rows(get_db(), g.mobile_member['id'])})

    @api.get('/invoices/<int:invoice_id>')
    @authenticated
    def invoice_detail(invoice_id):
        db = get_db()
        invoice = db.execute("""
            SELECT * FROM invoices WHERE id=? AND id IN (
                SELECT invoice_id FROM invoice_items WHERE member_id=?
                UNION SELECT invoice_id FROM invoice_carryovers WHERE member_id=?
            )
        """, (invoice_id, g.mobile_member['id'], g.mobile_member['id'])).fetchone()
        if not invoice:
            return _error('Abrechnung nicht gefunden.', 404, 'not_found')
        items = db.execute(
            'SELECT id, type, kwh, price_per_kwh, amount_eur, paid, paid_at '
            'FROM invoice_items WHERE invoice_id=? AND member_id=? ORDER BY id',
            (invoice_id, g.mobile_member['id']),
        ).fetchall()
        carryovers = get_invoice_carryovers(db, invoice_id, g.mobile_member['id'])
        return jsonify({
            'invoice': dict(invoice),
            'items': [dict(row) for row in items],
            'carryovers': [dict(row) for row in carryovers],
        })

    @api.get('/invoices/<int:invoice_id>/pdf')
    @authenticated
    def invoice_pdf(invoice_id):
        db = get_db()
        exists = db.execute("""
            SELECT 1 FROM invoices WHERE id=? AND id IN (
                SELECT invoice_id FROM invoice_items WHERE member_id=?
                UNION SELECT invoice_id FROM invoice_carryovers WHERE member_id=?
            )
        """, (invoice_id, g.mobile_member['id'], g.mobile_member['id'])).fetchone()
        if not exists:
            return _error('Abrechnung nicht gefunden.', 404, 'not_found')
        audit_log(
            'mobile_pdf_preview', f'PDF-Vorschau für Abrechnung {invoice_id}',
            user_id=g.mobile_user['user_id'], username=g.mobile_user['username'],
        )
        return render_invoice_pdf(invoice_id, g.mobile_member['id'], preview=True)

    @api.get('/messages')
    @authenticated
    def messages():
        return jsonify({'messages': unread_messages(get_db())})

    @api.post('/messages/<int:message_id>/read')
    @authenticated
    def mark_message_read(message_id):
        db = get_db()
        exists = db.execute("""
            SELECT 1 FROM mobile_messages
            WHERE id=? AND active=1
              AND (member_id IS NULL OR member_id=?)
        """, (message_id, g.mobile_member['id'])).fetchone()
        if not exists:
            return _error('Nachricht nicht gefunden.', 404, 'not_found')
        db.execute(
            'INSERT OR IGNORE INTO mobile_message_reads (message_id, user_id) VALUES (?, ?)',
            (message_id, g.mobile_user['user_id']),
        )
        db.commit()
        return '', 204

    @api.get('/account')
    @authenticated
    def account():
        return jsonify({'account': account_payload(get_db(), g.mobile_member['id'])})

    @api.get('/contracts')
    @authenticated
    def contracts():
        rows = get_db().execute(
            'SELECT id, type, filename, uploaded_at, uploaded_by '
            'FROM contracts WHERE member_id=? ORDER BY uploaded_at DESC',
            (g.mobile_member['id'],),
        ).fetchall()
        return jsonify({'contracts': [dict(row) for row in rows]})

    @api.get('/contracts/<int:contract_id>/pdf')
    @authenticated
    def contract_pdf(contract_id):
        row = get_db().execute(
            'SELECT filename, file_data FROM contracts WHERE id=? AND member_id=?',
            (contract_id, g.mobile_member['id']),
        ).fetchone()
        if not row:
            return _error('Vertrag nicht gefunden.', 404, 'not_found')
        from flask import Response
        response = Response(row['file_data'], mimetype='application/pdf')
        response.headers['Content-Disposition'] = 'inline; filename="contract.pdf"'
        return response

    return api
