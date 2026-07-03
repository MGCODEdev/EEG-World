import unittest

import app as eegapp


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


if __name__ == '__main__':
    unittest.main()
