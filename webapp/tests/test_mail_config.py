import unittest

from app import _is_valid_email, _mail_header, _validate_mail_config


class MailConfigTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
