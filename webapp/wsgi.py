"""WSGI-Einstiegspunkt fuer den Produktivbetrieb hinter gunicorn.

Fuehrt die Initialisierung aus, die bisher nur im __main__-Block von app.py lief.
Der Dienst muss mit genau einem Worker laufen: der Backup-Scheduler ist ein
prozesslokaler Thread mit Einmal-Guard und wuerde sonst mehrfach starten.
"""

from app import app, init_db, _startup_mail_config_check, start_backup_scheduler

init_db()
_startup_mail_config_check()
start_backup_scheduler()

application = app
