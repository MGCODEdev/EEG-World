"""Short-lived, integrity-checked staging for two-phase EDA imports."""

import hashlib
import json
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.eda_preview import preview_eda_xlsx


STAGING_LIFETIME_MINUTES = 20
_STORAGE_KEY = re.compile(r"^[0-9a-f]{64}$")


class ImportStagingError(ValueError):
    pass


def _utc_string(value=None):
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_root(root):
    root = Path(root).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _stage_path(root, storage_key, original_filename):
    if not _STORAGE_KEY.fullmatch(storage_key or ""):
        raise ImportStagingError("Ungültiger Speicherverweis.")
    root = Path(root).resolve()
    path = (root / storage_key / original_filename).resolve()
    if root not in path.parents or path.parent.name != storage_key:
        raise ImportStagingError("Ungültiger Speicherpfad.")
    return path


def cleanup_expired_staged_imports(db, root, now=None):
    """Expire database rows and remove only their validated staging directories."""
    now_text = _utc_string(now)
    rows = db.execute("""
        SELECT id, storage_key, original_filename
        FROM import_staging
        WHERE consumed_at IS NULL AND cancelled_at IS NULL AND expires_at <= ?
    """, (now_text,)).fetchall()
    for row in rows:
        try:
            path = _stage_path(root, row["storage_key"], row["original_filename"])
            shutil.rmtree(path.parent, ignore_errors=True)
        except ImportStagingError:
            pass
        db.execute(
            "UPDATE import_staging SET cancelled_at=? WHERE id=?",
            (now_text, row["id"]),
        )
    if rows:
        db.commit()
    return len(rows)


def stage_uploaded_import(db, upload, original_filename, user_id, data_status,
                          overwrite_existing, root, lifetime_minutes=STAGING_LIFETIME_MINUTES):
    """Persist an upload privately and return its one-time confirmation token."""
    if not original_filename or not original_filename.lower().endswith(".xlsx"):
        raise ImportStagingError("Nur XLSX-Dateien werden unterstützt.")
    if Path(original_filename).name != original_filename:
        raise ImportStagingError("Ungültiger Dateiname.")
    root = _ensure_root(root)
    storage_key = secrets.token_hex(32)
    stage_dir = root / storage_key
    stage_dir.mkdir(mode=0o700)
    path = _stage_path(root, storage_key, original_filename)
    token = secrets.token_urlsafe(32)
    created = datetime.now(timezone.utc)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            source = upload.stream if hasattr(upload, "stream") else upload
            shutil.copyfileobj(source, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(path, 0o600)
        preview = preview_eda_xlsx(str(path))
        expires = created + timedelta(minutes=lifetime_minutes)
        db.execute("""
            INSERT INTO import_staging (
                token_hash, user_id, original_filename, storage_key, sha256,
                size_bytes, data_status, overwrite_existing, preview_json,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            _token_hash(token), int(user_id), original_filename, storage_key,
            preview.sha256, preview.size_bytes, data_status,
            1 if overwrite_existing else 0,
            json.dumps(preview.to_dict(), ensure_ascii=False),
            _utc_string(created), _utc_string(expires),
        ))
        db.commit()
    except Exception:
        db.rollback()
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise
    return {
        "token": token,
        "filename": original_filename,
        "data_status": data_status,
        "overwrite": bool(overwrite_existing),
        "expires_at": _utc_string(expires),
        "preview": preview.to_dict(),
        "has_blocking_errors": any(w.severity == "error" for w in preview.warnings),
    }


def claim_staged_import(db, token, user_id, root, now=None):
    """Atomically claim a stage and verify that its bytes are unchanged."""
    now_text = _utc_string(now)
    row = db.execute("""
        SELECT * FROM import_staging
        WHERE token_hash=? AND user_id=? AND consumed_at IS NULL
          AND cancelled_at IS NULL AND claimed_at IS NULL AND expires_at > ?
    """, (_token_hash(token or ""), int(user_id), now_text)).fetchone()
    if row is None:
        raise ImportStagingError("Die Importvorschau ist ungültig, abgelaufen oder bereits verwendet.")
    updated = db.execute("""
        UPDATE import_staging SET claimed_at=?
        WHERE id=? AND claimed_at IS NULL AND consumed_at IS NULL AND cancelled_at IS NULL
    """, (now_text, row["id"])).rowcount
    db.commit()
    if updated != 1:
        raise ImportStagingError("Diese Importvorschau wird bereits verarbeitet.")
    try:
        path = _stage_path(root, row["storage_key"], row["original_filename"])
        if not path.is_file() or _file_hash(path) != row["sha256"]:
            raise ImportStagingError("Die bereitgestellte Datei ist nicht mehr unverändert vorhanden.")
    except Exception:
        release_staged_import(db, row["id"])
        raise
    return {
        "id": row["id"],
        "path": str(path),
        "filename": row["original_filename"],
        "data_status": row["data_status"],
        "overwrite": bool(row["overwrite_existing"]),
        "preview": json.loads(row["preview_json"]),
    }


def release_staged_import(db, stage_id):
    db.execute("""
        UPDATE import_staging SET claimed_at=NULL
        WHERE id=? AND consumed_at IS NULL AND cancelled_at IS NULL
    """, (stage_id,))
    db.commit()


def consume_staged_import(db, stage, root):
    now_text = _utc_string()
    updated = db.execute("""
        UPDATE import_staging SET consumed_at=?
        WHERE id=? AND claimed_at IS NOT NULL AND consumed_at IS NULL
    """, (now_text, stage["id"])).rowcount
    db.commit()
    if updated != 1:
        raise ImportStagingError("Importvorschau konnte nicht abgeschlossen werden.")
    path = Path(stage["path"])
    expected_root = Path(root).resolve()
    if expected_root in path.resolve().parents:
        shutil.rmtree(path.parent, ignore_errors=True)


def cancel_staged_import(db, token, user_id, root):
    row = db.execute("""
        SELECT id, storage_key, original_filename FROM import_staging
        WHERE token_hash=? AND user_id=? AND consumed_at IS NULL
          AND cancelled_at IS NULL AND claimed_at IS NULL
    """, (_token_hash(token or ""), int(user_id))).fetchone()
    if row is None:
        raise ImportStagingError("Die Importvorschau ist nicht mehr verfügbar.")
    db.execute(
        "UPDATE import_staging SET cancelled_at=? WHERE id=?",
        (_utc_string(), row["id"]),
    )
    db.commit()
    path = _stage_path(root, row["storage_key"], row["original_filename"])
    shutil.rmtree(path.parent, ignore_errors=True)
