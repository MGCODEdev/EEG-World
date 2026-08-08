#!/usr/bin/env python3
"""Einmalige APNs-Outbox-Verarbeitung; für systemd timer/cron gedacht."""

import json
import os
import sqlite3

from services.apns import process_outbox
from services.mobile_schema import ensure_mobile_device_schema


DB_PATH = os.environ.get('EEG_DB_PATH', '/var/www/eeg/eeg_data.db')


def main():
    with sqlite3.connect(DB_PATH, timeout=30) as db:
        db.row_factory = sqlite3.Row
        ensure_mobile_device_schema(db)
        # Die Schema-Aktualisierung muss auch dann dauerhaft sein, wenn ein
        # nachfolgender externer APNs-Aufruf fehlschlaegt.
        db.commit()
        print(json.dumps(process_outbox(db), sort_keys=True))


if __name__ == '__main__':
    main()
