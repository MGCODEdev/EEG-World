import sqlite3
import unittest

from core.security import is_safe_redirect_url, sanitize_newsletter_html, validate_password
from services.billing import calculate_billing


class SecurityServiceTests(unittest.TestCase):
    def test_redirects_are_limited_to_same_host(self):
        host = 'https://eeg.example/'
        self.assertTrue(is_safe_redirect_url('/portal', host))
        self.assertTrue(is_safe_redirect_url('https://eeg.example/settings', host))
        self.assertFalse(is_safe_redirect_url('https://evil.example/phishing', host))

    def test_newsletter_sanitizer_removes_unsafe_attributes(self):
        html = sanitize_newsletter_html(
            '<p onclick="attack()">Hallo <a href="javascript:attack()">Welt</a></p>'
        )
        self.assertEqual(html, '<p>Hallo <a>Welt</a></p>')

    def test_password_policy_rejects_short_passwords(self):
        self.assertIn('mindestens', validate_password('kurz', 'admin'))
        self.assertEqual(validate_password('eine-lange-sichere-passphrase', 'admin'), '')


class BillingServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE members (
                id INTEGER PRIMARY KEY, name TEXT, bezug_zp TEXT,
                einspeiser_zp TEXT, active INTEGER
            );
            CREATE TABLE meter_codes (id INTEGER PRIMARY KEY, code TEXT);
            CREATE TABLE measurements (
                metering_point_id TEXT, meter_code_id INTEGER,
                timestamp_start TEXT, value_kwh REAL
            );
            INSERT INTO members VALUES (1, 'Testmitglied', 'AT-CONS', 'AT-GEN', 1);
            INSERT INTO meter_codes VALUES (1, '1-1:2.9.0 G.03');
            INSERT INTO meter_codes VALUES (2, '1-1:2.9.0 G.01T');
            INSERT INTO meter_codes VALUES (3, '1-1:2.9.0 P.01T');
            INSERT INTO measurements VALUES ('AT-CONS', 1, '2026-01-15T12:00:00', 10.0);
            INSERT INTO measurements VALUES ('AT-GEN', 2, '2026-01-15T12:00:00', 8.0);
            INSERT INTO measurements VALUES ('AT-GEN', 3, '2026-01-15T12:00:00', 2.0);
        """)

    def tearDown(self):
        self.db.close()

    def test_calculation_keeps_consumption_generation_and_carryovers(self):
        result = calculate_billing(
            self.db, '2026-01-01', '2026-01-31', 12.0, 8.0,
            carryover_provider=lambda db, period: [{'period': period}],
        )
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['total_kwh'], 10.0)
        self.assertEqual(result['total_income'], 1.2)
        self.assertEqual(result['total_expense'], 0.48)
        self.assertEqual(result['total_margin'], 0.72)
        self.assertEqual(result['carryovers'], [{'period': '2026-01-01'}])


if __name__ == '__main__':
    unittest.main()
