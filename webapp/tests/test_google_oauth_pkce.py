import json
import os
import tempfile
import unittest
import zipfile

import app as eegapp


class FakeDriveFiles:
    def __init__(self, files=None, metadata=None):
        self._files = files or []
        self._metadata = metadata or {}
        self.list_kwargs = None
        self.updated = None

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return self

    def get(self, **kwargs):
        self.get_kwargs = kwargs
        return self

    def update(self, **kwargs):
        self.updated = kwargs
        return self

    def execute(self):
        if self.updated:
            return {
                'id': self.updated['fileId'],
                'name': self._metadata.get('name'),
                'trashed': True,
            }
        if getattr(self, 'get_kwargs', None):
            return self._metadata
        return {'files': self._files}


class FakeDriveService:
    def __init__(self, files):
        self.files_resource = files

    def files(self):
        return self.files_resource


class GoogleOAuthPKCETests(unittest.TestCase):
    def setUp(self):
        eegapp.init_db()
        eegapp.app.config['WTF_CSRF_ENABLED'] = False

    def _admin_id(self):
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                "SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1"
            ).fetchone()
            return row['id']

    def test_google_oauth_pkce_verifier_survives_redirect(self):
        captured = {}

        class FakeCredentials:
            def to_json(self):
                return (
                    '{"token":"access","refresh_token":"refresh",'
                    '"token_uri":"https://oauth2.googleapis.com/token",'
                    '"client_id":"client","client_secret":"secret",'
                    '"scopes":["https://www.googleapis.com/auth/drive.file"]}'
                )

        class FakeFlow:
            credentials = FakeCredentials()

            def authorization_url(self, **kwargs):
                captured['auth_kwargs'] = kwargs
                return 'https://accounts.google.com/o/oauth2/v2/auth', kwargs['state']

            def fetch_token(self, authorization_response, code_verifier):
                captured['fetch_url'] = authorization_response
                captured['code_verifier'] = code_verifier

        original_flow = eegapp._google_drive_flow
        original_write = eegapp._write_private_json_file
        try:
            eegapp._google_drive_flow = lambda: FakeFlow()
            eegapp._write_private_json_file = lambda path, payload: captured.setdefault('token_payload', payload)

            with eegapp.app.test_client() as client:
                with client.session_transaction() as sess:
                    sess['_user_id'] = str(self._admin_id())
                    sess['_fresh'] = True

                start = client.get('/admin/backup/google/connect')
                self.assertEqual(start.status_code, 302)
                self.assertEqual(captured['auth_kwargs']['code_challenge_method'], 'S256')
                self.assertTrue(captured['auth_kwargs']['code_challenge'])

                with client.session_transaction() as sess:
                    state = sess['google_drive_oauth_state']
                    correlation_id = sess['google_drive_oauth_correlation_id']

                with eegapp.app.app_context():
                    row = eegapp.get_db().execute(
                        "SELECT code_verifier FROM oauth_pkce_sessions WHERE id=? AND state=?",
                        (correlation_id, state),
                    ).fetchone()
                    self.assertIsNotNone(row)
                    stored_verifier = row['code_verifier']

                callback = client.get(f'/admin/backup/google/callback?state={state}&code=fake-code')
                self.assertEqual(callback.status_code, 302)
                self.assertEqual(captured['code_verifier'], stored_verifier)
                self.assertIn('code=fake-code', captured['fetch_url'])

                with client.session_transaction() as sess:
                    self.assertNotIn('google_drive_oauth_state', sess)
                    self.assertNotIn('google_drive_oauth_correlation_id', sess)

                with eegapp.app.app_context():
                    row = eegapp.get_db().execute(
                        "SELECT id FROM oauth_pkce_sessions WHERE id=?",
                        (correlation_id,),
                    ).fetchone()
                    self.assertIsNone(row)
        finally:
            eegapp._google_drive_flow = original_flow
            eegapp._write_private_json_file = original_write

    def test_list_google_drive_backups_filters_and_normalizes_files(self):
        files = FakeDriveFiles([
            {
                'id': 'driveid123',
                'name': 'eeg_manual_20260703_201500.zip',
                'size': '2097152',
                'createdTime': '2026-07-03T18:15:00Z',
                'modifiedTime': '2026-07-03T18:16:00Z',
                'webViewLink': 'https://drive.google.com/file/d/driveid123',
                'mimeType': 'application/zip',
            },
            {
                'id': 'other123',
                'name': 'not_a_backup.zip',
                'size': '1',
            },
        ])
        original_service = eegapp._google_drive_service
        try:
            eegapp._google_drive_service = lambda: FakeDriveService(files)
            with eegapp.app.app_context():
                backups = eegapp.list_google_drive_backups(eegapp.get_db())
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0]['name'], 'eeg_manual_20260703_201500.zip')
            self.assertEqual(backups[0]['size'], 2097152)
            self.assertIn("name contains 'eeg_'", files.list_kwargs['q'])
        finally:
            eegapp._google_drive_service = original_service

    def test_private_json_file_is_encrypted_when_key_is_set(self):
        original_key = os.environ.get('EEG_DATA_ENCRYPTION_KEY')
        os.environ['EEG_DATA_ENCRYPTION_KEY'] = 'test-encryption-key-for-google-drive-secrets'
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        try:
            payload = {'refresh_token': 'very-secret-refresh-token'}
            eegapp._write_private_json_file(tmp.name, payload)

            with open(tmp.name, encoding='utf-8') as f:
                raw = f.read()
            self.assertNotIn('very-secret-refresh-token', raw)
            stored = json.loads(raw)
            self.assertEqual(stored['_eeg_encrypted'], 1)

            self.assertEqual(eegapp._load_private_json_file(tmp.name), payload)
        finally:
            if original_key is None:
                os.environ.pop('EEG_DATA_ENCRYPTION_KEY', None)
            else:
                os.environ['EEG_DATA_ENCRYPTION_KEY'] = original_key
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def test_safe_invoice_pdf_filename_removes_path_characters(self):
        filename = eegapp.safe_invoice_pdf_filename(2, 7, '../Max Muster/Privat')
        self.assertEqual(filename, 'abrechnung_2_7_Max_Muster_Privat.pdf')

    def test_validate_backup_zip_rejects_unexpected_files(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        tmp.close()
        try:
            with zipfile.ZipFile(tmp.name, 'w') as zf:
                zf.writestr('eeg_data.db', b'db')
                zf.writestr('instance/google_drive_token.json', b'nope')
            with zipfile.ZipFile(tmp.name, 'r') as zf:
                with self.assertRaises(ValueError):
                    eegapp.validate_backup_zip(zf)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def test_trash_google_drive_backup_rejects_non_backup_file(self):
        files = FakeDriveFiles(metadata={
            'id': 'driveid123',
            'name': 'private_document.zip',
            'mimeType': 'application/zip',
            'trashed': False,
        })
        original_service = eegapp._google_drive_service
        try:
            eegapp._google_drive_service = lambda: FakeDriveService(files)
            with eegapp.app.app_context():
                with self.assertRaises(ValueError):
                    eegapp.trash_google_drive_backup(eegapp.get_db(), 'driveid123')
            self.assertIsNone(files.updated)
        finally:
            eegapp._google_drive_service = original_service

    def test_trash_google_drive_backup_moves_valid_backup_to_trash(self):
        files = FakeDriveFiles(metadata={
            'id': 'driveid123',
            'name': 'eeg_auto_20260703_021500.zip',
            'mimeType': 'application/zip',
            'trashed': False,
        })
        original_service = eegapp._google_drive_service
        try:
            eegapp._google_drive_service = lambda: FakeDriveService(files)
            with eegapp.app.app_context():
                deleted = eegapp.trash_google_drive_backup(eegapp.get_db(), 'driveid123')
            self.assertEqual(deleted['name'], 'eeg_auto_20260703_021500.zip')
            self.assertTrue(files.updated['body']['trashed'])
        finally:
            eegapp._google_drive_service = original_service


if __name__ == '__main__':
    unittest.main()
