import os
import tempfile
import unittest
from datetime import date

import app as eegapp


class PaymentBookingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db_path = eegapp.DB_PATH
        eegapp.DB_PATH = self.tmp.name
        eegapp.init_db()
        eegapp.app.config['WTF_CSRF_ENABLED'] = False
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute("INSERT INTO members (id, name, iban) VALUES (1, 'Testmitglied', 'AT00')")
            db.execute("""INSERT INTO invoices (id, period_from, period_to, status)
                          VALUES (1, '2026-01-01', '2026-03-31', 'sent')""")
            # Mitglied schuldet der EEG 100 EUR.
            db.execute("""INSERT INTO invoice_items
                          (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur, paid)
                          VALUES (1, 1, 'consumption', 500, 20, 100.0, 0)""")
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

    def _book(self, client, amount=None, booking_date=None, reason='Testbuchung laut Kontoauszug'):
        data = {'invoice_id': '1', 'member_id': '1',
                'booking_date': booking_date or date.today().isoformat()}
        if amount is not None:
            data['amount_eur'] = amount
        if reason is not None:
            data['change_reason'] = reason
        return client.post('/payments/mark_paid', data=data, follow_redirects=True)

    def _row(self):
        with eegapp.app.app_context():
            return eegapp.get_payment_row(eegapp.get_db(), 1, 1)

    def test_full_booking_settles_row(self):
        self._book(self._client())
        row = self._row()
        self.assertTrue(row['paid'])
        self.assertEqual(row['booked_total'], 100.0)
        self.assertEqual(row['open_amount'], 0.0)
        self.assertFalse(row['is_partially_booked'])

    def test_underpayment_keeps_remainder_open(self):
        self._book(self._client(), amount='60,00')
        row = self._row()
        self.assertFalse(row['paid'])
        self.assertTrue(row['is_partially_booked'])
        self.assertEqual(row['booked_total'], 60.0)
        self.assertEqual(row['open_amount'], 40.0)
        with eegapp.app.app_context():
            paid_flags = [r['paid'] for r in eegapp.get_db().execute(
                "SELECT paid FROM invoice_items WHERE invoice_id=1 AND member_id=1")]
        self.assertEqual(paid_flags, [0])

    def test_second_booking_settles_remainder(self):
        client = self._client()
        self._book(client, amount='60')
        self._book(client, amount='40')
        row = self._row()
        self.assertTrue(row['paid'])
        self.assertEqual(row['booked_total'], 100.0)
        self.assertEqual(len(row['bookings']), 2)

    def test_overpayment_creates_credit(self):
        self._book(self._client(), amount='100,01')
        row = self._row()
        self.assertFalse(row['paid'])
        self.assertEqual(row['open_amount'], -0.01)
        self.assertEqual(row['open_direction'], 'eeg_to_member')

    def test_credit_can_be_refunded(self):
        client = self._client()
        self._book(client, amount='100.01')
        # Rueckerstattung des Guthabens: negative Buchung.
        self._book(client, amount='-0.01')
        row = self._row()
        self.assertTrue(row['paid'])
        self.assertEqual(row['booked_total'], 100.0)

    def test_booking_amount_can_be_corrected(self):
        client = self._client()
        self._book(client, amount='100')
        booking_id = self._row()['bookings'][0]['id']
        response = client.post(f'/payments/bookings/{booking_id}/edit',
                               data={'amount_eur': '99,50',
                                     'booking_date': date.today().isoformat(),
                                     'change_reason': 'Bankbeleg weicht ab'},
                               follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        row = self._row()
        self.assertEqual(row['booked_total'], 99.5)
        self.assertEqual(row['open_amount'], 0.5)
        self.assertFalse(row['paid'])

    def test_correcting_booking_back_to_full_settles_row(self):
        client = self._client()
        self._book(client, amount='60')
        booking_id = self._row()['bookings'][0]['id']
        client.post(f'/payments/bookings/{booking_id}/edit',
                    data={'amount_eur': '100', 'booking_date': date.today().isoformat(),
                          'change_reason': 'Restzahlung eingegangen'},
                    follow_redirects=True)
        self.assertTrue(self._row()['paid'])

    def test_single_booking_can_be_reversed(self):
        client = self._client()
        self._book(client, amount='60')
        booking_id = self._row()['bookings'][0]['id']
        client.post(f'/payments/bookings/{booking_id}/reverse',
                    data={'change_reason': 'Falsch erfasst'}, follow_redirects=True)
        row = self._row()
        self.assertEqual(row['bookings'], [])
        self.assertEqual(row['open_amount'], 100.0)
        self.assertFalse(row['paid'])

    def test_edit_requires_change_reason(self):
        client = self._client()
        self._book(client, amount='100')
        booking_id = self._row()['bookings'][0]['id']
        response = client.post(f'/payments/bookings/{booking_id}/edit',
                               data={'amount_eur': '90', 'booking_date': date.today().isoformat(),
                                     'change_reason': 'kurz'},
                               follow_redirects=True)
        self.assertIn('Änderungsgrund', response.get_data(as_text=True))
        self.assertEqual(self._row()['booked_total'], 100.0)

    def test_reverse_requires_change_reason(self):
        client = self._client()
        self._book(client, amount='100')
        booking_id = self._row()['bookings'][0]['id']
        response = client.post(f'/payments/bookings/{booking_id}/reverse',
                               data={'change_reason': ''}, follow_redirects=True)
        self.assertIn('Änderungsgrund', response.get_data(as_text=True))
        self.assertEqual(len(self._row()['bookings']), 1)

    def test_mark_unpaid_requires_change_reason(self):
        client = self._client()
        self._book(client)
        response = client.post('/payments/mark_unpaid',
                               data={'invoice_id': '1', 'member_id': '1'},
                               follow_redirects=True)
        self.assertIn('Änderungsgrund', response.get_data(as_text=True))
        self.assertTrue(self._row()['paid'])

    def test_deviating_amount_requires_change_reason(self):
        client = self._client()
        response = self._book(client, amount='60', reason=None)
        self.assertIn('Änderungsgrund', response.get_data(as_text=True))
        self.assertEqual(self._row()['bookings'], [])

    def test_matching_amount_needs_no_reason(self):
        client = self._client()
        response = self._book(client, reason=None)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._row()['paid'])

    def test_change_history_records_reason(self):
        client = self._client()
        self._book(client, amount='60', reason='Teilzahlung laut Kontoauszug')
        booking_id = self._row()['bookings'][0]['id']
        client.post(f'/payments/bookings/{booking_id}/edit',
                    data={'amount_eur': '70', 'booking_date': date.today().isoformat(),
                          'change_reason': 'Betrag laut Bankbeleg korrigiert'},
                    follow_redirects=True)
        changes = self._row()['bookings'][0]['changes']
        self.assertEqual([c['action'] for c in changes], ['create', 'edit'])
        self.assertEqual(changes[0]['reason'], 'Teilzahlung laut Kontoauszug')
        self.assertEqual(changes[1]['reason'], 'Betrag laut Bankbeleg korrigiert')
        self.assertEqual(changes[1]['old_amount_eur'], 60.0)
        self.assertEqual(changes[1]['new_amount_eur'], 70.0)

    def test_reason_is_written_to_audit_log(self):
        client = self._client()
        self._book(client, amount='60', reason='Teilzahlung laut Kontoauszug')
        booking_id = self._row()['bookings'][0]['id']
        client.post(f'/payments/bookings/{booking_id}/edit',
                    data={'amount_eur': '70', 'booking_date': date.today().isoformat(),
                          'change_reason': 'Betrag laut Bankbeleg korrigiert'},
                    follow_redirects=True)
        with eegapp.app.app_context():
            details = [r['detail'] for r in eegapp.get_db().execute(
                "SELECT detail FROM audit_log WHERE action LIKE 'payment%' ORDER BY id")]
        self.assertTrue(any('Grund: Teilzahlung laut Kontoauszug' in d for d in details))
        self.assertTrue(any('Grund: Betrag laut Bankbeleg korrigiert' in d for d in details))

    def test_unchanged_edit_is_rejected(self):
        client = self._client()
        self._book(client, amount='100')
        booking_id = self._row()['bookings'][0]['id']
        response = client.post(f'/payments/bookings/{booking_id}/edit',
                               data={'amount_eur': '100', 'booking_date': date.today().isoformat(),
                                     'change_reason': 'Versehentlich gespeichert'},
                               follow_redirects=True)
        self.assertIn('unverändert', response.get_data(as_text=True))

    def test_history_is_visible_on_payments_page(self):
        client = self._client()
        self._book(client, amount='60', reason='Teilzahlung laut Kontoauszug')
        html = client.get('/payments').get_data(as_text=True)
        self.assertIn('Änderungsverlauf', html)
        self.assertIn('Teilzahlung laut Kontoauszug', html)
        self.assertIn('data-confirm-booking', html)

    def test_zero_amount_is_rejected(self):
        response = self._book(self._client(), amount='0')
        self.assertIn('darf nicht null sein', response.get_data(as_text=True))
        self.assertEqual(self._row()['bookings'], [])

    def test_remainder_is_carried_into_next_invoice(self):
        self._book(self._client(), amount='60')
        with eegapp.app.app_context():
            carryovers = eegapp.calculate_carryovers_for_period(eegapp.get_db(), '2026-04-01')
        self.assertEqual(len(carryovers), 1)
        self.assertEqual(carryovers[0]['amount'], 40.0)
        self.assertEqual(carryovers[0]['member_id'], 1)
        self.assertIn('Restforderung', carryovers[0]['description'])

    def test_overpayment_is_carried_as_credit(self):
        self._book(self._client(), amount='100.01')
        with eegapp.app.app_context():
            carryovers = eegapp.calculate_carryovers_for_period(eegapp.get_db(), '2026-04-01')
        self.assertEqual(carryovers[0]['amount'], -0.01)
        self.assertIn('Überzahlung', carryovers[0]['description'])

    def test_settled_row_is_not_carried(self):
        self._book(self._client())
        with eegapp.app.app_context():
            carryovers = eegapp.calculate_carryovers_for_period(eegapp.get_db(), '2026-04-01')
        self.assertEqual(carryovers, [])

    def test_member_account_overview_shows_balance(self):
        self._book(self._client(), amount='60')
        with eegapp.app.app_context():
            accounts = eegapp.get_member_account_overview(eegapp.get_db())
        self.assertEqual(len(accounts), 1)
        account = accounts[0]
        self.assertEqual(account['member_name'], 'Testmitglied')
        self.assertEqual(account['invoiced_total'], 100.0)
        self.assertEqual(account['booked_total'], 60.0)
        self.assertEqual(account['balance'], 40.0)
        self.assertEqual(account['deviating_rows'], 1)

    def test_member_account_summary_uses_open_amount(self):
        self._book(self._client(), amount='60')
        with eegapp.app.app_context():
            summary = eegapp.get_member_account_summary(eegapp.get_db(), 1)
        self.assertEqual(summary['balance'], 40.0)
        self.assertEqual(summary['open_claims'], 40.0)
        self.assertEqual(summary['history'][0]['balance_after'], 40.0)

    def test_cashbook_uses_actually_booked_amount(self):
        self._book(self._client(), amount='60')
        with eegapp.app.app_context():
            book = eegapp.build_cashbook(eegapp.get_db())
        self.assertEqual(book['summary']['income_total'], 60.0)
        self.assertEqual(book['summary']['bank_balance'], 60.0)

    def test_cashbook_lists_every_booking_separately(self):
        client = self._client()
        self._book(client, amount='60', booking_date='2026-05-01')
        self._book(client, amount='40', booking_date='2026-05-20')
        with eegapp.app.app_context():
            book = eegapp.build_cashbook(eegapp.get_db())
        energy = [row for row in book['rows'] if row['source'] == 'energy']
        self.assertEqual(len(energy), 2)
        self.assertEqual(sorted(row['amount_eur'] for row in energy), [40.0, 60.0])
        self.assertEqual(book['summary']['bank_balance'], 100.0)

    def test_member_accounts_page_renders(self):
        client = self._client()
        self._book(client, amount='60')
        response = client.get('/mitgliederkonten')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Mitgliedskonten', html)
        self.assertIn('Testmitglied', html)

    def test_member_account_detail_renders(self):
        client = self._client()
        self._book(client, amount='60')
        response = client.get('/mitgliederkonten/1')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Kontoauszug', response.get_data(as_text=True))

    def test_v2_member_accounts_data_is_delivered(self):
        client = self._client()
        self._book(client, amount='60')
        response = client.get('/v2/mitgliederkonten')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('"type": "member_accounts"', html)

    def test_payments_page_renders_with_partial_booking(self):
        client = self._client()
        self._book(client, amount='60')
        response = client.get('/payments')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        # Offen bleibt der Restbetrag, nicht der volle Sollbetrag.
        self.assertIn('Rest von 100.00 €', html)
        self.assertIn('bereits gebucht: 60.00 €', html)
        self.assertIn('offen: 40.00 €', html)
        self.assertIn('/payments/bookings/1/edit', html)
        self.assertIn('/payments/bookings/1/reverse', html)


if __name__ == '__main__':
    unittest.main()
