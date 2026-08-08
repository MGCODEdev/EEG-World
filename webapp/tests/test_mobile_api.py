import hashlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as eegapp
from services.mobile_link import create_mobile_link, normalize_code, secret_hash


class MobileAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db_path = eegapp.DB_PATH
        self.original_csrf = eegapp.app.config['WTF_CSRF_ENABLED']
        eegapp.app.config['WTF_CSRF_ENABLED'] = False
        eegapp.DB_PATH = self.tmp.name
        eegapp.init_db()
        with eegapp.app.app_context():
            db = eegapp.get_db()
            cursor = db.execute("""
                INSERT INTO members (name, email, phone, active, newsletter_optout)
                VALUES ('Anna Energie', 'anna@example.org', '+43123', 1, 0)
            """)
            self.member_id = cursor.lastrowid
            other = db.execute("""
                INSERT INTO members (name, email, active)
                VALUES ('Fremdes Mitglied', 'fremd@example.org', 1)
            """).lastrowid
            self.other_member_id = other
            self.user_id = db.execute("""
                INSERT INTO users (
                    username, password_hash, email, is_admin, member_id, role,
                    password_change_required
                ) VALUES (?, ?, ?, 0, ?, 'member', 0)
            """, ('anna', generate_password_hash('Sichere-Passphrase-2026'),
                  'anna@example.org', self.member_id)).lastrowid
            db.execute("""
                INSERT INTO users (
                    username, password_hash, email, is_admin, role,
                    password_change_required
                ) VALUES (?, ?, ?, 1, 'admin', 0)
            """, ('mobile-admin', generate_password_hash('Admin-Passphrase-2026'),
                  'admin@example.org'))
            db.execute("""
                INSERT INTO contracts (member_id, type, filename, file_data, uploaded_by)
                VALUES (?, 'bezug', 'anna-vertrag.pdf', ?, 'Admin')
            """, (self.member_id, b'%PDF-own'))
            db.execute("""
                INSERT INTO contracts (member_id, type, filename, file_data, uploaded_by)
                VALUES (?, 'bezug', 'fremd-vertrag.pdf', ?, 'Admin')
            """, (other, b'%PDF-other'))
            db.commit()

    def tearDown(self):
        eegapp.DB_PATH = self.original_db_path
        eegapp.app.config['WTF_CSRF_ENABLED'] = self.original_csrf
        for suffix in ('', '-wal', '-shm'):
            try:
                os.unlink(self.tmp.name + suffix)
            except OSError:
                pass

    def login(self, client):
        response = client.post('/api/v1/auth/login', json={
            'username': 'anna', 'password': 'Sichere-Passphrase-2026',
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    @staticmethod
    def auth(token):
        return {'Authorization': f'Bearer {token}'}

    @staticmethod
    def device_auth(token, device_id):
        return {
            'Authorization': f'Bearer {token}',
            'X-EEG-Device-ID': device_id,
        }

    def create_link(self):
        with eegapp.app.app_context():
            return create_mobile_link(eegapp.get_db(), self.user_id, delivery='test')

    def test_login_stores_only_token_hashes_and_returns_member(self):
        with eegapp.app.test_client() as client:
            payload = self.login(client)
            response = client.get('/api/v1/me', headers=self.auth(payload['access_token']))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['member']['name'], 'Anna Energie')
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                'SELECT access_token_hash, refresh_token_hash FROM mobile_api_tokens'
            ).fetchone()
        self.assertEqual(row['access_token_hash'], hashlib.sha256(
            payload['access_token'].encode()).hexdigest())
        self.assertNotIn(payload['access_token'], tuple(row))
        self.assertNotIn(payload['refresh_token'], tuple(row))

    def test_invalid_login_is_rejected(self):
        with eegapp.app.test_client() as client:
            response = client.post('/api/v1/auth/login', json={
                'username': 'anna', 'password': 'falsch',
            })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()['error']['code'], 'invalid_credentials')

    def test_connection_code_is_hashed_single_use_and_device_bound(self):
        link = self.create_link()
        device_id = 'installation-11111111-2222-3333-4444-555555555555'
        with eegapp.app.test_client() as client:
            redeemed = client.post('/api/v1/auth/link/redeem', json={
                'code': link['code'], 'device_id': device_id, 'device_name': 'iPhone',
            })
            self.assertEqual(redeemed.status_code, 200, redeemed.get_data(as_text=True))
            tokens = redeemed.get_json()
            own_device = client.get(
                '/api/v1/me', headers=self.device_auth(tokens['access_token'], device_id))
            foreign_device = client.get(
                '/api/v1/me', headers=self.device_auth(
                    tokens['access_token'], 'installation-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'))
            foreign_refresh = client.post(
                '/api/v1/auth/refresh',
                headers={'X-EEG-Device-ID': 'installation-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},
                json={'refresh_token': tokens['refresh_token']},
            )
            reused = client.post('/api/v1/auth/link/redeem', json={
                'code': link['code'], 'device_id': device_id,
            })

        self.assertEqual(own_device.status_code, 200)
        self.assertEqual(foreign_device.status_code, 401)
        self.assertEqual(foreign_device.get_json()['error']['code'], 'device_mismatch')
        self.assertEqual(foreign_refresh.status_code, 401)
        self.assertEqual(foreign_refresh.get_json()['error']['code'], 'device_mismatch')
        self.assertEqual(reused.status_code, 401)
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                'SELECT code_hash, link_token_hash, used_at, used_device_hash '
                'FROM mobile_connection_links'
            ).fetchone()
        self.assertEqual(row['code_hash'], secret_hash(normalize_code(link['code'])))
        self.assertNotIn(link['code'], tuple(row))
        self.assertNotIn(link['link_token'], tuple(row))
        self.assertIsNotNone(row['used_at'])

    def test_magic_link_token_can_be_redeemed_once(self):
        link = self.create_link()
        device_id = 'installation-99999999-2222-3333-4444-555555555555'
        with eegapp.app.test_client() as client:
            first = client.post('/api/v1/auth/link/redeem', json={
                'link_token': link['link_token'], 'device_id': device_id,
            })
            second = client.post('/api/v1/auth/link/redeem', json={
                'link_token': link['link_token'], 'device_id': device_id,
            })
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 401)

    def test_expired_connection_code_is_rejected(self):
        link = self.create_link()
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute(
                "UPDATE mobile_connection_links SET expires_at='2000-01-01T00:00:00Z'"
            )
            db.commit()
        with eegapp.app.test_client() as client:
            response = client.post('/api/v1/auth/link/redeem', json={
                'code': link['code'],
                'device_id': 'installation-77777777-2222-3333-4444-555555555555',
            })
        self.assertEqual(response.status_code, 401)

    def test_admin_can_create_no_store_qr_connection_page(self):
        with eegapp.app.app_context():
            admin_id = eegapp.get_db().execute(
                "SELECT id FROM users WHERE username='mobile-admin'"
            ).fetchone()['id']
        with eegapp.app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = str(admin_id)
                session['_fresh'] = True
            response = client.post(f'/admin/users/{self.user_id}/mobile-link')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['Cache-Control'])
        html = response.get_data(as_text=True)
        self.assertIn('Manueller Verbindungscode', html)
        self.assertIn('data:image/png;base64,', html)

    def test_admin_can_revoke_all_mobile_access_for_user(self):
        link = self.create_link()
        device_id = 'installation-66666666-2222-3333-4444-555555555555'
        with eegapp.app.app_context():
            admin_id = eegapp.get_db().execute(
                "SELECT id FROM users WHERE username='mobile-admin'"
            ).fetchone()['id']
        with eegapp.app.test_client() as client:
            redeemed = client.post('/api/v1/auth/link/redeem', json={
                'code': link['code'], 'device_id': device_id,
            }).get_json()
            with client.session_transaction() as session:
                session['_user_id'] = str(admin_id)
                session['_fresh'] = True
            revoked = client.post(f'/admin/users/{self.user_id}/mobile-access/revoke')
            denied = client.get(
                '/api/v1/me', headers=self.device_auth(redeemed['access_token'], device_id))
        self.assertEqual(revoked.status_code, 302)
        self.assertEqual(denied.status_code, 401)

    def test_email_link_request_does_not_reveal_unknown_accounts(self):
        with eegapp.app.test_client() as client:
            response = client.post('/api/v1/auth/link/request', json={
                'email': 'unknown@example.org',
            })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['accepted'])
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                'SELECT email_hash, ip_hash FROM mobile_connection_requests'
            ).fetchone()
        self.assertNotIn('unknown@example.org', tuple(row))
        self.assertNotIn('127.0.0.1', tuple(row))

    def test_apple_association_matches_submitted_app_and_magic_link_path(self):
        with eegapp.app.test_client() as client:
            response = client.get('/.well-known/apple-app-site-association')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')
        details = response.get_json()['applinks']['details']
        self.assertEqual(
            details[0]['appIDs'],
            ['LQFUQM34Z5.at.eeg.trabocherstrasse.member'],
        )
        self.assertEqual(details[0]['components'][0]['/'], '/mobile-connect')

    def test_refresh_rotates_tokens_and_revokes_old_access(self):
        with eegapp.app.test_client() as client:
            old = self.login(client)
            refreshed = client.post('/api/v1/auth/refresh', json={
                'refresh_token': old['refresh_token'],
            })
            self.assertEqual(refreshed.status_code, 200)
            new = refreshed.get_json()
            old_access = client.get('/api/v1/me', headers=self.auth(old['access_token']))
            new_access = client.get('/api/v1/me', headers=self.auth(new['access_token']))
        self.assertEqual(old_access.status_code, 401)
        self.assertEqual(new_access.status_code, 200)
        self.assertNotEqual(old['refresh_token'], new['refresh_token'])

    def test_contracts_are_limited_to_authenticated_member(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.get('/api/v1/contracts', headers=self.auth(tokens['access_token']))
        self.assertEqual(response.status_code, 200)
        filenames = [row['filename'] for row in response.get_json()['contracts']]
        self.assertEqual(filenames, ['anna-vertrag.pdf'])

    def test_contract_pdf_is_limited_to_authenticated_member(self):
        with eegapp.app.app_context():
            rows = eegapp.get_db().execute(
                'SELECT id, member_id FROM contracts ORDER BY id'
            ).fetchall()
            own_id = next(row['id'] for row in rows if row['member_id'] == self.member_id)
            foreign_id = next(row['id'] for row in rows if row['member_id'] == self.other_member_id)
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            headers = self.auth(tokens['access_token'])
            own = client.get(f'/api/v1/contracts/{own_id}/pdf', headers=headers)
            foreign = client.get(f'/api/v1/contracts/{foreign_id}/pdf', headers=headers)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.mimetype, 'application/pdf')
        self.assertEqual(foreign.status_code, 404)

    def test_profile_update_changes_only_own_member(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.patch('/api/v1/me', headers=self.auth(tokens['access_token']), json={
                'phone': '+43999', 'newsletter_optout': True,
            })
        self.assertEqual(response.status_code, 200)
        member = response.get_json()['member']
        self.assertEqual(member['phone'], '+43999')
        self.assertEqual(member['newsletter_optout'], 1)

    def test_profile_update_rejects_invalid_bank_data(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.patch('/api/v1/me', headers=self.auth(tokens['access_token']), json={
                'iban': 'zu-kurz', 'bic': 'x',
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'invalid_request')

    def test_profile_photo_upload_and_download_are_member_scoped(self):
        jpeg = b'\xff\xd8\xff\xe0' + b'profile-photo'
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            headers = self.auth(tokens['access_token'])
            headers['Content-Type'] = 'image/jpeg'
            uploaded = client.put('/api/v1/me/photo', headers=headers, data=jpeg)
            downloaded = client.get(
                '/api/v1/me/photo', headers=self.auth(tokens['access_token']))
        self.assertEqual(uploaded.status_code, 200, uploaded.get_data(as_text=True))
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.mimetype, 'image/jpeg')
        self.assertEqual(downloaded.data, jpeg)
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                'SELECT member_id FROM member_profile_photos'
            ).fetchone()
        self.assertEqual(row['member_id'], self.member_id)

    def test_member_can_send_scoped_feedback_with_pdf_and_location(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.post(
                '/api/v1/member-feedback',
                headers=self.auth(tokens['access_token']),
                data={
                    'message': 'Bitte Zählerstand prüfen.',
                    'latitude': '47.123456',
                    'longitude': '15.654321',
                    'location_accuracy_m': '18.5',
                    'attachments': (io.BytesIO(b'%PDF-1.4\nmember-document'), 'zaehler.pdf'),
                },
                content_type='multipart/form-data',
            )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload['received'])
        self.assertEqual(payload['attachment_count'], 1)
        with eegapp.app.app_context():
            db = eegapp.get_db()
            feedback = db.execute('SELECT * FROM member_feedback').fetchone()
            attachment = db.execute(
                'SELECT filename, mime_type, file_data FROM member_feedback_attachments'
            ).fetchone()
        self.assertEqual(feedback['member_id'], self.member_id)
        self.assertEqual(feedback['message'], 'Bitte Zählerstand prüfen.')
        self.assertAlmostEqual(feedback['latitude'], 47.123456)
        self.assertEqual(feedback['source_ip'], '127.0.0.1')
        self.assertEqual(attachment['filename'], 'zaehler.pdf')
        self.assertEqual(attachment['mime_type'], 'application/pdf')
        self.assertTrue(attachment['file_data'].startswith(b'%PDF-'))

    def test_member_feedback_rejects_disguised_attachment(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.post(
                '/api/v1/member-feedback',
                headers=self.auth(tokens['access_token']),
                data={
                    'message': 'Anlage',
                    'attachments': (io.BytesIO(b'not-a-real-pdf'), 'falsch.pdf'),
                },
                content_type='multipart/form-data',
            )
        self.assertEqual(response.status_code, 400)
        with eegapp.app.app_context():
            count = eegapp.get_db().execute(
                'SELECT COUNT(*) FROM member_feedback'
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_member_feedback_requires_location(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.post(
                '/api/v1/member-feedback',
                headers=self.auth(tokens['access_token']),
                data={'message': 'Bitte zurückrufen.'},
                content_type='multipart/form-data',
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error']['code'], 'location_required')

    def test_feedback_mail_is_sent_only_to_opted_in_admin_with_attachment(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute("UPDATE users SET admin_feedback_email=1 WHERE username='mobile-admin'")
            settings = {
                'smtp_host': 'smtp.example.org', 'smtp_port': '587',
                'smtp_user': 'sender@example.org', 'smtp_pass': 'secret',
                'smtp_tls': 'true', 'mail_from_address': 'sender@example.org',
                'mail_reply_to': 'sender@example.org',
            }
            for key, value in settings.items():
                db.execute(
                    'INSERT INTO settings(key, value) VALUES (?, ?) '
                    'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                    (key, value),
                )
            feedback_id = db.execute("""
                INSERT INTO member_feedback(member_id, user_id, message)
                VALUES (?, ?, 'Zählerfoto im Anhang')
            """, (self.member_id, self.user_id)).lastrowid
            image_attachment_id = db.execute("""
                INSERT INTO member_feedback_attachments(
                    feedback_id, filename, mime_type, file_size, file_data
                ) VALUES (?, 'foto.jpg', 'image/jpeg', 8, ?)
            """, (feedback_id, b'\xff\xd8\xffphoto')).lastrowid
            pdf_attachment_id = db.execute("""
                INSERT INTO member_feedback_attachments(
                    feedback_id, filename, mime_type, file_size, file_data
                ) VALUES (?, 'zaehler.pdf', 'application/pdf', 16, ?)
            """, (feedback_id, b'%PDF-1.4 document')).lastrowid
            db.commit()
            with patch('smtplib.SMTP') as smtp:
                count = eegapp.send_member_feedback_email(db, feedback_id)

        self.assertEqual(count, 1)
        server = smtp.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with('sender@example.org', 'secret')
        sent = server.send_message.call_args.args[0]
        self.assertIn('Mitgliedsnachricht', sent['Subject'])
        self.assertEqual(sent['To'], 'admin@example.org')
        self.assertIn('foto.jpg', sent.as_string())
        self.assertIn('zaehler.pdf', sent.as_string())
        self.assertIn(
            f'<feedback-{feedback_id}-attachment-{image_attachment_id}>',
            sent.as_string(),
        )
        html_part = next(
            part for part in sent.walk() if part.get_content_type() == 'text/html'
        )
        html = html_part.get_payload(decode=True).decode('utf-8')
        self.assertIn('width="260" height="140"', html)
        self.assertIn('height:140px', html)
        self.assertIn('BILD', html)
        self.assertIn('DOKUMENT', html)
        self.assertIn(f'attachment={image_attachment_id}', html)
        self.assertIn(f'attachment={pdf_attachment_id}', html)

    def test_admin_feedback_page_previews_images_and_documents_in_modal(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            feedback_id = db.execute("""
                INSERT INTO member_feedback(member_id, user_id, message)
                VALUES (?, ?, 'Zwei Anlagen')
            """, (self.member_id, self.user_id)).lastrowid
            image_id = db.execute("""
                INSERT INTO member_feedback_attachments(
                    feedback_id, filename, mime_type, file_size, file_data
                ) VALUES (?, 'foto.jpg', 'image/jpeg', 8, ?)
            """, (feedback_id, b'\xff\xd8\xffphoto')).lastrowid
            pdf_id = db.execute("""
                INSERT INTO member_feedback_attachments(
                    feedback_id, filename, mime_type, file_size, file_data
                ) VALUES (?, 'dokument.pdf', 'application/pdf', 16, ?)
            """, (feedback_id, b'%PDF-1.4 document')).lastrowid
            admin_id = db.execute(
                "SELECT id FROM users WHERE username='mobile-admin'"
            ).fetchone()['id']
            db.commit()

        with eegapp.app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = str(admin_id)
                session['_fresh'] = True
            response = client.get(
                f'/admin/member-feedback?id={feedback_id}&attachment={pdf_id}'
            )
            embedded_pdf = client.get(
                f'/admin/member-feedback/attachments/{pdf_id}?embed=1'
            )
            downloaded_pdf = client.get(
                f'/admin/member-feedback/attachments/{pdf_id}?download=1'
            )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('feedback-attachment-frame', html)
        self.assertIn('id="attachmentPreviewModal"', html)
        self.assertIn(f'data-attachment-id="{image_id}"', html)
        self.assertIn(f'data-attachment-id="{pdf_id}"', html)
        self.assertIn(
            f'document.querySelector(\'[data-attachment-id="{pdf_id}"]\')',
            html,
        )
        self.assertEqual(embedded_pdf.status_code, 200)
        self.assertEqual(embedded_pdf.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertIn('inline', embedded_pdf.headers['Content-Disposition'])
        self.assertIn('attachment', downloaded_pdf.headers['Content-Disposition'])

    def test_admin_can_delete_feedback_and_all_attachments(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            feedback_id = db.execute("""
                INSERT INTO member_feedback(member_id, user_id, message)
                VALUES (?, ?, 'Bitte löschen')
            """, (self.member_id, self.user_id)).lastrowid
            db.execute("""
                INSERT INTO member_feedback_attachments(
                    feedback_id, filename, mime_type, file_size, file_data
                ) VALUES (?, 'dokument.pdf', 'application/pdf', 16, ?)
            """, (feedback_id, b'%PDF-1.4 document'))
            admin_id = db.execute(
                "SELECT id FROM users WHERE username='mobile-admin'"
            ).fetchone()['id']
            db.commit()

        with eegapp.app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = str(admin_id)
                session['_fresh'] = True
            response = client.post(f'/admin/member-feedback/{feedback_id}/delete')

        self.assertEqual(response.status_code, 302)
        with eegapp.app.app_context():
            db = eegapp.get_db()
            self.assertEqual(
                db.execute(
                    'SELECT COUNT(*) FROM member_feedback WHERE id=?', (feedback_id,)
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                db.execute(
                    'SELECT COUNT(*) FROM member_feedback_attachments WHERE feedback_id=?',
                    (feedback_id,),
                ).fetchone()[0],
                0,
            )

    def test_admin_can_enable_feedback_mail_preference(self):
        with eegapp.app.app_context():
            admin_id = eegapp.get_db().execute(
                "SELECT id FROM users WHERE username='mobile-admin'"
            ).fetchone()['id']
        with eegapp.app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = str(admin_id)
                session['_fresh'] = True
            response = client.post(
                f'/admin/users/{admin_id}/feedback-email',
                data={'enabled': ['0', '1']},
            )
        self.assertEqual(response.status_code, 302)
        with eegapp.app.app_context():
            enabled = eegapp.get_db().execute(
                'SELECT admin_feedback_email FROM users WHERE id=?', (admin_id,)
            ).fetchone()['admin_feedback_email']
        self.assertEqual(enabled, 1)

    def test_invoice_endpoints_enforce_member_isolation(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            own_invoice = db.execute(
                "INSERT INTO invoices (period_from, period_to, status) VALUES (?, ?, 'finalized')",
                ('2026-01-01', '2026-01-31'),
            ).lastrowid
            foreign_invoice = db.execute(
                "INSERT INTO invoices (period_from, period_to, status) VALUES (?, ?, 'finalized')",
                ('2026-02-01', '2026-02-28'),
            ).lastrowid
            db.execute(
                "INSERT INTO invoice_items (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur) "
                "VALUES (?, ?, 'consumption', 12.5, 0.15, 1.88)",
                (own_invoice, self.member_id),
            )
            db.execute(
                "INSERT INTO invoice_items (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur) "
                "VALUES (?, ?, 'consumption', 99, 0.15, 14.85)",
                (foreign_invoice, self.other_member_id),
            )
            db.commit()
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            listing = client.get('/api/v1/invoices', headers=self.auth(tokens['access_token']))
            own = client.get(
                f'/api/v1/invoices/{own_invoice}', headers=self.auth(tokens['access_token'])
            )
            foreign = client.get(
                f'/api/v1/invoices/{foreign_invoice}', headers=self.auth(tokens['access_token'])
            )
        self.assertEqual([row['id'] for row in listing.get_json()['invoices']], [own_invoice])
        self.assertEqual(own.status_code, 200)
        self.assertEqual(foreign.status_code, 404)

    def test_energy_rejects_invalid_or_excessive_ranges(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            invalid = client.get(
                '/api/v1/energy?from=kein-datum&to=2026-01-01',
                headers=self.auth(tokens['access_token']),
            )
            excessive = client.get(
                '/api/v1/energy?from=2020-01-01&to=2026-01-01',
                headers=self.auth(tokens['access_token']),
            )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(excessive.status_code, 400)

    def test_historical_energy_endpoints_are_member_scoped_and_never_live(self):
        own_point = 'AT0080000879200000000000000000001'
        own_generation_point = 'AT0080000879200000000000000000003'
        foreign_point = 'AT0080000879200000000000000000002'
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute(
                'UPDATE members SET bezug_zp=?, bezug_ab=?, einspeiser_zp=?, einspeiser_ab=? '
                'WHERE id=?',
                (own_point, '2026-01-01', own_generation_point, '2026-01-01', self.member_id),
            )
            db.execute("""
                INSERT INTO metering_points(metering_point_id, energy_direction)
                VALUES (?, 'CONSUMPTION'), (?, 'CONSUMPTION'), (?, 'GENERATION')
            """, (own_point, foreign_point, own_generation_point))
            batch_id = db.execute("""
                INSERT INTO import_batches(
                    source_file, period_start, period_end, data_status,
                    import_status, imported_at
                ) VALUES ('test.xlsx', '2026-01-01T00:00:00',
                          '2026-01-31T23:45:00', 'final', 'committed',
                          '2026-02-01 10:00:00')
            """).lastrowid
            codes = {
                row['code']: row['id'] for row in db.execute(
                    "SELECT id, code FROM meter_codes WHERE code IN (?, ?, ?, ?)",
                    ('1-1:1.9.0 G.01', '1-1:2.9.0 G.03',
                     '1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T'),
                ).fetchall()
            }
            db.executemany("""
                INSERT INTO measurements(
                    batch_id, metering_point_id, timestamp_start, timestamp_end,
                    interval_minutes, meter_code_id, value_kwh, quality,
                    is_estimated
                ) VALUES (?, ?, '2026-01-01T00:00:00',
                          '2026-01-01T00:15:00', 15, ?, ?, ?, ?)
            """, [
                (batch_id, own_point, codes['1-1:1.9.0 G.01'], 10.0, 'L1', 0),
                (batch_id, own_point, codes['1-1:2.9.0 G.03'], 3.0, 'L2', 1),
                (batch_id, own_generation_point, codes['1-1:2.9.0 G.01T'], 8.0, 'L1', 0),
                (batch_id, own_generation_point, codes['1-1:2.9.0 P.01T'], 2.5, 'L1', 0),
            ])
            db.commit()

        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            headers = self.auth(tokens['access_token'])
            status = client.get('/api/v1/data-status', headers=headers)
            points = client.get('/api/v1/metering-points', headers=headers)
            summary = client.get(
                '/api/v1/energy/summary?from=2026-01-01&to=2026-01-31',
                headers=headers,
            )
            series = client.get(
                '/api/v1/energy/series?from=2026-01-01&to=2026-01-31&resolution=day',
                headers=headers,
            )
            hourly_series = client.get(
                '/api/v1/energy/series?from=2026-01-01&to=2026-01-01&resolution=hour',
                headers=headers,
            )
            foreign = client.get(
                f'/api/v1/energy/summary?from=2026-01-01&to=2026-01-31&metering_point={foreign_point}',
                headers=headers,
            )

        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.get_json()['data_status']['is_live'])
        self.assertEqual(points.status_code, 200)
        point_payload = points.get_json()['metering_points']
        self.assertEqual(len(point_payload), 2)
        self.assertNotEqual(point_payload[0]['masked_id'], own_point)
        self.assertEqual(summary.status_code, 200, summary.get_data(as_text=True))
        payload = summary.get_json()
        self.assertFalse(payload['is_live'])
        self.assertEqual(payload['totals']['consumption_kwh'], 10.0)
        self.assertEqual(payload['totals']['self_coverage_kwh'], 3.0)
        self.assertEqual(payload['derived']['residual_grid_kwh'], 7.0)
        self.assertEqual(payload['derived']['self_sufficiency_percent'], 30.0)
        self.assertEqual(payload['balance']['consumption'], {
            'total_kwh': 10.0,
            'eeg_kwh': 3.0,
            'grid_kwh': 7.0,
            'eeg_percent': 30.0,
        })
        self.assertEqual(payload['balance']['generation'], {
            'total_kwh': 8.0,
            'eeg_kwh': 5.5,
            'grid_kwh': 2.5,
            'eeg_percent': 68.75,
        })
        self.assertEqual(payload['quality'], {'L1': 3, 'L2': 1})
        self.assertEqual(series.status_code, 200, series.get_data(as_text=True))
        series_payload = series.get_json()
        self.assertFalse(series_payload['is_live'])
        self.assertEqual(series_payload['unit'], 'kWh')
        self.assertEqual(len(series_payload['series']), 1)
        self.assertEqual(series_payload['series'][0]['bucket'], '2026-01-01')
        self.assertEqual(series_payload['series'][0]['residual_grid_kwh'], 7.0)
        self.assertEqual(
            series_payload['series'][0]['balance']['consumption']['eeg_kwh'], 3.0
        )
        self.assertTrue(series_payload['series'][0]['contains_estimated_values'])
        self.assertEqual(hourly_series.status_code, 200, hourly_series.get_data(as_text=True))
        self.assertEqual(hourly_series.get_json()['series'][0]['bucket'], '2026-01-01T00:00:00')
        self.assertEqual(foreign.status_code, 404)

    def test_dashboard_and_account_are_available(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            dashboard = client.get('/api/v1/dashboard', headers=self.auth(tokens['access_token']))
            account = client.get('/api/v1/account', headers=self.auth(tokens['access_token']))
        self.assertEqual(dashboard.status_code, 200, dashboard.get_data(as_text=True))
        self.assertEqual(account.status_code, 200, account.get_data(as_text=True))
        self.assertEqual(dashboard.get_json()['account']['balance'], 0)

    def test_prices_deliver_current_eeg_tariff_and_estimate_reference(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute("""
                INSERT INTO prices(
                    valid_from, valid_to, price_consumption,
                    price_generation, description
                ) VALUES ('2026-01-01', '2099-12-31', 14.5, 10.2, 'EEG Tarif')
            """)
            db.commit()
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.get(
                '/api/v1/prices', headers=self.auth(tokens['access_token']))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload['current']['eeg_consumption_ct'], 14.5)
        self.assertEqual(payload['current']['eeg_generation_ct'], 10.2)
        self.assertTrue(payload['reference']['is_estimate'])

    def test_logout_revokes_access_token(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            logout = client.post('/api/v1/auth/logout', headers=self.auth(tokens['access_token']))
            after = client.get('/api/v1/me', headers=self.auth(tokens['access_token']))
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(after.status_code, 401)

    def test_device_registration_preferences_and_logout(self):
        token = 'a' * 64
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            headers = self.auth(tokens['access_token'])
            registered = client.put('/api/v1/devices/current', headers=headers, json={
                'device_token': token, 'environment': 'sandbox', 'app_version': '1.0',
            })
            changed = client.patch('/api/v1/notification-preferences', headers=headers, json={
                'sound_enabled': False, 'invoice_notifications': True,
            })
            preferences = client.get('/api/v1/notification-preferences', headers=headers)
            logout = client.post('/api/v1/auth/logout', headers=headers)
        self.assertEqual(registered.status_code, 200)
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(preferences.get_json()['preferences']['sound_enabled'])
        self.assertEqual(logout.status_code, 204)
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                'SELECT disabled_at FROM mobile_devices WHERE device_token=?', (token,)
            ).fetchone()
        self.assertIsNotNone(row['disabled_at'])

    def test_android_fcm_device_registration_keeps_case_sensitive_token(self):
        token = 'fcm:CaseSensitive-Token_1234567890-ABCDEFGHIJ'
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            response = client.put('/api/v1/devices/current', headers=self.auth(tokens['access_token']), json={
                'device_token': token, 'platform': 'android', 'environment': 'production',
                'app_version': '1.0.0',
            })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                'SELECT device_token, platform, apns_environment FROM mobile_devices WHERE device_token=?',
                (token,),
            ).fetchone()
        self.assertEqual(row['device_token'], token)
        self.assertEqual(row['platform'], 'android')
        self.assertEqual(row['apns_environment'], 'production')

    def test_web_password_change_revokes_mobile_session(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            web_login = client.post('/login', data={
                'username': 'anna', 'password': 'Sichere-Passphrase-2026',
            })
            self.assertIn(web_login.status_code, (302, 303))
            changed = client.post('/change-password', data={
                'old_password': 'Sichere-Passphrase-2026',
                'new_password': 'Neue-Sichere-Passphrase-2026',
                'confirm_password': 'Neue-Sichere-Passphrase-2026',
            })
            after = client.get('/api/v1/me', headers=self.auth(tokens['access_token']))
        self.assertIn(changed.status_code, (302, 303))
        self.assertEqual(after.status_code, 401)

    def test_dashboard_delivers_messages_and_read_receipts(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            global_id = db.execute(
                "INSERT INTO mobile_messages (title, body) VALUES ('Info', 'Für alle')"
            ).lastrowid
            member_id = db.execute(
                "INSERT INTO mobile_messages (title, body, level, member_id) "
                "VALUES ('Persönlich', 'Nur für Anna', 'warning', ?)",
                (self.member_id,),
            ).lastrowid
            db.execute(
                "INSERT INTO mobile_messages (title, body, member_id) "
                "VALUES ('Fremd', 'Nicht für Anna', ?)",
                (self.other_member_id,),
            )
            db.commit()
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            headers = self.auth(tokens['access_token'])
            dashboard = client.get('/api/v1/dashboard', headers=headers)
            delivered = dashboard.get_json()['unread_messages']
            for message_id in (global_id, member_id):
                read = client.post(f'/api/v1/messages/{message_id}/read', headers=headers)
                self.assertEqual(read.status_code, 204)
            after = client.get('/api/v1/messages', headers=headers)
        self.assertEqual([row['id'] for row in delivered], [global_id, member_id])
        self.assertEqual(after.get_json()['messages'], [])

    def test_invoice_pdf_preview_is_member_scoped(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            own_invoice = db.execute(
                "INSERT INTO invoices (period_from, period_to, status) VALUES (?, ?, 'finalized')",
                ('2026-03-01', '2026-03-31'),
            ).lastrowid
            foreign_invoice = db.execute(
                "INSERT INTO invoices (period_from, period_to, status) VALUES (?, ?, 'finalized')",
                ('2026-04-01', '2026-04-30'),
            ).lastrowid
            db.execute(
                "INSERT INTO invoice_items (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur) "
                "VALUES (?, ?, 'consumption', 10, 15, 1.5)",
                (own_invoice, self.member_id),
            )
            db.execute(
                "INSERT INTO invoice_items (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur) "
                "VALUES (?, ?, 'consumption', 10, 15, 1.5)",
                (foreign_invoice, self.other_member_id),
            )
            db.commit()
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            headers = self.auth(tokens['access_token'])
            own = client.get(f'/api/v1/invoices/{own_invoice}/pdf', headers=headers)
            foreign = client.get(f'/api/v1/invoices/{foreign_invoice}/pdf', headers=headers)
        self.assertEqual(own.status_code, 200, repr(own.data[:500]))
        self.assertEqual(own.mimetype, 'application/pdf')
        self.assertTrue(own.data.startswith(b'%PDF'))
        self.assertEqual(foreign.status_code, 404)

    def test_admin_can_publish_and_deactivate_app_message(self):
        with eegapp.app.test_client() as client:
            tokens = self.login(client)
            device = client.put(
                '/api/v1/devices/current', headers=self.auth(tokens['access_token']), json={
                    'device_token': 'b' * 64, 'environment': 'sandbox',
                },
            )
            self.assertEqual(device.status_code, 200)
            login = client.post('/login', data={
                'username': 'mobile-admin', 'password': 'Admin-Passphrase-2026',
            })
            self.assertIn(login.status_code, (302, 303))
            created = client.post('/admin/mobile-messages', data={
                'title': 'Wartungsfenster', 'body': 'Kurzer Ausfall am Abend.',
                'level': 'warning', 'member_id': '', 'expires_at': '',
            })
            self.assertIn(created.status_code, (302, 303))
            with eegapp.app.app_context():
                row = eegapp.get_db().execute(
                    'SELECT id, active, created_by FROM mobile_messages WHERE title=?',
                    ('Wartungsfenster',),
                ).fetchone()
                queued = eegapp.get_db().execute(
                    'SELECT COUNT(*) FROM mobile_push_outbox WHERE message_id=?', (row['id'],)
                ).fetchone()[0]
            deactivated = client.post(f'/admin/mobile-messages/{row["id"]}/deactivate')
        self.assertEqual(row['active'], 1)
        self.assertEqual(row['created_by'], 'mobile-admin')
        self.assertEqual(queued, 1)
        self.assertIn(deactivated.status_code, (302, 303))
        with eegapp.app.app_context():
            active = eegapp.get_db().execute(
                'SELECT active FROM mobile_messages WHERE id=?', (row['id'],)
            ).fetchone()['active']
        self.assertEqual(active, 0)


if __name__ == '__main__':
    unittest.main()
