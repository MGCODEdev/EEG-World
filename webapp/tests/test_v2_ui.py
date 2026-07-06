import unittest

import app as eegapp


class V2UITests(unittest.TestCase):
    def setUp(self):
        eegapp.init_db()
        eegapp.app.config['WTF_CSRF_ENABLED'] = False

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

    def test_v2_subpage_points_shell_to_embedded_existing_page(self):
        with eegapp.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self._admin_id())
                sess['_fresh'] = True

            response = client.get('/v2/import?files_sort=source_file')

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"current_path": "/import"', html)
        self.assertIn('"content_path": "/import?files_sort=source_file\\u0026embed=1"', html)

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
