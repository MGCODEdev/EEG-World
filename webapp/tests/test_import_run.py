import os
import sys
import tempfile
import types
import unittest

import app as eegapp


class ImportRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.original_db_path = eegapp.DB_PATH
        eegapp.DB_PATH = self.tmp.name
        eegapp.init_db()

    def tearDown(self):
        eegapp.DB_PATH = self.original_db_path
        sys.modules.pop('import_eda', None)
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def test_run_import_calls_importer_with_filepath_then_connection(self):
        captured = {}
        fake_module = types.ModuleType('import_eda')

        def fake_import_file(filepath, conn, allow_duplicate=False):
            captured['filepath'] = filepath
            captured['conn_type'] = type(conn).__name__
            captured['allow_duplicate'] = allow_duplicate
            conn.execute("""
                INSERT INTO import_batches (source_file, report_code, period_start, period_end, data_status)
                VALUES (?, 'RC', '2026-05-01T00:00:00', '2026-05-31T23:45:00', 'final')
            """, (os.path.basename(filepath),))
            return 42

        fake_module.import_file = fake_import_file
        fake_module.parse_filename = lambda filename: {
            'report_code': 'RC',
            'period_start': '2026-05-01T00:00:00',
            'period_end': '2026-05-31T23:45:00',
        }
        sys.modules['import_eda'] = fake_module

        with tempfile.NamedTemporaryFile(suffix='.xlsx') as upload:
            result = eegapp.run_import(upload.name, overwrite=False, data_status='provisional')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data_status'], 'provisional')
        self.assertEqual(result['records'], 42)
        self.assertEqual(captured['filepath'], upload.name)
        self.assertEqual(captured['conn_type'], 'Connection')
        self.assertFalse(captured['allow_duplicate'])

        with eegapp.app.app_context():
            batch = eegapp.get_db().execute(
                "SELECT data_status FROM import_batches WHERE source_file=?",
                (os.path.basename(upload.name),),
            ).fetchone()
        self.assertEqual(batch['data_status'], 'provisional')

    def test_final_import_replaces_provisional_batch_same_period(self):
        captured = {}
        fake_module = types.ModuleType('import_eda')

        def fake_import_file(filepath, conn, allow_duplicate=False):
            captured['allow_duplicate'] = allow_duplicate
            cur = conn.execute("""
                INSERT INTO import_batches (source_file, report_code, period_start, period_end, data_status)
                VALUES (?, 'RC', '2026-06-01T00:00:00', '2026-06-30T23:45:00', 'final')
            """, (os.path.basename(filepath),))
            conn.execute("""
                INSERT INTO measurements (
                    batch_id, metering_point_id, timestamp_start, timestamp_end,
                    interval_minutes, meter_code_id, value_kwh, quality, is_estimated
                ) VALUES (?, 'AT001', '2026-06-01T00:00:00', '2026-06-01T00:15:00', 15, 1, 1.0, 'L1', 0)
            """, (cur.lastrowid,))
            return 1

        fake_module.import_file = fake_import_file
        fake_module.parse_filename = lambda filename: {
            'report_code': 'RC',
            'period_start': '2026-06-01T00:00:00',
            'period_end': '2026-06-30T23:45:00',
        }
        sys.modules['import_eda'] = fake_module

        with eegapp.app.app_context():
            db = eegapp.get_db()
            provisional = db.execute("""
                INSERT INTO import_batches (source_file, report_code, period_start, period_end, data_status)
                VALUES ('old.xlsx', 'RC', '2026-06-01T00:00:00', '2026-06-30T23:45:00', 'provisional')
            """)
            db.execute("""
                INSERT INTO measurements (
                    batch_id, metering_point_id, timestamp_start, timestamp_end,
                    interval_minutes, meter_code_id, value_kwh, quality, is_estimated
                ) VALUES (?, 'AT001', '2026-06-01T00:00:00', '2026-06-01T00:15:00', 15, 1, 1.0, 'L1', 0)
            """, (provisional.lastrowid,))
            db.commit()

        with tempfile.NamedTemporaryFile(suffix='.xlsx') as upload:
            result = eegapp.run_import(upload.name, overwrite=False, data_status='final')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data_status'], 'final')
        self.assertEqual(result['overwritten'], 1)
        self.assertTrue(captured['allow_duplicate'])

        with eegapp.app.app_context():
            db = eegapp.get_db()
            replaced = db.execute("SELECT replaced_at FROM import_batches WHERE source_file='old.xlsx'").fetchone()
            active_provisional = db.execute(
                "SELECT COUNT(*) FROM import_batches WHERE data_status='provisional' AND replaced_at IS NULL"
            ).fetchone()[0]
        self.assertIsNotNone(replaced['replaced_at'])
        self.assertEqual(active_provisional, 0)

    def test_invoice_blocker_requires_recalculation_after_final_data_arrives(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute("""
                INSERT INTO import_batches (source_file, report_code, period_start, period_end, data_status)
                VALUES ('provisional.xlsx', 'RC', '2026-07-01T00:00:00', '2026-07-31T23:45:00', 'provisional')
            """)
            invoice = db.execute("""
                INSERT INTO invoices (period_from, period_to, data_status)
                VALUES ('2026-07-01', '2026-07-31', 'provisional')
            """)
            db.commit()
            invoice_row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice.lastrowid,)).fetchone()
            self.assertTrue(eegapp.invoice_finalization_blocker(db, invoice_row))

            db.execute("UPDATE import_batches SET data_status='final'")
            db.commit()
            invoice_row = db.execute("SELECT * FROM invoices WHERE id=?", (invoice.lastrowid,)).fetchone()
            blocker = eegapp.invoice_finalization_blocker(db, invoice_row)

        self.assertIn('neu berechnen', blocker)

    def test_provisional_invoice_detail_renders_without_redirect(self):
        with eegapp.app.app_context():
            db = eegapp.get_db()
            db.execute("""
                INSERT INTO import_batches (source_file, report_code, period_start, period_end, data_status)
                VALUES ('provisional.xlsx', 'RC', '2026-08-01T00:00:00', '2026-08-31T23:45:00', 'provisional')
            """)
            member = db.execute("INSERT INTO members (name, active) VALUES ('Max Mustermann', 1)")
            invoice = db.execute("""
                INSERT INTO invoices (period_from, period_to, data_status, total_kwh_traded, total_income, total_expense, total_margin)
                VALUES ('2026-08-01', '2026-08-31', 'provisional', 1, 1, 0, 1)
            """)
            db.execute("""
                INSERT INTO invoice_items (invoice_id, member_id, type, kwh, price_per_kwh, amount_eur)
                VALUES (?, ?, 'consumption', 1, 10, 0.10)
            """, (invoice.lastrowid, member.lastrowid))
            admin = db.execute("SELECT id, username, is_admin, member_id, role FROM users WHERE is_admin=1 LIMIT 1").fetchone()
            db.commit()
            invoice_id = invoice.lastrowid
            admin_data = dict(admin)

        with eegapp.app.test_request_context(f'/invoices/{invoice_id}', base_url='https://admin.eeg-trabocherstrasse.at'):
            from flask_login import login_user
            login_user(eegapp.User(admin_data['id'], admin_data['username'], admin_data['is_admin'], admin_data['member_id'], admin_data['role']))
            response = eegapp.invoice_detail(invoice_id)

        self.assertIsInstance(response, str)
        self.assertIn('Vorläufige Information', response)
        self.assertIn('Abschluss und Versand gesperrt', response)


if __name__ == '__main__':
    unittest.main()
