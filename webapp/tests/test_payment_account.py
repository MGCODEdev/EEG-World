import os
import tempfile
import unittest
from datetime import timedelta

import app as eegapp


class PaymentAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db_path = eegapp.DB_PATH
        eegapp.DB_PATH = self.tmp.name
        eegapp.init_db()

    def tearDown(self):
        eegapp.DB_PATH = self.original_db_path
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _seed_member_invoice(self, db, period_from, period_to, amount, paid=False, member_id=None):
        if member_id is None:
            member = db.execute(
                "INSERT INTO members (name, email, active) VALUES (?, ?, 1)",
                ('Max Mustermann', 'max@example.org'),
            )
            member_id = member.lastrowid
        invoice = db.execute(
            """INSERT INTO invoices (period_from, period_to, status, created_at, finalized_at)
               VALUES (?, ?, 'sent', ?, ?)""",
            (period_from, period_to, f'{period_to} 10:00:00', f'{period_to} 10:00:00'),
        )
        db.execute(
            """INSERT INTO invoice_items (
                   invoice_id, member_id, type, kwh, price_per_kwh, amount_eur, paid, paid_at
               ) VALUES (?, ?, 'consumption', 100, 20, ?, ?, ?)""",
            (
                invoice.lastrowid,
                member_id,
                amount,
                1 if paid else 0,
                eegapp._paid_at_from_booking_date(eegapp.local_now().date()) if paid else None,
            ),
        )
        db.commit()
        return member_id, invoice.lastrowid

    def test_account_summary_marks_old_open_invoice_as_booking_backlog(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            old_day = (eegapp.local_now().date() - timedelta(days=20)).isoformat()
            member_id, _ = self._seed_member_invoice(db, old_day, old_day, 50.0)

            summary = eegapp.get_member_account_summary(db, member_id)

        self.assertEqual(summary['balance'], 50.0)
        self.assertEqual(summary['open_claims'], 50.0)
        self.assertEqual(summary['overdue_claims'], 50.0)
        self.assertTrue(summary['rows'][0]['is_overdue'])

    def test_account_summary_is_zero_after_active_payment_booking(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            old_day = (eegapp.local_now().date() - timedelta(days=20)).isoformat()
            member_id, invoice_id = self._seed_member_invoice(db, old_day, old_day, 50.0)
            booking_date = eegapp.local_now().date().isoformat()
            db.execute(
                """INSERT INTO payment_bookings (
                       invoice_id, member_id, amount_eur, direction, booking_date
                   ) VALUES (?, ?, 50.0, 'member_to_eeg', ?)""",
                (invoice_id, member_id, booking_date),
            )
            db.execute(
                "UPDATE invoice_items SET paid=1, paid_at=? WHERE invoice_id=? AND member_id=?",
                (eegapp._paid_at_from_booking_date(eegapp.local_now().date()), invoice_id, member_id),
            )
            db.commit()

            summary = eegapp.get_member_account_summary(db, member_id)

        self.assertEqual(summary['balance'], 0)
        self.assertEqual(summary['open_claims'], 0)
        self.assertTrue(summary['rows'][0]['paid'])
        self.assertEqual(summary['rows'][0]['booking_date'], booking_date)

    def test_booking_date_must_not_be_in_future(self):
        future = (eegapp.local_now().date() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            eegapp._parse_booking_date(future)

    def test_open_previous_invoice_is_carried_into_new_invoice_once(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            member_id, old_invoice_id = self._seed_member_invoice(
                db, '2026-01-01', '2026-03-31', 50.0
            )
            current_invoice = db.execute(
                """INSERT INTO invoices (period_from, period_to, status, created_at)
                   VALUES ('2026-04-01', '2026-06-30', 'draft', '2026-06-30 10:00:00')"""
            )
            current_invoice_id = current_invoice.lastrowid
            db.execute(
                """INSERT INTO invoice_items (
                       invoice_id, member_id, type, kwh, price_per_kwh, amount_eur
                   ) VALUES (?, ?, 'consumption', 100, 20, 20.0)""",
                (current_invoice_id, member_id),
            )

            carryovers = eegapp.calculate_carryovers_for_period(db, '2026-04-01')
            eegapp.save_invoice_carryovers(db, current_invoice_id, carryovers)
            db.commit()

            rows = eegapp.get_payment_rows(db, member_id=member_id)
            old_row = next(row for row in rows if row['invoice_id'] == old_invoice_id)
            current_row = next(row for row in rows if row['invoice_id'] == current_invoice_id)
            summary = eegapp.get_member_account_summary(db, member_id)

        self.assertEqual(carryovers[0]['amount'], 50.0)
        self.assertTrue(old_row['is_settled_by_carryover'])
        self.assertEqual(old_row['carried_forward_to_invoice_id'], current_invoice_id)
        self.assertEqual(current_row['energy_total'], 20.0)
        self.assertEqual(current_row['carryover_total'], 50.0)
        self.assertEqual(current_row['net_total'], 70.0)
        self.assertEqual(summary['balance'], 70.0)

    def test_previous_credit_reduces_new_invoice_amount(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            member_id, _ = self._seed_member_invoice(
                db, '2026-01-01', '2026-03-31', -30.0
            )
            current_invoice = db.execute(
                """INSERT INTO invoices (period_from, period_to, status, created_at)
                   VALUES ('2026-04-01', '2026-06-30', 'draft', '2026-06-30 10:00:00')"""
            )
            current_invoice_id = current_invoice.lastrowid
            db.execute(
                """INSERT INTO invoice_items (
                       invoice_id, member_id, type, kwh, price_per_kwh, amount_eur
                   ) VALUES (?, ?, 'consumption', 100, 20, 20.0)""",
                (current_invoice_id, member_id),
            )
            carryovers = eegapp.calculate_carryovers_for_period(db, '2026-04-01')
            eegapp.save_invoice_carryovers(db, current_invoice_id, carryovers)
            db.commit()

            row = next(
                row for row in eegapp.get_payment_rows(db, member_id=member_id)
                if row['invoice_id'] == current_invoice_id
            )

        self.assertEqual(carryovers[0]['amount'], -30.0)
        self.assertEqual(row['energy_total'], 20.0)
        self.assertEqual(row['carryover_total'], -30.0)
        self.assertEqual(row['net_total'], -10.0)


if __name__ == '__main__':
    unittest.main()
