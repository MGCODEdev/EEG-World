import os
import unittest

from app import (
    _build_invitation_email,
    _is_valid_email,
    _mail_header,
    _validate_mail_config,
    app,
    public_url_for,
)


class MailConfigTests(unittest.TestCase):
    def setUp(self):
        self._public_base_url = app.config.get('PUBLIC_BASE_URL')
        self._server_name_public = app.config.get('SERVER_NAME_PUBLIC')
        self._is_production = app.view_functions['login'].__globals__['_IS_PRODUCTION']
        self._redirect_internal_http = os.environ.get('EEG_REDIRECT_INTERNAL_HTTP')

    def tearDown(self):
        app.config['PUBLIC_BASE_URL'] = self._public_base_url
        app.config['SERVER_NAME_PUBLIC'] = self._server_name_public
        app.view_functions['login'].__globals__['_IS_PRODUCTION'] = self._is_production
        if self._redirect_internal_http is None:
            os.environ.pop('EEG_REDIRECT_INTERNAL_HTTP', None)
        else:
            os.environ['EEG_REDIRECT_INTERNAL_HTTP'] = self._redirect_internal_http

    def test_from_header_contains_valid_address(self):
        header = _mail_header('EEG Portal', 'office@example.org')
        self.assertIn('<office@example.org>', header)

    def test_umlaut_name_is_encoded_or_preserved(self):
        header = _mail_header('EEG Österreich', 'office@example.org')
        # Header may be MIME-encoded or UTF-8 plain depending on policy.
        self.assertTrue('Österreich' in header or '=?utf-8?' in header.lower())

    def test_invalid_from_address_is_rejected(self):
        cfg = {
            'smtp_host': 'mail.your-server.de',
            'smtp_user': 'office@example.org',
            'smtp_pass': 'x',
            'from_address': 'invalid',
            'reply_to_address': 'office@example.org',
        }
        ok, _ = _validate_mail_config(cfg)
        self.assertFalse(ok)

    def test_missing_from_address_is_rejected(self):
        cfg = {
            'smtp_host': 'mail.your-server.de',
            'smtp_user': 'office@example.org',
            'smtp_pass': 'x',
            'from_address': '',
            'reply_to_address': 'office@example.org',
        }
        ok, _ = _validate_mail_config(cfg)
        self.assertFalse(ok)

    def test_cross_domain_from_is_rejected(self):
        cfg = {
            'smtp_host': 'mail.your-server.de',
            'smtp_user': 'office@example.org',
            'smtp_pass': 'x',
            'from_address': 'other@example.com',
            'reply_to_address': 'office@example.org',
        }
        ok, _ = _validate_mail_config(cfg)
        self.assertFalse(ok)

    def test_same_domain_alias_is_allowed(self):
        cfg = {
            'smtp_host': 'mail.your-server.de',
            'smtp_user': 'office@example.org',
            'smtp_pass': 'x',
            'from_address': 'billing@example.org',
            'reply_to_address': 'office@example.org',
        }
        ok, _ = _validate_mail_config(cfg)
        self.assertTrue(ok)

    def test_email_validator(self):
        self.assertTrue(_is_valid_email('office@example.org'))
        self.assertFalse(_is_valid_email('office@example'))

    def test_invitation_email_contains_sender_hint_and_steps(self):
        subject, text, html = _build_invitation_email(
            'Max Mustermann',
            'max@example.org',
            'member',
            'https://portal.example.org/invite/abc',
            '2026-05-31T23:59:00',
            {
                'org_name': 'EEG Portal',
                'org_email': 'office@example.org',
                'org_address': 'Teststrasse 1',
                'org_website': 'https://example.org',
            },
        )

        self.assertEqual(subject, 'Einladung zum EEG Portal')
        self.assertIn('Christian und Markus von der EEG', text)
        self.assertIn('Eigenes Passwort festlegen', html)
        self.assertIn('https://portal.example.org/invite/abc', html)

    def test_invitation_email_can_include_inline_logo(self):
        _, _, html = _build_invitation_email(
            'Max Mustermann',
            'max@example.org',
            'member',
            'https://portal.example.org/invite/abc',
            '2026-05-31T23:59:00',
            {
                'org_name': 'EEG Portal',
                'org_email': 'office@example.org',
                'org_address': 'Teststrasse 1',
                'org_website': 'https://example.org',
            },
            logo_src='cid:eeg-logo',
        )

        self.assertIn('src="cid:eeg-logo"', html)
        self.assertIn('alt="EEG Portal"', html)

    def test_invitation_email_escapes_html_values(self):
        _, text, html = _build_invitation_email(
            '<Max>',
            'max@example.org',
            'admin',
            'https://portal.example.org/invite/a&b',
            '2026-05-31T23:59:00',
            {
                'org_name': 'EEG <Portal>',
                'org_email': 'office@example.org',
                'org_address': '',
                'org_website': '',
            },
        )

        self.assertIn('<Max>', text)
        self.assertIn('&lt;Max&gt;', html)
        self.assertIn('EEG &lt;Portal&gt;', html)
        self.assertIn('https://portal.example.org/invite/a&amp;b', html)

    def test_public_url_for_uses_configured_public_base_url(self):
        app.config['PUBLIC_BASE_URL'] = 'https://admin.eeg-trabocherstrasse.at/'
        app.config['SERVER_NAME_PUBLIC'] = 'localhost'
        with app.test_request_context('/', base_url='http://10.0.10.226:5000/'):
            invite_url = public_url_for('invite_accept', token='abc123')
        self.assertEqual(invite_url, 'https://admin.eeg-trabocherstrasse.at/invite/abc123')

    def test_public_url_for_falls_back_to_public_server_name(self):
        app.config['PUBLIC_BASE_URL'] = ''
        app.config['SERVER_NAME_PUBLIC'] = 'admin.eeg-trabocherstrasse.at'
        with app.test_request_context('/', base_url='http://10.0.10.226:5000/'):
            invite_url = public_url_for('invite_accept', token='abc123')
        self.assertEqual(invite_url, 'https://admin.eeg-trabocherstrasse.at/invite/abc123')

    def test_internal_host_redirect_is_disabled_by_default(self):
        app.config['PUBLIC_BASE_URL'] = 'https://admin.eeg-trabocherstrasse.at'
        app.view_functions['login'].__globals__['_IS_PRODUCTION'] = True
        os.environ.pop('EEG_REDIRECT_INTERNAL_HTTP', None)
        with app.test_client() as client:
            response = client.get('/login', base_url='http://10.0.10.226:5000/')
        self.assertEqual(response.status_code, 200)

    def test_internal_host_redirects_to_public_login_when_enabled(self):
        app.config['PUBLIC_BASE_URL'] = 'https://admin.eeg-trabocherstrasse.at'
        app.view_functions['login'].__globals__['_IS_PRODUCTION'] = True
        os.environ['EEG_REDIRECT_INTERNAL_HTTP'] = 'true'
        with app.test_client() as client:
            response = client.get('/login', base_url='http://10.0.10.226:5000/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], 'https://admin.eeg-trabocherstrasse.at/login')

    def test_https_proxy_request_does_not_redirect_on_internal_host_header(self):
        app.config['PUBLIC_BASE_URL'] = 'https://admin.eeg-trabocherstrasse.at'
        app.view_functions['login'].__globals__['_IS_PRODUCTION'] = True
        with app.test_client() as client:
            response = client.get(
                '/login',
                base_url='http://10.0.10.226:5000/',
                headers={'X-Forwarded-Proto': 'https'},
            )
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
