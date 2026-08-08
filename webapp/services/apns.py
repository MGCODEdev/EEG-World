"""Minimaler, dauerhafter APNs-Versand für die native Mitglieder-App."""

import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def _b64url(data):
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _provider_token(key_path, key_id, team_id):
    with open(key_path, 'rb') as handle:
        private_key = serialization.load_pem_private_key(handle.read(), password=None)
    header = _b64url(json.dumps({'alg': 'ES256', 'kid': key_id}, separators=(',', ':')).encode())
    claims = _b64url(json.dumps({'iss': team_id, 'iat': int(time.time())}, separators=(',', ':')).encode())
    content = f'{header}.{claims}'.encode('ascii')
    signature_der = private_key.sign(content, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(signature_der)
    signature = _b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))
    return f'{header}.{claims}.{signature}'


def configured():
    return bool(
        os.environ.get('EEG_APNS_KEY_PATH')
        and os.environ.get('EEG_APNS_KEY_ID')
        and (os.environ.get('EEG_APNS_TEAM_ID') or os.environ.get('EEG_APPLE_TEAM_ID'))
        and os.environ.get('EEG_APNS_BUNDLE_ID')
    )


def send(device_token, environment, title, body, message_id, sound=True):
    token = _provider_token(
        os.environ['EEG_APNS_KEY_PATH'], os.environ['EEG_APNS_KEY_ID'],
        os.environ.get('EEG_APNS_TEAM_ID') or os.environ['EEG_APPLE_TEAM_ID'],
    )
    host = 'api.push.apple.com' if environment == 'production' else 'api.sandbox.push.apple.com'
    payload = {
        'aps': {
            'alert': {'title': title, 'body': body},
            'sound': 'eeg-notification.caf' if sound else None,
            'badge': 1,
            'category': 'EEG_MESSAGE',
            'interruption-level': 'active',
        },
        'route': 'message',
        'message_id': message_id,
    }
    if not sound:
        payload['aps'].pop('sound')
    headers = {
        'authorization': f'bearer {token}',
        'apns-topic': os.environ['EEG_APNS_BUNDLE_ID'],
        'apns-push-type': 'alert',
        'apns-priority': '10',
    }
    command = ['curl', '--silent', '--show-error', '--http2', '--max-time', '15']
    for name, value in headers.items():
        command.extend(['--header', f'{name}: {value}'])
    command.extend([
        '--header', 'content-type: application/json', '--data-binary', '@-',
        '--write-out', '\n%{http_code}', f'https://{host}/3/device/{device_token}',
    ])
    completed = subprocess.run(
        command, input=json.dumps(payload, separators=(',', ':')), text=True,
        capture_output=True, timeout=20, check=False,
    )
    if completed.returncode:
        raise OSError(completed.stderr.strip() or f'curl exit {completed.returncode}')
    body, _, status_text = completed.stdout.rpartition('\n')
    status = int(status_text)
    reason = ''
    if body:
        try:
            reason = json.loads(body).get('reason', '')
        except (ValueError, AttributeError):
            reason = body[:300]
    return status, reason


def process_outbox(db, limit=100):
    """Versendet eine Charge. Liefert Statistiken für Logs/systemd zurück."""
    if not configured():
        raise RuntimeError('APNs ist nicht konfiguriert; EEG_APNS_* Umgebungsvariablen fehlen.')
    rows = db.execute("""
        SELECT p.id, p.attempts, d.id device_id, d.device_token,
               d.apns_environment, d.sound_enabled, m.id message_id,
               m.title, m.body
        FROM mobile_push_outbox p
        JOIN mobile_devices d ON d.id=p.device_id
        JOIN mobile_messages m ON m.id=p.message_id
        WHERE p.status IN ('pending', 'retry')
          AND p.next_attempt_at <= datetime('now')
          AND d.platform='ios'
          AND d.disabled_at IS NULL AND m.active=1
        ORDER BY p.id LIMIT ?
    """, (limit,)).fetchall()
    result = {'selected': len(rows), 'sent': 0, 'retry': 0, 'failed': 0}
    for row in rows:
        try:
            status, reason = send(
                row['device_token'], row['apns_environment'], row['title'], row['body'],
                row['message_id'], bool(row['sound_enabled']),
            )
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            status, reason = 503, str(error)[:300]
        attempts = row['attempts'] + 1
        if status == 200:
            db.execute(
                "UPDATE mobile_push_outbox SET status='sent', attempts=?, sent_at=datetime('now'), last_error=NULL WHERE id=?",
                (attempts, row['id']),
            )
            result['sent'] += 1
        elif status == 410 or reason in {'BadDeviceToken', 'DeviceTokenNotForTopic', 'Unregistered'}:
            db.execute("UPDATE mobile_devices SET disabled_at=datetime('now') WHERE id=?", (row['device_id'],))
            db.execute(
                "UPDATE mobile_push_outbox SET status='failed', attempts=?, last_error=? WHERE id=?",
                (attempts, f'{status} {reason}', row['id']),
            )
            result['failed'] += 1
        elif attempts >= 6 or status in {400, 403}:
            db.execute(
                "UPDATE mobile_push_outbox SET status='failed', attempts=?, last_error=? WHERE id=?",
                (attempts, f'{status} {reason}', row['id']),
            )
            result['failed'] += 1
        else:
            delay = min(3600, 30 * (2 ** (attempts - 1)))
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            db.execute(
                "UPDATE mobile_push_outbox SET status='retry', attempts=?, next_attempt_at=?, last_error=? WHERE id=?",
                (attempts, retry_at.strftime('%Y-%m-%d %H:%M:%S'), f'{status} {reason}', row['id']),
            )
            result['retry'] += 1
        db.commit()
    return result
