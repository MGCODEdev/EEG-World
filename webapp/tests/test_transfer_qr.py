import os
import tempfile
import unittest

import app as eegapp


class SepaQrPayloadTests(unittest.TestCase):
    """EPC069-12 Datensatz, wie ihn Banking-Apps erwarten."""

    def test_payload_structure(self):
        payload = eegapp.build_epc_payload(
            recipient='Hubert Greimer',
            iban='AT61 1904 3002 3457 3201',
            amount=24.62,
            remittance='EEG-Abr 1/2026 Gutschrift',
            bic='GIBAATWWXXX')
        lines = payload.split('\n')
        self.assertEqual(lines[0], 'BCD')
        self.assertEqual(lines[1], '002')
        self.assertEqual(lines[2], '1')
        self.assertEqual(lines[3], 'SCT')
        self.assertEqual(lines[4], 'GIBAATWWXXX')
        self.assertEqual(lines[5], 'Hubert Greimer')
        self.assertEqual(lines[6], 'AT611904300234573201')
        self.assertEqual(lines[7], 'EUR24.62')
        self.assertEqual(lines[8], '')
        self.assertEqual(lines[9], '')
        self.assertEqual(lines[10], 'EEG-Abr 1/2026 Gutschrift')

    def test_payload_without_bic_is_allowed(self):
        payload = eegapp.build_epc_payload('Anna Muster', 'AT611904300234573201', 5.0)
        self.assertEqual(payload.split('\n')[4], '')

    def test_umlauts_are_transliterated(self):
        payload = eegapp.build_epc_payload(
            'Brigitta Hochegger-Haubmann Groß & Söhne', 'AT611904300234573201',
            1.0, 'Rückzahlung Überschuss')
        lines = payload.split('\n')
        self.assertEqual(lines[5], 'Brigitta Hochegger-Haubmann Gross und Soehne')
        self.assertEqual(lines[10], 'Rueckzahlung Ueberschuss')
        payload.encode('ascii')  # darf keine Sonderzeichen mehr enthalten

    def test_amount_is_always_two_decimals(self):
        payload = eegapp.build_epc_payload('Anna Muster', 'AT611904300234573201', 0.1)
        self.assertEqual(payload.split('\n')[7], 'EUR0.10')

    def test_invalid_amounts_are_rejected(self):
        for amount in (0, 0.004, -5, 1000000000):
            with self.assertRaises(ValueError):
                eegapp.build_epc_payload('Anna Muster', 'AT611904300234573201', amount)

    def test_missing_recipient_is_rejected(self):
        with self.assertRaises(ValueError):
            eegapp.build_epc_payload('   ', 'AT611904300234573201', 10.0)

    def test_payload_stays_within_size_limit(self):
        payload = eegapp.build_epc_payload('M' * 200, 'AT611904300234573201', 10.0, 'Z' * 200)
        self.assertLessEqual(len(payload.encode('utf-8')), eegapp.EPC_MAX_PAYLOAD_BYTES)

    def test_iban_is_normalized(self):
        self.assertEqual(eegapp.normalize_iban(' at61 1904 3002 3457 3201 '),
                         'AT611904300234573201')

    def test_invalid_iban_is_rejected(self):
        for iban in ('', 'AT61190430023457320', 'AT621904300234573201', 'HALLO'):
            with self.assertRaises(ValueError):
                eegapp.normalize_iban(iban)

    def test_svg_is_rendered(self):
        svg = eegapp.render_epc_qr_svg(
            eegapp.build_epc_payload('Anna Muster', 'AT611904300234573201', 12.34))
        self.assertIn('<svg', svg)
        self.assertIn('</svg>', svg)


class TransferQrRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db_path = eegapp.DB_PATH
        eegapp.DB_PATH = self.tmp.name
        eegapp.init_db()
        eegapp.app.config['WTF_CSRF_ENABLED'] = False
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute("""INSERT INTO members (id, name, iban, bic, account_holder)
                          VALUES (1, 'Anna Muster', 'AT611904300234573201',
                                  'GIBAATWWXXX', 'Anna Maria Muster')""")
            db.execute("INSERT INTO members (id, name) VALUES (2, 'Ohne Bankverbindung')")
            db.execute("""INSERT INTO invoices (id, period_from, period_to, status)
                          VALUES (1, '2026-01-01', '2026-03-31', 'sent')""")
            # Beide Mitglieder haben eine Gutschrift, die EEG schuldet Geld.
            for member_id, amount in ((1, 42.5), (2, 10.0)):
                db.execute("""INSERT INTO invoice_items
                              (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur, paid)
                              VALUES (1, ?, 'generation', 100, 10, ?, 0)""", (member_id, amount))
            db.commit()

    def tearDown(self):
        eegapp.DB_PATH = self.original_db_path
        for suffix in ('', '-wal', '-shm'):
            try:
                os.unlink(self.tmp.name + suffix)
            except OSError:
                pass

    def _client(self):
        client = eegapp.app.test_client()
        with eegapp.app.app_context():
            admin_id = eegapp.get_db().execute(
                "SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()['id']
        with client.session_transaction() as sess:
            sess['_user_id'] = str(admin_id)
            sess['_fresh'] = True
        return client

    def test_qr_route_returns_svg(self):
        response = self._client().get('/payments/1/1/qr.svg')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/svg+xml')
        self.assertIn(b'<svg', response.data)

    def test_qr_route_uses_open_amount_by_default(self):
        with eegapp.app.app_context():
            row = eegapp.get_payment_row(eegapp.get_db(), 1, 1)
        self.assertEqual(row['open_amount'], -42.5)
        payload = eegapp.build_epc_payload(
            'Anna Maria Muster', 'AT611904300234573201', abs(row['open_amount']),
            eegapp.payment_transfer_reference(row), 'GIBAATWWXXX')
        self.assertEqual(payload.split('\n')[7], 'EUR42.50')

    def test_qr_route_accepts_custom_amount(self):
        response = self._client().get('/payments/1/1/qr.svg?amount=12,50')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<svg', response.data)

    def test_qr_route_without_iban_returns_error(self):
        response = self._client().get('/payments/1/2/qr.svg')
        self.assertEqual(response.status_code, 400)
        self.assertIn('IBAN', response.get_data(as_text=True))

    def test_qr_route_requires_login(self):
        response = eegapp.app.test_client().get('/payments/1/1/qr.svg')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_unknown_row_returns_404(self):
        self.assertEqual(self._client().get('/payments/9/9/qr.svg').status_code, 404)

    def test_reference_contains_invoice_and_member(self):
        with eegapp.app.app_context():
            row = eegapp.get_payment_row(eegapp.get_db(), 1, 1)
        reference = eegapp.payment_transfer_reference(row)
        self.assertIn('EEG-Abr 1/2026', reference)
        self.assertIn('Anna Muster', reference)

    def test_qr_route_encodes_expected_payload(self):
        """Die Route muss genau den erwarteten EPC-Datensatz kodieren."""
        response = self._client().get('/payments/1/1/qr.svg?amount=-42.50')
        expected = eegapp.render_epc_qr_svg('\n'.join([
            'BCD', '002', '1', 'SCT',
            'GIBAATWWXXX',
            'Anna Maria Muster',
            'AT611904300234573201',
            'EUR42.50',
            '', '',
            'EEG-Abr 1/2026 Gutschrift Anna Muster',
        ]))
        self.assertEqual(response.get_data(as_text=True), expected)

    def test_encoded_data_matches_payload(self):
        """Gegenprobe: die Bibliothek kodiert den Datensatz unveraendert."""
        import qrcode

        payload = eegapp.build_epc_payload(
            'Anna Muster', 'AT611904300234573201', 42.5, 'Gutschrift Rückzahlung')
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        encoded = b''.join(segment.data for segment in qr.data_list).decode('utf-8')
        self.assertEqual(encoded, payload)
        self.assertIn('Gutschrift Rueckzahlung', encoded)

    def test_payments_page_shows_qr_button_only_with_iban(self):
        html = self._client().get('/payments').get_data(as_text=True)
        self.assertIn('data-transfer-qr', html)
        self.assertIn('/payments/1/1/qr.svg', html)
        self.assertNotIn('/payments/1/2/qr.svg', html)
        self.assertIn('transferQrModal', html)


if __name__ == '__main__':
    unittest.main()
