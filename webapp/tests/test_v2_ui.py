import os
import tempfile
import unittest

import app as eegapp


class V2UITests(unittest.TestCase):
    def setUp(self):
        # Eigene Datenbank pro Test: init_db() wuerde sonst gegen die
        # Produktivdatenbank laufen.
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db_path = eegapp.DB_PATH
        eegapp.DB_PATH = self.tmp.name
        eegapp.init_db()
        eegapp.app.config['WTF_CSRF_ENABLED'] = False

    def tearDown(self):
        eegapp.DB_PATH = self.original_db_path
        for suffix in ('', '-wal', '-shm'):
            try:
                os.unlink(self.tmp.name + suffix)
            except OSError:
                pass

    def _admin_id(self):
        with eegapp.app.app_context():
            row = eegapp.get_db().execute(
                "SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1"
            ).fetchone()
            return row['id']

    def test_v2_dashboard_renders_react_entry_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('window.EEG_V2_DATA', html)
        self.assertIn('/static/v2/assets/index-', html)
        self.assertIn('type="module"', html)
        self.assertIn('id="root"', html)
        self.assertIn('"type": "dashboard"', html)

    def test_v2_members_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/members')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/members"', html)
        self.assertIn('"type": "members"', html)
        self.assertIn('"counts"', html)

    def test_v2_import_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/import')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/import"', html)
        self.assertIn('"type": "import"', html)
        self.assertIn('"csrf_token"', html)

    def test_v2_prices_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/prices')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/prices"', html)
        self.assertIn('"type": "prices"', html)
        self.assertIn('"csrf_token"', html)

    def test_v2_invoices_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/invoices')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/invoices"', html)
        self.assertIn('"type": "invoices"', html)

    def test_v2_payments_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/payments')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/payments"', html)
        self.assertIn('"type": "payments"', html)
        self.assertIn('"csrf_token"', html)

    def test_v2_newsletter_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/newsletter')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/newsletter"', html)
        self.assertIn('"type": "newsletter"', html)
        self.assertIn('"csrf_token"', html)

    def test_v2_reports_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/reports')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/reports"', html)
        self.assertIn('"type": "reports"', html)

    def test_v2_users_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/admin/users')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/admin/users"', html)
        self.assertIn('"type": "users"', html)
        self.assertIn('"contracts"', html)
        self.assertIn('"csrf_token"', html)

    def test_v2_audit_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/admin/audit')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/admin/audit"', html)
        self.assertIn('"type": "audit"', html)
        self.assertIn('"pagination"', html)

    def test_v2_backup_renders_native_data_for_admin(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/admin/backup')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/admin/backup"', html)
        self.assertIn('"type": "backup"', html)
        self.assertIn('"local_backups"', html)

    def test_v2_subpage_points_shell_to_embedded_existing_page(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/admin/database')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/admin/database"', html)
        self.assertIn('"content_path": "/admin/database?embed=1"', html)

    def test_embed_mode_can_be_framed_by_same_origin_only(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/import?embed=1')

        self.assertEqual(response.status_code, 200)
        self.assertIn('SAMEORIGIN', response.headers['X-Frame-Options'])
        self.assertIn("frame-ancestors 'self'", response.headers['Content-Security-Policy'])
        self.assertIn('body class="embed-mode"', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
